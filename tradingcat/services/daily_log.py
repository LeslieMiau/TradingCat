from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from tradingcat.domain.models import Market
from tradingcat.services.trading_session import TradingSessionService, TradingPhase

if TYPE_CHECKING:
    from tradingcat.domain.models import DailyTradingPlanNote, DailyTradingSummaryNote
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.ai_researcher import AIAnalysis, AIFeature, AIResearcher
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.services.market_awareness import MarketAwarenessService
    from tradingcat.services.trading_journal import TradingJournalService


logger = logging.getLogger(__name__)


@dataclass
class DailyLogBriefingResult:
    as_of: date
    market: str
    awareness_snapshot: object
    ai_briefing: object | None = None
    insight_count: int = 0
    briefing_path: str | None = None
    skipped_reason: str | None = None


@dataclass
class DailyLogReviewResult:
    as_of: date
    plan: object | None = None
    summary: object | None = None
    ai_journal: object | None = None
    unresolved_insight_count: int = 0
    deviations: list[str] = field(default_factory=list)
    parameter_hints: list[str] = field(default_factory=list)


class DailyLogService:
    """Unified daily lifecycle: pre-market briefing + post-market review + journal.

    Replaces PreMarketOrchestrator, PostMarketReflectionService, and
    TradingJournalService with a single entry point. The three phases of a
    trading day (plan → execute → review) are accessible through one service.
    """

    def __init__(
        self,
        *,
        trading_journal: TradingJournalService,
        ai_researcher: Callable[[], AIResearcher],
        insight_store: Callable[[], InsightStore],
        insight_engine: Callable[[], InsightEngine],
        awareness_service: Callable[[], MarketAwarenessService],
        market_calendar: object,
        data_dir: str | Path = "data",
        plan_factory: Callable[[date], DailyTradingPlanNote] | None = None,
        summary_factory: Callable[[date], DailyTradingSummaryNote] | None = None,
    ) -> None:
        self._journal = trading_journal
        self._ai_getter = ai_researcher
        self._insight_store_getter = insight_store
        self._insight_engine_getter = insight_engine
        self._awareness_getter = awareness_service
        self._market_calendar = market_calendar
        self._data_dir = Path(data_dir)
        self._plan_factory = plan_factory
        self._summary_factory = summary_factory

    # ── Journal passthrough (TradingJournalService compat) ──────────────────

    @property
    def trading_journal(self) -> TradingJournalService:
        return self._journal

    def save_plan(self, note: DailyTradingPlanNote) -> DailyTradingPlanNote:
        return self._journal.save_plan(note)

    def save_summary(self, note: DailyTradingSummaryNote) -> DailyTradingSummaryNote:
        return self._journal.save_summary(note)

    def list_plans(self, account: str | None = None) -> list[DailyTradingPlanNote]:
        return self._journal.list_plans(account)

    def list_summaries(self, account: str | None = None) -> list[DailyTradingSummaryNote]:
        return self._journal.list_summaries(account)

    def latest_plan(self, account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote | None:
        return self._journal.latest_plan(account, as_of)

    def latest_summary(self, account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote | None:
        return self._journal.latest_summary(account, as_of)

    def clear(self) -> None:
        self._journal.clear()

    # ── Plan / Summary generation (delegates to app-level factories) ────────

    def generate_plan(self, as_of: date | None = None) -> DailyTradingPlanNote | None:
        if self._plan_factory is None:
            logger.warning("daily_log: no plan_factory configured, skipping plan generation")
            return None
        return self._plan_factory(as_of or date.today())

    def generate_summary(self, as_of: date | None = None) -> DailyTradingSummaryNote | None:
        if self._summary_factory is None:
            logger.warning("daily_log: no summary_factory configured, skipping summary generation")
            return None
        return self._summary_factory(as_of or date.today())

    # ── Pre-market briefing ────────────────────────────────────────────────

    def run_briefing(self, as_of: date | None = None, market: Market | None = None) -> DailyLogBriefingResult:
        """Run the pre-market briefing chain: awareness → insights → AI briefing.

        Awareness is always computed from cached bars regardless of trading phase.
        Only insight-engine and AI-briefing are gated behind PRE_MARKET.
        """
        as_of = as_of or date.today()
        target_market = market or Market.CN

        # Always compute awareness snapshot — uses cached price bars, no live data needed
        try:
            awareness = self._awareness_getter().snapshot(as_of=as_of)
        except Exception as exc:
            logger.warning("briefing: awareness snapshot failed (%s); using fallback", exc)
            awareness = _default_awareness(as_of)

        session_svc = TradingSessionService(self._market_calendar)
        session = session_svc.get_phase(target_market)

        if session.phase != TradingPhase.PRE_MARKET:
            logger.info("briefing [%s]: AI/insight skipped (phase=%s, as_of=%s)", target_market.value, session.phase, as_of)
            return DailyLogBriefingResult(
                as_of=as_of,
                market=target_market.value,
                awareness_snapshot=awareness,
                ai_briefing=self._build_fallback_briefing(awareness),
                skipped_reason=f"current phase is {session.phase.value}, not pre_market",
            )

        insight_result = self._insight_engine_getter().run(as_of=as_of)
        logger.info("briefing: insight engine produced %d insights", len(insight_result.produced))

        ai_briefing = None
        briefing_path = None
        if self._ai_getter().enabled:
            try:
                awareness_dict = _safe_asdict(awareness)
                ai_briefing = self._ai_getter().market_briefing(market_data=awareness_dict)
                path = self._ai_getter().save_analysis(ai_briefing)
                briefing_path = str(path)
            except Exception as exc:
                logger.warning("briefing: AI briefing failed (%s); continuing without it", exc)
        else:
            ai_briefing = self._build_fallback_briefing(awareness)

        return DailyLogBriefingResult(
            as_of=as_of,
            market=target_market.value,
            awareness_snapshot=awareness,
            ai_briefing=ai_briefing,
            insight_count=len(insight_result.produced),
            briefing_path=briefing_path,
        )

    # ── Post-market review ─────────────────────────────────────────────────

    def run_review(self, as_of: date | None = None) -> DailyLogReviewResult:
        """Run post-market review: plan vs actual → AI journal → unresolved insights."""
        as_of = as_of or date.today()

        plan = self._journal.latest_plan(as_of=as_of)

        summary = None
        if self._summary_factory:
            summary = self._summary_factory(as_of)
        else:
            summary = self._journal.latest_summary(as_of=as_of)

        deviations: list[str] = []
        if plan and summary:
            deviations = self._compare_plan_to_actual(plan, summary)

        unresolved = self._insight_store_getter().list(include_dismissed=False)
        unresolved_count = len(unresolved)

        parameter_hints: list[str] = []
        if unresolved_count > 0:
            parameter_hints.append(f"{unresolved_count} 条洞察待处理（请在 Dashboard 中确认或忽略）")

        ai_journal = None
        if self._ai_getter().enabled:
            try:
                daily_data = self._build_journal_data(as_of, plan, summary, unresolved_count, deviations)
                ai_journal = self._ai_getter().journal(daily_data=daily_data)
                self._ai_getter().save_analysis(ai_journal)
            except Exception as exc:
                logger.warning("review: AI journal failed (%s); continuing without it", exc)
        else:
            ai_journal = self._build_fallback_journal(plan, summary, deviations, unresolved_count)

        return DailyLogReviewResult(
            as_of=as_of,
            plan=plan,
            summary=summary,
            ai_journal=ai_journal,
            unresolved_insight_count=unresolved_count,
            deviations=deviations,
            parameter_hints=parameter_hints,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _compare_plan_to_actual(plan: DailyTradingPlanNote, summary: DailyTradingSummaryNote) -> list[str]:
        deviations: list[str] = []
        plan_intents = plan.counts.get("intent_count", 0)
        summary_orders = summary.metrics.get("order_count", 0)
        if isinstance(plan_intents, (int, float)) and isinstance(summary_orders, (int, float)):
            if plan_intents > 0 and summary_orders < plan_intents:
                deviations.append(f"計劃 {int(plan_intents)} 條訂單意圖，實際僅 {int(summary_orders)} 條訂單")
        if plan.status == "blocked":
            deviations.append("今日計劃因執行門禁阻塞")
        return deviations

    @staticmethod
    def _build_journal_data(
        as_of: date,
        plan: DailyTradingPlanNote | None,
        summary: DailyTradingSummaryNote | None,
        unresolved_count: int,
        deviations: list[str],
    ) -> dict[str, object]:
        return {
            "as_of": str(as_of),
            "plan_headline": plan.headline if plan else "N/A",
            "plan_status": plan.status if plan else "N/A",
            "summary_headline": summary.headline if summary else "N/A",
            "unresolved_insight_count": unresolved_count,
            "deviations": deviations,
        }

    # ── Fallback content (when AI is unavailable) ─────────────────────────

    def _build_fallback_briefing(self, awareness: object) -> object:
        """Build a structured briefing from awareness data when AI is unavailable."""
        from tradingcat.services.ai_researcher import AIAnalysis, AIFeature

        regime_label = {
            "bullish": "看涨", "neutral": "中性", "caution": "谨慎", "risk_off": "避险"
        }.get(str(_val(awareness, "overall_regime")), "未知")

        risk_label = {
            "build_risk": "加仓", "hold_pace": "稳健",
            "reduce_risk": "减仓", "pause_new_adds": "暂停"
        }.get(str(_val(awareness, "risk_posture")), "未知")

        score = _val(awareness, "overall_score")

        lines = [
            f"## 市场体制: {regime_label}",
            f"风险姿态: {risk_label}",
            f"综合评分: {score:.4f}" if isinstance(score, (int, float)) else "综合评分: N/A",
            "",
        ]

        # Per-market evidence
        for view in _val_list(awareness, "market_views"):
            market_str = str(_val(view, "market"))
            market_label = {"US": "美股", "HK": "港股", "CN": "A股"}.get(market_str, market_str)
            regime_str = str(_val(view, "regime"))
            lines.append(f"### {market_label} ({regime_str})")
            lines.append(f"评分: {_val(view, 'score', 'N/A')}")
            lines.append(f"动量(21d): {_fmt_pct(_val(view, 'momentum_21d'))}")
            lines.append(f"回撤(20d): {_fmt_pct(_val(view, 'drawdown_20d'))}")
            lines.append(f"波动率(20d): {_fmt_pct(_val(view, 'realized_volatility_20d'))}")
            lines.append("")

        # Fear & Greed
        fg = _val(awareness, "fear_greed")
        if fg:
            lines.append(f"恐惧贪婪指数: {_val(fg, 'score', 'N/A')}")

        # Participation
        part = _val(awareness, "participation")
        if part:
            decision = _val(part, "decision")
            prob = _val(part, "probability")
            odds = _val(part, "odds")
            lines.append(f"参与决策: {decision}")
            if isinstance(prob, (int, float)):
                lines.append(f"概率: {prob:.2f}")
            if isinstance(odds, (int, float)):
                lines.append(f"赔率: {odds:.2f}")

        return AIAnalysis(
            feature=AIFeature.BRIEFING,
            content="\n".join(filter(None, lines)),
            summary=f"市场体制 {regime_label}，风险姿态 {risk_label}（由本地数据计算，非 AI 生成）",
            confidence="medium",
            metadata={
                "observations": self._basic_observations(awareness),
                "support_resistance": [],
                "sector_rotation": [],
                "source": "local_computation",
            },
        )

    @staticmethod
    def _basic_observations(awareness: object) -> list[dict[str, object]]:
        """Extract basic observations from market-view evidence rows."""
        observations: list[dict[str, object]] = []
        for view in _val_list(awareness, "market_views"):
            market_str = str(_val(view, "market"))
            for ev in _val_list(view, "evidence"):
                label = _val(ev, "label", "")
                explanation = _val(ev, "explanation", "")
                status_str = str(_val(ev, "status"))
                if explanation:
                    observations.append({
                        "symbol": f"{market_str} {label}" if label else market_str,
                        "observation": str(explanation),
                        "confidence": 0.7 if status_str == "supportive" else 0.5 if status_str == "mixed" else 0.3,
                        "rationale": f"基于本地价格数据计算的{label}信号",
                        "time_horizon": "short_term",
                    })
        return observations

    def _build_fallback_journal(
        self,
        plan: object | None,
        summary: object | None,
        deviations: list[str],
        unresolved_count: int,
    ) -> object:
        """Build a structured post-market review when AI is unavailable."""
        from tradingcat.services.ai_researcher import AIAnalysis, AIFeature

        lines = []
        if plan:
            headline = getattr(plan, "headline", "")
            status = getattr(plan, "status", "N/A")
            counts = getattr(plan, "counts", {}) or {}
            lines.append(f"## 计划回顾")
            lines.append(f"状态: {status}")
            lines.append(f"信号数: {counts.get('signal_count', 0)}, 意图数: {counts.get('intent_count', 0)}")
            lines.append(f"标题: {headline}")
            lines.append("")

        if summary:
            headline = getattr(summary, "headline", "")
            highlights = getattr(summary, "highlights", []) or []
            blockers = getattr(summary, "blockers", []) or []
            next_actions = getattr(summary, "next_actions", []) or []
            lines.append("## 总结回顾")
            lines.append(f"标题: {headline}")
            if highlights:
                lines.append("亮点:")
                for h in highlights:
                    lines.append(f"  - {h}")
            if blockers:
                lines.append("阻塞项:")
                for b in blockers:
                    lines.append(f"  - {b}")
            if next_actions:
                lines.append("下一步:")
                for a in next_actions:
                    lines.append(f"  - {a}")
            lines.append("")

        if deviations:
            lines.append("## 偏差分析")
            for d in deviations:
                lines.append(f"  - {d}")
            lines.append("")

        if unresolved_count:
            lines.append(f"未处理洞察: {unresolved_count} 条")

        trade_scores: list[dict[str, object]] = []
        lessons: list[dict[str, object]] = []
        adjustments: list[dict[str, object]] = []

        if plan:
            items = getattr(plan, "items", []) or []
            for item in items:
                symbol = item.get("symbol", "unknown") if isinstance(item, dict) else getattr(item, "symbol", "unknown")
                trade_scores.append({
                    "symbol": symbol,
                    "overall_score": "N/A",
                    "entry_score": "N/A",
                    "exit_score": "N/A",
                    "position_score": "N/A",
                    "note": "计划中，待执行",
                })

        for d in deviations:
            lessons.append({"category": "execution", "lesson": d, "impact": "medium"})

        if summary:
            next_actions = getattr(summary, "next_actions", []) or []
            for a in next_actions:
                adjustments.append({"action": a, "rationale": "来自交易总结", "target_outcome": "改善执行质量"})

        return AIAnalysis(
            feature=AIFeature.JOURNAL,
            content="\n".join(lines),
            summary="基于本地数据计算的复盘（非 AI 生成）",
            confidence="medium",
            metadata={
                "trade_scores": trade_scores,
                "lessons_learned": lessons,
                "adjustments": adjustments,
                "source": "local_computation",
            },
        )


def _safe_asdict(obj: object) -> dict[str, object]:
    if hasattr(obj, "model_dump"):
        result = obj.model_dump(mode="json")
    elif hasattr(obj, "__dataclass_fields__"):
        from dataclasses import fields
        result = {f.name: getattr(obj, f.name) for f in fields(obj)}
    elif isinstance(obj, dict):
        result = obj
    else:
        try:
            result = json.loads(json.dumps(obj, default=str))
        except Exception:
            return {"_raw": str(obj)}
    return _sanitize_json(result)


def _sanitize_json(obj: object) -> object:
    """Recursively replace NaN/Infinity with None so the value is JSON-safe."""
    import math as _math
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


def _default_awareness(as_of: date) -> dict[str, object]:
    """Minimal awareness snapshot when MarketAwarenessService fails."""
    return {
        "as_of": str(as_of),
        "overall_regime": "neutral",
        "confidence": "low",
        "risk_posture": "hold_pace",
        "overall_score": 0.0,
        "market_views": [],
        "evidence": [],
        "actions": [],
        "data_quality": {"status": "degraded", "degraded": True},
    }


def _fmt_pct(value: float | None) -> str:
    """Format a float as percentage string, or N/A."""
    if value is None:
        return "N/A"
    return f"{value * 100:+.2f}%"


def _val(obj: object, name: str, default: object = None) -> object:
    """Safely get attribute or dict key from obj, handling enum .value."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    raw = getattr(obj, name, default)
    if raw is default:
        return default
    return raw.value if hasattr(raw, "value") else raw


def _val_list(obj: object, name: str) -> list:
    """Safely get a list attribute or dict key."""
    if isinstance(obj, dict):
        return obj.get(name, []) or []
    raw = getattr(obj, name, None)
    return list(raw) if raw else []

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
    from tradingcat.services.ai_researcher import AIResearcher
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
        """Run the pre-market briefing chain: awareness → insights → AI briefing."""
        as_of = as_of or date.today()
        target_market = market or Market.CN

        session_svc = TradingSessionService(self._market_calendar)
        session = session_svc.get_phase(target_market)
        if session.phase != TradingPhase.PRE_MARKET:
            logger.info("briefing [%s]: skipped (phase=%s, as_of=%s)", target_market.value, session.phase, as_of)
            return DailyLogBriefingResult(
                as_of=as_of,
                market=target_market.value,
                awareness_snapshot={},
                skipped_reason=f"current phase is {session.phase.value}, not pre_market",
            )

        awareness = self._awareness_getter().snapshot(as_of=as_of)

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


def _safe_asdict(obj: object) -> dict[str, object]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dataclass_fields__"):
        from dataclasses import fields
        return {f.name: getattr(obj, f.name) for f in fields(obj)}
    if isinstance(obj, dict):
        return obj
    try:
        return json.loads(json.dumps(obj, default=str))
    except Exception:
        return {"_raw": str(obj)}

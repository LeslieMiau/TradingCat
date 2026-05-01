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
    structured_report: dict[str, object] = field(default_factory=dict)


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
        orders_reader: Callable[[], list[object]] | None = None,
        approvals_reader: Callable[[], list[object]] | None = None,
        intent_context_resolver: Callable[[str], dict[str, object] | None] | None = None,
        price_context_resolver: Callable[[str], dict[str, object]] | None = None,
        authorization_context_resolver: Callable[[str], dict[str, object]] | None = None,
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
        self._orders_reader = orders_reader
        self._approvals_reader = approvals_reader
        self._intent_context_resolver = intent_context_resolver
        self._price_context_resolver = price_context_resolver
        self._authorization_context_resolver = authorization_context_resolver

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

        insight_store = self._insight_store_getter()
        unresolved = insight_store.list(include_dismissed=False)
        unresolved_count = len(unresolved)
        structured_report = self._build_structured_review(
            plan,
            as_of=as_of,
            unresolved_count=unresolved_count,
            insight_summary=self._insight_summary(insight_store),
        )
        structured_deviations = [
            str(item.get("detail") or item.get("type") or item)
            for item in structured_report.get("deviations", [])
            if isinstance(item, dict)
        ]
        deviations = list(dict.fromkeys([*deviations, *structured_deviations]))

        parameter_hints: list[str] = []
        if unresolved_count > 0:
            parameter_hints.append(f"{unresolved_count} 条洞察待处理（请在 Dashboard 中确认或忽略）")

        ai_journal = None
        if self._ai_getter().enabled:
            try:
                daily_data = self._build_journal_data(as_of, plan, summary, unresolved_count, deviations, structured_report)
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
            structured_report=structured_report,
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

    def _build_structured_review(
        self,
        plan: DailyTradingPlanNote | None,
        *,
        as_of: date,
        unresolved_count: int,
        insight_summary: dict[str, object] | None = None,
    ) -> dict[str, object]:
        plan_items = list(getattr(plan, "items", []) or [])
        plan_intent_ids = {
            str(item.get("intent_id"))
            for item in plan_items
            if isinstance(item, dict) and item.get("intent_id")
        }
        all_orders = self._orders_reader() if self._orders_reader else []
        all_approvals = self._approvals_reader() if self._approvals_reader else []
        orders = [
            order
            for order in all_orders
            if self._review_order_in_scope(order, plan_intent_ids=plan_intent_ids, as_of=as_of)
        ]
        approvals = [
            approval
            for approval in all_approvals
            if self._review_approval_in_scope(approval, plan_intent_ids=plan_intent_ids, as_of=as_of)
        ]
        orders_by_intent = {
            str(getattr(order, "order_intent_id", "")): order
            for order in orders
            if getattr(order, "order_intent_id", "")
        }
        approvals_by_intent = {
            str(getattr(getattr(approval, "order_intent", None), "id", "")): approval
            for approval in approvals
            if getattr(getattr(approval, "order_intent", None), "id", "")
        }

        rows: list[dict[str, object]] = []
        unexecuted: list[dict[str, object]] = []
        tca_samples: list[dict[str, object]] = []
        deviations: list[dict[str, object]] = []
        approval_delays: list[dict[str, object]] = []
        fill_latencies: list[float] = []

        for item in plan_items:
            if not isinstance(item, dict):
                continue
            intent_id = str(item.get("intent_id") or "")
            order = orders_by_intent.get(intent_id)
            approval = approvals_by_intent.get(intent_id)
            price_context = self._resolve_price_context(intent_id)
            authorization_context = self._resolve_authorization_context(intent_id)
            order_row = self._serialize_order(order)
            if order_row is not None:
                order_row = self._enrich_order_from_plan_item(order_row, item)
            approval_row = self._serialize_approval(approval)
            tca = self._build_tca_sample(item, order_row, price_context)
            if tca:
                tca_samples.append(tca)
            latency = self._fill_latency_seconds(order_row, approval_row)
            if latency is not None:
                fill_latencies.append(latency)
            row = {
                "plan_item": item,
                "order": order_row,
                "approval": approval_row,
                "authorization": authorization_context,
                "tca": tca,
                "reference": price_context,
            }
            rows.append(row)
            if not intent_id:
                deviations.append({"type": "plan_item_missing_intent", "detail": f"{item.get('symbol', 'unknown')} 缺少 intent_id"})
                continue
            if order is None:
                unexecuted.append(item)
                deviations.append({"type": "unexecuted_plan_item", "detail": f"{item.get('symbol', intent_id)} 计划条目未找到订单记录"})
            elif order_row.get("status") not in {"filled", "partially_filled"}:
                deviations.append({"type": "order_not_filled", "detail": f"{item.get('symbol', intent_id)} 订单状态为 {order_row.get('status')}"})
            if approval_row and approval_row.get("status") in {"pending", "rejected", "expired"}:
                deviations.append({"type": "approval_not_completed", "detail": f"{item.get('symbol', intent_id)} 审批状态为 {approval_row.get('status')}"})
            if approval_row and approval_row.get("decision_latency_minutes") is not None:
                approval_delays.append({
                    "intent_id": intent_id,
                    "symbol": item.get("symbol"),
                    "decision_latency_minutes": approval_row["decision_latency_minutes"],
                    "status": approval_row.get("status"),
                })
            if self._is_degraded_reference(price_context):
                deviations.append({"type": "synthetic_reference", "detail": f"{item.get('symbol', intent_id)} 使用 synthetic/degraded reference"})

        extra_orders = [
            self._serialize_order(order)
            for order in orders
            if str(getattr(order, "order_intent_id", "")) not in plan_intent_ids
        ]
        for order in extra_orders:
            deviations.append({"type": "extra_order", "detail": f"{order.get('symbol') or order.get('order_intent_id')} 不在计划条目中"})
        if unresolved_count:
            deviations.append({"type": "unhandled_insights", "detail": f"{unresolved_count} 条洞察未处理"})
        filled_count = sum(1 for row in rows if (row.get("order") or {}).get("status") in {"filled", "partially_filled"})
        matched_count = sum(1 for row in rows if row.get("order"))
        tca_values = [float(row["deviation_value"]) for row in tca_samples if row.get("deviation_value") is not None]

        return {
            "scope": {
                "as_of": as_of.isoformat(),
                "account": getattr(plan, "account", None),
                "included_order_count": len(orders),
                "excluded_order_count": max(0, len(all_orders) - len(orders)),
                "included_approval_count": len(approvals),
                "excluded_approval_count": max(0, len(all_approvals) - len(approvals)),
            },
            "plan_item_count": len(plan_items),
            "order_count": len(orders),
            "matched_count": matched_count,
            "filled_count": filled_count,
            "fill_rate": round(filled_count / len(plan_items), 4) if plan_items else 0.0,
            "avg_time_to_fill_seconds": round(sum(fill_latencies) / len(fill_latencies), 2) if fill_latencies else None,
            "plan_vs_actual": {
                "planned_items": len(plan_items),
                "matched_orders": matched_count,
                "filled_orders": filled_count,
                "unexecuted_items": len(unexecuted),
                "extra_orders": len(extra_orders),
                "approval_delay_count": len(approval_delays),
            },
            "items": rows,
            "unexecuted_plan_items": unexecuted,
            "extra_orders": extra_orders,
            "approval_delays": approval_delays,
            "tca_samples": tca_samples,
            "tca_summary": {
                "sample_count": len(tca_samples),
                "avg_slippage_bps": round(sum(tca_values) / len(tca_values), 2) if tca_values else None,
                "max_abs_slippage_bps": round(max((abs(value) for value in tca_values), default=0.0), 2) if tca_values else None,
            },
            "deviations": deviations,
            "unresolved_insight_count": unresolved_count,
            "insight_summary": insight_summary or {"unresolved": unresolved_count},
            "ai_role": "AI narrative may summarize only these structured facts; it must not create facts or trading recommendations.",
        }

    def _insight_summary(self, insight_store: object) -> dict[str, object]:
        try:
            insights = insight_store.list(include_dismissed=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("review: insight summary unavailable (%s)", exc)
            return {}
        counts: dict[str, int] = {}
        for insight in insights:
            action = getattr(getattr(insight, "user_action", None), "value", getattr(insight, "user_action", None))
            label = str(action or "unknown")
            counts[label] = counts.get(label, 0) + 1
        return {
            "total": len(insights),
            "by_user_action": counts,
            "unresolved": counts.get("pending", 0),
            "dismissed": counts.get("dismissed", 0),
            "acknowledged": counts.get("acknowledged", 0),
        }

    @staticmethod
    def _review_order_in_scope(order: object, *, plan_intent_ids: set[str], as_of: date) -> bool:
        intent_id = str(getattr(order, "order_intent_id", "") or "")
        if intent_id and intent_id in plan_intent_ids:
            return True
        return DailyLogService._same_day(getattr(order, "timestamp", None), as_of)

    @staticmethod
    def _review_approval_in_scope(approval: object, *, plan_intent_ids: set[str], as_of: date) -> bool:
        intent_id = str(getattr(getattr(approval, "order_intent", None), "id", "") or "")
        if intent_id and intent_id in plan_intent_ids:
            return True
        return any(
            DailyLogService._same_day(getattr(approval, attr, None), as_of)
            for attr in ("created_at", "decided_at", "expires_at")
        )

    @staticmethod
    def _same_day(value: object, target: date) -> bool:
        if value is None:
            return False
        if isinstance(value, datetime):
            return value.date() == target
        if isinstance(value, date):
            return value == target
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date() == target
            except ValueError:
                try:
                    return date.fromisoformat(value) == target
                except ValueError:
                    return False
        return False

    def _resolve_price_context(self, intent_id: str) -> dict[str, object]:
        if not intent_id or self._price_context_resolver is None:
            return {}
        try:
            return dict(self._price_context_resolver(intent_id) or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("review: price context unavailable for %s (%s)", intent_id, exc)
            return {"error": str(exc)}

    def _resolve_authorization_context(self, intent_id: str) -> dict[str, object]:
        if not intent_id or self._authorization_context_resolver is None:
            return {}
        try:
            return dict(self._authorization_context_resolver(intent_id) or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("review: authorization context unavailable for %s (%s)", intent_id, exc)
            return {"error": str(exc)}

    def _resolve_intent_context(self, intent_id: str) -> dict[str, object]:
        if not intent_id or self._intent_context_resolver is None:
            return {}
        try:
            return dict(self._intent_context_resolver(intent_id) or {})
        except Exception as exc:  # noqa: BLE001
            logger.warning("review: intent context unavailable for %s (%s)", intent_id, exc)
            return {"error": str(exc)}

    def _serialize_order(self, order: object | None) -> dict[str, object] | None:
        if order is None:
            return None
        intent_id = str(getattr(order, "order_intent_id", "") or "")
        intent_context = self._resolve_intent_context(intent_id)
        authorization_context = self._resolve_authorization_context(intent_id)
        raw_status = getattr(order, "status", None)
        return {
            "id": getattr(order, "id", None),
            "order_intent_id": getattr(order, "order_intent_id", None),
            "broker_order_id": getattr(order, "broker_order_id", None),
            "fill_id": getattr(order, "fill_id", None),
            "status": getattr(raw_status, "value", raw_status),
            "filled_quantity": getattr(order, "filled_quantity", 0.0),
            "average_price": getattr(order, "average_price", None),
            "symbol": intent_context.get("symbol"),
            "market": intent_context.get("market") or getattr(getattr(order, "market", None), "value", getattr(order, "market", None)),
            "asset_class": intent_context.get("asset_class"),
            "currency": intent_context.get("currency"),
            "side": intent_context.get("side"),
            "strategy_id": intent_context.get("strategy_id"),
            "message": getattr(order, "message", None),
            "timestamp": getattr(order, "timestamp", None),
            "slippage": getattr(order, "slippage", None),
            "fill_source": self._fill_source(order, authorization_context),
        }

    @staticmethod
    def _enrich_order_from_plan_item(order: dict[str, object], plan_item: dict[str, object]) -> dict[str, object]:
        enriched = dict(order)
        for key in ("symbol", "market", "side", "strategy_id"):
            if not enriched.get(key) and plan_item.get(key):
                enriched[key] = plan_item.get(key)
        return enriched

    @staticmethod
    def _fill_source(order: object, authorization_context: dict[str, object]) -> str | None:
        external_source = authorization_context.get("external_source")
        if external_source:
            return str(external_source)
        fill_id = str(getattr(order, "fill_id", "") or "")
        broker_order_id = str(getattr(order, "broker_order_id", "") or "")
        if fill_id.startswith("manual-") or broker_order_id.startswith("manual-"):
            return "manual"
        if broker_order_id:
            return "broker"
        raw_status = getattr(order, "status", None)
        status = str(getattr(raw_status, "value", raw_status) or "")
        if status in {"filled", "partially_filled"}:
            return "recorded"
        return None

    @staticmethod
    def _serialize_approval(approval: object | None) -> dict[str, object] | None:
        if approval is None:
            return None
        created_at = getattr(approval, "created_at", None)
        decided_at = getattr(approval, "decided_at", None)
        latency = None
        if created_at is not None and decided_at is not None:
            latency = round((decided_at - created_at).total_seconds() / 60.0, 2)
        raw_status = getattr(approval, "status", None)
        return {
            "id": getattr(approval, "id", None),
            "intent_id": getattr(getattr(approval, "order_intent", None), "id", None),
            "status": getattr(raw_status, "value", raw_status),
            "created_at": created_at,
            "decided_at": decided_at,
            "decision_latency_minutes": latency,
            "decision_reason": getattr(approval, "decision_reason", None),
            "expires_at": getattr(approval, "expires_at", None),
        }

    @staticmethod
    def _build_tca_sample(
        plan_item: dict[str, object],
        order: dict[str, object] | None,
        price_context: dict[str, object],
    ) -> dict[str, object] | None:
        if not order:
            return None
        reference_price = price_context.get("reference_price") or price_context.get("expected_price") or plan_item.get("reference_price")
        average_price = order.get("average_price")
        if reference_price in (None, 0) or average_price in (None, 0):
            return None
        ref = float(reference_price)
        avg = float(average_price)
        side = str(plan_item.get("side") or "").lower()
        signed_ratio = (avg - ref) / ref if side != "sell" else (ref - avg) / ref
        return {
            "intent_id": order.get("order_intent_id"),
            "symbol": plan_item.get("symbol"),
            "side": side or None,
            "reference_price": ref,
            "average_price": avg,
            "deviation_metric": "slippage_bps",
            "deviation_value": round(signed_ratio * 10_000, 2),
            "recorded_slippage": order.get("slippage"),
            "reference_source": price_context.get("reference_source") or price_context.get("source"),
            "reference_quality": price_context.get("reference_quality") or price_context.get("quality"),
        }

    @staticmethod
    def _fill_latency_seconds(order: dict[str, object] | None, approval: dict[str, object] | None) -> float | None:
        if not order or order.get("status") not in {"filled", "partially_filled"}:
            return None
        order_time = DailyLogService._coerce_datetime(order.get("timestamp"))
        if order_time is None:
            return None
        approval_time = None
        if approval:
            approval_time = DailyLogService._coerce_datetime(approval.get("decided_at")) or DailyLogService._coerce_datetime(approval.get("created_at"))
        if approval_time is None:
            return None
        return max(0.0, (order_time - approval_time).total_seconds())

    @staticmethod
    def _coerce_datetime(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return None
        return None

    @staticmethod
    def _is_degraded_reference(price_context: dict[str, object]) -> bool:
        quality = str(price_context.get("reference_quality") or price_context.get("quality") or "").lower()
        source = str(price_context.get("reference_source") or price_context.get("source") or "").lower()
        return any(token in quality for token in ("synthetic", "degraded")) or any(token in source for token in ("synthetic", "fallback"))

    @staticmethod
    def _build_journal_data(
        as_of: date,
        plan: DailyTradingPlanNote | None,
        summary: DailyTradingSummaryNote | None,
        unresolved_count: int,
        deviations: list[str],
        structured_report: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "as_of": str(as_of),
            "plan_headline": plan.headline if plan else "N/A",
            "plan_status": plan.status if plan else "N/A",
            "summary_headline": summary.headline if summary else "N/A",
            "unresolved_insight_count": unresolved_count,
            "deviations": deviations,
            "structured_report": structured_report or {},
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

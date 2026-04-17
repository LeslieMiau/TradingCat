from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    MarketAwarenessActionItem,
    MarketAwarenessActionSeverity,
    MarketAwarenessConfidence,
    MarketAwarenessDataQuality,
    MarketAwarenessDataStatus,
    MarketAwarenessEvidenceRow,
    MarketAwarenessRegime,
    MarketAwarenessRiskPosture,
    MarketAwarenessSignalStatus,
    MarketAwarenessSnapshot,
)
from tradingcat.services.preflight import build_startup_preflight, summarize_validation_diagnostics
from tradingcat.services.reporting import latest_report_dir


logger = logging.getLogger(__name__)


def _safe_market_awareness_snapshot(
    snapshot_getter: Callable[[], Any],
    as_of: date,
) -> dict[str, object]:
    try:
        return snapshot_getter().snapshot(as_of).model_dump(mode="json")
    except Exception:
        logger.exception("Market awareness snapshot generation failed", extra={"as_of": as_of.isoformat()})
        return MarketAwarenessSnapshot(
            as_of=as_of,
            overall_regime=MarketAwarenessRegime.CAUTION,
            confidence=MarketAwarenessConfidence.LOW,
            risk_posture=MarketAwarenessRiskPosture.HOLD_PACE,
            overall_score=0.0,
            evidence=[
                MarketAwarenessEvidenceRow(
                    market="overall",
                    signal_key="market_awareness_failure",
                    label="Market awareness",
                    status=MarketAwarenessSignalStatus.BLOCKED,
                    value=None,
                    unit=None,
                    explanation="Market-awareness snapshot generation failed, so the response was downgraded.",
                )
            ],
            actions=[
                MarketAwarenessActionItem(
                    severity=MarketAwarenessActionSeverity.MEDIUM,
                    action_key="respect_data_gaps",
                    text="Treat this snapshot as conservative guidance until the market-awareness pipeline recovers.",
                    rationale="The market-awareness service failed and returned a degraded fallback payload.",
                )
            ],
            strategy_guidance=[],
            data_quality=MarketAwarenessDataQuality(
                status=MarketAwarenessDataStatus.DEGRADED,
                complete=False,
                degraded=True,
                fallback_driven=False,
                adapter_limitations=["market_awareness_snapshot_failed"],
                blockers=["Market-awareness snapshot generation failed."],
            ),
        ).model_dump(mode="json")


class DataQualityQueryService:
    def __init__(
        self,
        *,
        config: AppConfig,
        market_history_getter: Callable[[], Any],
        strategy_registry_getter: Callable[[], Any],
        strategy_signal_provider_getter: Callable[[], Any],
        explicit_execution_strategy_ids_getter: Callable[[], list[str]],
    ) -> None:
        self._config = config
        self._market_history_getter = market_history_getter
        self._strategy_registry_getter = strategy_registry_getter
        self._strategy_signal_provider_getter = strategy_signal_provider_getter
        self._explicit_execution_strategy_ids_getter = explicit_execution_strategy_ids_getter

    def data_quality_summary(self, *, lookback_days: int = 30, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        explicit_ids = set(self._explicit_execution_strategy_ids_getter())
        provider = self._strategy_signal_provider_getter()
        registry = self._strategy_registry_getter()
        explicit_signals = []
        for strategy in registry.select(explicit_ids):
            explicit_signals.extend(provider.execution_signals_for_strategy(strategy, evaluation_date))
        target_symbols = sorted({signal.instrument.symbol for signal in explicit_signals})
        scope = "active_execution"
        if not target_symbols:
            target_symbols = self.repair_priority_symbols(as_of=evaluation_date)[:5]
            scope = "research_universe"
        if not target_symbols:
            return {"ready": True, "scope": scope, "target_symbols": [], "incomplete_count": 0, "reports": [], "blockers": []}
        coverage = self._market_history_getter().summarize_history_coverage(
            symbols=target_symbols,
            start=evaluation_date - timedelta(days=lookback_days),
            end=evaluation_date,
        )
        incomplete = [report for report in coverage["reports"] if float(report.get("coverage_ratio", 0.0)) < 0.95]
        blockers = [str(item) for item in coverage.get("blockers", [])]
        return {
            "ready": not incomplete and not blockers,
            "scope": scope,
            "target_symbols": target_symbols,
            "incomplete_count": len(incomplete),
            "minimum_coverage_ratio": coverage.get("minimum_coverage_ratio", 1.0),
            "minimum_required_ratio": coverage.get("minimum_required_ratio", 0.95),
            "missing_symbols": coverage.get("missing_symbols", []),
            "blockers": blockers,
            "reports": coverage["reports"],
        }

    def repair_priority_symbols(self, symbols: list[str] | None = None, as_of: date | None = None) -> list[str]:
        requested = [str(symbol) for symbol in (symbols or [])]
        evaluation_date = as_of or date.today()
        strategy_signals = self._strategy_signal_provider_getter().strategy_signal_map(evaluation_date)
        explicit_ids = set(self._explicit_execution_strategy_ids_getter())
        symbol_weights: dict[str, int] = {}
        for strategy_id, signal_list in strategy_signals.items():
            boost = 3 if strategy_id in explicit_ids else 1
            for signal in signal_list:
                if signal.instrument.asset_class.value == "option":
                    symbol = str(signal.metadata.get("underlying_symbol") or signal.instrument.symbol)
                else:
                    symbol = signal.instrument.symbol
                symbol_weights[symbol] = symbol_weights.get(symbol, 0) + boost
        targets = requested or list(symbol_weights.keys())
        return sorted(targets, key=lambda symbol: (-symbol_weights.get(symbol, 0), symbol))

    def history_baseline_symbols(self, *, as_of: date | None = None, limit: int = 5) -> list[str]:
        return self.repair_priority_symbols(as_of=as_of)[:limit]

    def baseline_quote_currencies(self, symbols: list[str]) -> list[str]:
        selected = set(symbols)
        instruments = [instrument for instrument in self._market_history_getter().list_instruments() if instrument.symbol in selected]
        return sorted(
            {
                instrument.currency.upper()
                for instrument in instruments
                if instrument.currency.upper() != self._config.base_currency.upper()
            }
        )


class ReadinessQueryService:
    def __init__(
        self,
        *,
        config: AppConfig,
        strategy_signal_provider_getter: Callable[[], Any],
        strategy_registry_getter: Callable[[], Any],
        strategy_experiment_getter: Callable[[], Any],
        default_execution_strategy_ids_getter: Callable[[], list[str]],
        broker_validation: Callable[[], dict[str, object]],
        broker_status: Callable[[], dict[str, object]],
        run_market_data_smoke_test: Callable[..., dict[str, object]],
        preview_execution: Callable[[date], dict[str, object]],
        data_quality_summary: Callable[[], dict[str, object]],
        operations_rollout: Callable[[], dict[str, object]],
        alerts_summary: Callable[[], dict[str, object]],
        compliance_summary: Callable[[], dict[str, object]],
        order_state_summary: Callable[[], dict[str, object]],
        execution_authorization_summary: Callable[[], dict[str, object]],
        operations_execution_readiness: Callable[..., dict[str, object]],
    ) -> None:
        self._config = config
        self._strategy_signal_provider_getter = strategy_signal_provider_getter
        self._strategy_registry_getter = strategy_registry_getter
        self._strategy_experiment_getter = strategy_experiment_getter
        self._default_execution_strategy_ids_getter = default_execution_strategy_ids_getter
        self._broker_validation = broker_validation
        self._broker_status = broker_status
        self._run_market_data_smoke_test = run_market_data_smoke_test
        self._preview_execution = preview_execution
        self._data_quality_summary = data_quality_summary
        self._operations_rollout = operations_rollout
        self._alerts_summary = alerts_summary
        self._compliance_summary = compliance_summary
        self._order_state_summary = order_state_summary
        self._execution_authorization_summary = execution_authorization_summary
        self._operations_execution_readiness = operations_execution_readiness

    def base_validation_snapshot(self, as_of: date, *, preflight: dict[str, object] | None = None) -> dict[str, object]:
        preflight_payload = preflight or self.startup_preflight_summary(as_of)
        broker_validation = self._broker_validation()
        market_data = None
        market_data_error = None
        preview = None
        preview_error = None
        try:
            market_data = self._run_market_data_smoke_test(symbols=self._config.smoke_symbols or None)
        except Exception as exc:
            logger.exception("Base validation market-data smoke-test failed")
            market_data_error = str(exc)
        try:
            preview = self._preview_execution(as_of)
        except Exception as exc:
            logger.exception("Base validation execution preview failed")
            preview_error = str(exc)
        diagnostics = summarize_validation_diagnostics(
            preflight=preflight_payload,
            broker_validation=broker_validation,
            market_data=market_data,
            execution_preview=preview,
            market_data_error=market_data_error,
            execution_preview_error=preview_error,
        )
        return {
            "preflight": preflight_payload,
            "broker_validation": broker_validation,
            "market_data": market_data,
            "preview": preview,
            "diagnostics": diagnostics,
        }

    def research_readiness_summary(self, evaluation_date: date) -> dict[str, object]:
        strategy_ids = self._default_execution_strategy_ids_getter()
        signal_map = self._strategy_signal_provider_getter().strategy_signal_map(
            evaluation_date,
            strategy_ids=strategy_ids,
            local_history_only=True,
        )
        registry = self._strategy_registry_getter()
        experiment_service = self._strategy_experiment_getter()
        strategies = [
            experiment_service.inspect_strategy_readiness(
                strategy_id,
                evaluation_date,
                signal_list,
                strategy=registry.get(strategy_id),
            )
            for strategy_id, signal_list in signal_map.items()
        ]
        blocked_strategy_ids = [item["strategy_id"] for item in strategies if bool(item.get("promotion_blocked"))]
        ready_strategy_ids = [item["strategy_id"] for item in strategies if bool(item.get("data_ready"))]
        blocking_reasons: list[str] = []
        for item in strategies:
            if not bool(item.get("promotion_blocked")):
                continue
            strategy_id = str(item.get("strategy_id", "unknown_strategy"))
            for reason in item.get("blocking_reasons", []):
                blocking_reasons.append(f"{strategy_id}: {reason}")
        minimum_history_coverage_ratio = round(
            min((float(item.get("minimum_coverage_ratio", 1.0)) for item in strategies), default=1.0),
            4,
        )
        report_status = "blocked" if blocked_strategy_ids else "ready"
        return {
            "as_of": evaluation_date,
            "ready": not bool(blocked_strategy_ids),
            "report_status": report_status,
            "blocked_count": len(blocked_strategy_ids),
            "blocked_strategy_ids": blocked_strategy_ids,
            "ready_strategy_ids": ready_strategy_ids,
            "blocking_reasons": list(dict.fromkeys(blocking_reasons)),
            "minimum_history_coverage_ratio": minimum_history_coverage_ratio,
            "strategies": strategies,
        }

    def startup_preflight_summary(
        self,
        evaluation_date: date,
        *,
        research_readiness: dict[str, object] | None = None,
    ) -> dict[str, object]:
        preflight = build_startup_preflight(self._config)
        readiness = research_readiness or self.research_readiness_summary(evaluation_date)
        return {
            **preflight,
            "research_ready": readiness["ready"],
            "research_blockers": list(readiness.get("blocking_reasons", [])),
            "research_readiness": readiness,
            "system_ready": bool(preflight.get("healthy", False)) and bool(readiness["ready"]),
        }

    def execution_gate_summary(self, evaluation_date: date, *, validation: dict[str, object] | None = None) -> dict[str, object]:
        validation_payload = validation or self.base_validation_snapshot(evaluation_date)
        diagnostics = validation_payload["diagnostics"]
        research_readiness = validation_payload["preflight"].get("research_readiness", {})
        rollout = self._operations_rollout()
        execution_readiness = self._operations_execution_readiness(
            state_counts=self._order_state_summary(),
            authorization=self._execution_authorization_summary(),
            alerts_summary=self._alerts_summary(),
        )
        reasons = list(diagnostics["findings"])
        reasons.extend(str(item) for item in research_readiness.get("blocking_reasons", []))
        reasons.extend(execution_readiness["blockers"])
        if not rollout["ready_for_rollout"]:
            reasons.extend(blocker for blocker in rollout["blockers"])
        reasons = list(dict.fromkeys(str(reason) for reason in reasons))
        ready = (
            bool(diagnostics["ready"])
            and bool(research_readiness.get("ready", True))
            and rollout["ready_for_rollout"]
            and execution_readiness["ready"]
        )
        return {
            "as_of": evaluation_date,
            "ready": ready,
            "should_block": not ready,
            "reasons": reasons,
            "next_actions": list(diagnostics["next_actions"]),
            "recommended_stage": rollout["current_recommendation"],
            "preflight": validation_payload["preflight"],
            "broker_validation": validation_payload["broker_validation"],
            "market_data": validation_payload["market_data"],
            "diagnostics": diagnostics,
            "execution": execution_readiness,
        }

    def operations_readiness(
        self,
        *,
        evaluation_date: date | None = None,
        validation: dict[str, object] | None = None,
        data_quality: dict[str, object] | None = None,
    ) -> dict[str, object]:
        as_of = evaluation_date or date.today()
        validation_payload = validation or self.base_validation_snapshot(as_of)
        broker_status = self._broker_status()
        data_quality_payload = data_quality or self._data_quality_summary()
        research_readiness = validation_payload["preflight"].get("research_readiness", {})
        alerts_summary = self._alerts_summary()
        compliance_summary = self._compliance_summary()
        compliance_counts = self.compliance_counts(compliance_summary)
        diagnostics = validation_payload["diagnostics"]
        execution_readiness = self._operations_execution_readiness(
            state_counts=self._order_state_summary(),
            authorization=self._execution_authorization_summary(),
            alerts_summary=alerts_summary,
        )
        blockers = list(diagnostics.get("findings", []))
        blockers.extend(str(item) for item in research_readiness.get("blocking_reasons", []))
        blockers.extend(data_quality_payload.get("blockers", []))
        blockers.extend(execution_readiness["blockers"])
        blockers = list(dict.fromkeys(str(blocker) for blocker in blockers))
        ready = (
            bool(diagnostics["ready"])
            and bool(research_readiness.get("ready", True))
            and bool(data_quality_payload.get("ready", True))
            and compliance_counts["blocked_count"] == 0
            and execution_readiness["ready"]
        )
        latest_dir = latest_report_dir(self._config.data_dir)
        return {
            "ready": ready,
            "blockers": blockers,
            "diagnostics": diagnostics,
            "preflight": validation_payload["preflight"],
            "broker_status": broker_status,
            "broker_validation": validation_payload["broker_validation"],
            "research_readiness": research_readiness,
            "data_quality": data_quality_payload,
            "execution": execution_readiness,
            "alerts": alerts_summary,
            "compliance": {**compliance_summary, **compliance_counts},
            "latest_report_dir": str(latest_dir) if latest_dir else None,
        }

    def compliance_counts(self, summary: dict[str, object]) -> dict[str, int]:
        pending = 0
        blocked = 0
        for checklist in summary.get("checklists", []):
            if not isinstance(checklist, dict):
                continue
            counts = checklist.get("counts", {})
            if isinstance(counts, dict):
                pending += int(counts.get("pending", 0))
                blocked += int(counts.get("blocked", 0))
        return {"pending_count": pending, "blocked_count": blocked}


class ResearchQueryService:
    def __init__(
        self,
        *,
        market_awareness_getter: Callable[[], Any],
        strategy_signal_provider_getter: Callable[[], Any],
        strategy_analysis_getter: Callable[[], Any],
        strategy_registry_getter: Callable[[], Any],
        research_getter: Callable[[], Any],
        default_execution_strategy_ids_getter: Callable[[], list[str]],
        review_strategy_selections: Callable[[date], dict[str, object]],
        review_strategy_allocations: Callable[[date], dict[str, object]],
        sentiment_history_getter: Callable[[], Any] | None = None,
    ) -> None:
        self._market_awareness_getter = market_awareness_getter
        self._strategy_signal_provider_getter = strategy_signal_provider_getter
        self._strategy_analysis_getter = strategy_analysis_getter
        self._strategy_registry_getter = strategy_registry_getter
        self._research_getter = research_getter
        self._default_execution_strategy_ids_getter = default_execution_strategy_ids_getter
        self._review_strategy_selections = review_strategy_selections
        self._review_strategy_allocations = review_strategy_allocations
        self._sentiment_history_getter = sentiment_history_getter

    def scorecard(self, as_of: date, *, include_candidates: bool) -> dict[str, object]:
        return self._strategy_analysis_getter().build_profit_scorecard(
            as_of,
            self._strategy_signal_map(as_of, include_candidates=include_candidates, local_history_only=True),
        )

    def report(self, as_of: date) -> dict[str, object]:
        return self._strategy_analysis_getter().summarize_strategy_report(
            as_of,
            self._strategy_signal_map(as_of, local_history_only=True),
        )

    def stability(self, as_of: date) -> dict[str, object]:
        return self._strategy_analysis_getter().summarize_strategy_stability(
            as_of,
            self._strategy_signal_map(as_of, local_history_only=True),
        )

    def recommendations(self, as_of: date) -> dict[str, object]:
        return self._strategy_analysis_getter().recommend_strategy_actions(
            as_of,
            self._strategy_signal_map(as_of, include_candidates=True, local_history_only=True),
        )

    def ideas(self, as_of: date) -> dict[str, object]:
        return self._research_getter().suggest_experiments(
            as_of,
            self._strategy_signal_map(as_of, local_history_only=True),
        )

    def run_backtests(self, as_of: date) -> dict[str, object]:
        experiments = []
        research = self._research_getter()
        for strategy in self._strategy_registry_getter().all():
            experiments.append(
                research.run_experiment(
                    strategy.strategy_id,
                    as_of,
                    strategy.generate_signals(as_of),
                )
            )
        return {"count": len(experiments), "experiments": experiments}

    def strategy_detail(self, strategy_id: str, as_of: date) -> dict[str, object]:
        return self._strategy_analysis_getter().strategy_detail(
            strategy_id,
            as_of,
            self._strategy_signal_map(as_of, strategy_ids=[strategy_id], local_history_only=True).get(strategy_id, []),
        )

    async def asset_correlation(self, symbols: list[str], days: int) -> dict[str, object]:
        end = date.today()
        start = end - timedelta(days=days)
        return await self._strategy_analysis_getter().calculate_asset_correlation_async(symbols, start, end)

    def review_selections(self, as_of: date) -> dict[str, object]:
        return self._review_strategy_selections(as_of)

    def review_allocations(self, as_of: date) -> dict[str, object]:
        return self._review_strategy_allocations(as_of)

    def market_awareness(self, as_of: date) -> dict[str, object]:
        result = _safe_market_awareness_snapshot(self._market_awareness_getter, as_of)
        # Enrich with sparkline history if available.
        if self._sentiment_history_getter is not None:
            try:
                history_repo = self._sentiment_history_getter()
                if history_repo is not None and history_repo.available:
                    raw_history = history_repo.load_history(days=30)
                    # Group by indicator_key for sparkline rendering.
                    by_key: dict[str, list[dict]] = {}
                    for row in raw_history:
                        key = row.get("indicator_key", "")
                        if key:
                            by_key.setdefault(key, []).append({
                                "ts": row.get("ts", ""),
                                "value": row.get("value"),
                                "score": row.get("score", 0.0),
                            })
                    sentiment = result.get("market_sentiment")
                    if isinstance(sentiment, dict):
                        sentiment["history"] = by_key
            except Exception:  # noqa: BLE001
                logger.debug("sentiment history enrichment failed", exc_info=True)
        return result

    def _strategy_signal_map(
        self,
        as_of: date,
        *,
        include_candidates: bool = False,
        strategy_ids: list[str] | None = None,
        local_history_only: bool = False,
    ) -> dict[str, object]:
        resolved_strategy_ids = strategy_ids
        if resolved_strategy_ids is None and not include_candidates:
            resolved_strategy_ids = self._default_execution_strategy_ids_getter()
        return self._strategy_signal_provider_getter().strategy_signal_map(
            as_of,
            strategy_ids=resolved_strategy_ids,
            local_history_only=local_history_only,
        )


class DashboardQueryService:
    def __init__(
        self,
        *,
        market_awareness_getter: Callable[[], Any],
        execution_gate_summary: Callable[[date], dict[str, object]],
        operations_period_report: Callable[[int, str], dict[str, object]],
        live_acceptance_summary: Callable[[date], dict[str, object]],
        operations_rollout: Callable[[], dict[str, object]],
        operations_readiness: Callable[[], dict[str, object]],
        data_quality_summary: Callable[[], dict[str, object]],
        active_execution_strategy_ids_getter: Callable[[], list[str]],
        selection_summary: Callable[[], dict[str, object]],
        allocation_summary: Callable[[], dict[str, object]],
        dashboard_snapshot_getter: Callable[[date], dict[str, object]],
        list_orders: Callable[[], list[object]],
        resolve_intent_context: Callable[[str | None], dict[str, object] | None],
        resolve_price_context: Callable[[str | None], dict[str, object]],
    ) -> None:
        self._market_awareness_getter = market_awareness_getter
        self._execution_gate_summary = execution_gate_summary
        self._operations_period_report = operations_period_report
        self._live_acceptance_summary = live_acceptance_summary
        self._operations_rollout = operations_rollout
        self._operations_readiness = operations_readiness
        self._data_quality_summary = data_quality_summary
        self._active_execution_strategy_ids_getter = active_execution_strategy_ids_getter
        self._selection_summary = selection_summary
        self._allocation_summary = allocation_summary
        self._dashboard_snapshot_getter = dashboard_snapshot_getter
        self._list_orders = list_orders
        self._resolve_intent_context = resolve_intent_context
        self._resolve_price_context = resolve_price_context

    def summary_context(self, evaluation_date: date) -> dict[str, object]:
        return {
            "gate": self._execution_gate_summary(evaluation_date),
            "daily_report": self._operations_period_report(1, "daily"),
            "weekly_report": self._operations_period_report(7, "weekly"),
            "live_acceptance": self._live_acceptance_summary(evaluation_date),
            "rollout": self._operations_rollout(),
            "operations": self._operations_readiness(),
            "data_quality": self._data_quality_summary(),
            "recent_orders": self.recent_orders(),
            "candidate_scorecard": self._dashboard_snapshot_getter(evaluation_date),
            "active_strategy_ids": self._active_execution_strategy_ids_getter(),
            "selection_summary": self._selection_summary(),
            "allocation_summary": self._allocation_summary(),
            "market_awareness": _safe_market_awareness_snapshot(self._market_awareness_getter, evaluation_date),
        }

    def recent_orders(self, limit: int = 20) -> list[dict[str, object]]:
        orders = sorted(self._list_orders(), key=lambda item: item.timestamp, reverse=True)[:limit]
        rows: list[dict[str, object]] = []
        for order in orders:
            context = self._resolve_intent_context(order.order_intent_id) or {}
            price_context = self._resolve_price_context(order.order_intent_id)
            rows.append(
                {
                    **order.model_dump(mode="json"),
                    "symbol": context.get("symbol"),
                    "market": context.get("market"),
                    "asset_class": context.get("asset_class"),
                    "strategy_id": context.get("strategy_id"),
                    "expected_price": price_context.get("expected_price"),
                    "realized_price": price_context.get("realized_price"),
                    "reference_source": price_context.get("reference_source"),
                }
            )
        return rows

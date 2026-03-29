from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, timedelta
from typing import Any

from tradingcat.config import AppConfig
from tradingcat.services.preflight import build_startup_preflight, summarize_validation_diagnostics
from tradingcat.services.reporting import latest_report_dir


logger = logging.getLogger(__name__)


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
        strategy_analysis_getter: Callable[[], Any],
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
        self._strategy_analysis_getter = strategy_analysis_getter
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

    def base_validation_snapshot(self, as_of: date) -> dict[str, object]:
        preflight = self.startup_preflight_summary(as_of)
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
            preflight=preflight,
            broker_validation=broker_validation,
            market_data=market_data,
            execution_preview=preview,
            market_data_error=market_data_error,
            execution_preview_error=preview_error,
        )
        return {
            "preflight": preflight,
            "broker_validation": broker_validation,
            "market_data": market_data,
            "preview": preview,
            "diagnostics": diagnostics,
        }

    def research_readiness_summary(self, evaluation_date: date) -> dict[str, object]:
        report = self._strategy_analysis_getter().summarize_strategy_report(
            evaluation_date,
            self._strategy_signal_provider_getter().strategy_signal_map(evaluation_date),
        )
        strategies = [
            {
                "strategy_id": item["strategy_id"],
                "validation_status": item["validation_status"],
                "data_source": item["data_source"],
                "data_ready": item["data_ready"],
                "promotion_blocked": item["promotion_blocked"],
                "blocking_reasons": item["blocking_reasons"],
            }
            for item in report.get("strategy_reports", [])
        ]
        return {
            "as_of": evaluation_date,
            "ready": not bool(report.get("hard_blocked", False)),
            "report_status": report.get("report_status", "review"),
            "blocked_count": report.get("blocked_count", 0),
            "blocked_strategy_ids": list(report.get("blocked_strategy_ids", [])),
            "ready_strategy_ids": list(report.get("ready_strategy_ids", [])),
            "blocking_reasons": list(report.get("blocking_reasons", [])),
            "minimum_history_coverage_ratio": report.get("minimum_history_coverage_ratio", 1.0),
            "strategies": strategies,
        }

    def startup_preflight_summary(self, evaluation_date: date) -> dict[str, object]:
        preflight = build_startup_preflight(self._config)
        research_readiness = self.research_readiness_summary(evaluation_date)
        return {
            **preflight,
            "research_ready": research_readiness["ready"],
            "research_blockers": list(research_readiness.get("blocking_reasons", [])),
            "research_readiness": research_readiness,
            "system_ready": bool(preflight.get("healthy", False)) and bool(research_readiness["ready"]),
        }

    def execution_gate_summary(self, evaluation_date: date) -> dict[str, object]:
        validation = self.base_validation_snapshot(evaluation_date)
        diagnostics = validation["diagnostics"]
        research_readiness = validation["preflight"].get("research_readiness", {})
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
            "preflight": validation["preflight"],
            "broker_validation": validation["broker_validation"],
            "market_data": validation["market_data"],
            "diagnostics": diagnostics,
            "execution": execution_readiness,
        }

    def operations_readiness(self) -> dict[str, object]:
        evaluation_date = date.today()
        validation = self.base_validation_snapshot(evaluation_date)
        broker_status = self._broker_status()
        data_quality = self._data_quality_summary()
        research_readiness = validation["preflight"].get("research_readiness", {})
        alerts_summary = self._alerts_summary()
        compliance_summary = self._compliance_summary()
        compliance_counts = self.compliance_counts(compliance_summary)
        diagnostics = validation["diagnostics"]
        execution_readiness = self._operations_execution_readiness(
            state_counts=self._order_state_summary(),
            authorization=self._execution_authorization_summary(),
            alerts_summary=alerts_summary,
        )
        blockers = list(diagnostics.get("findings", []))
        blockers.extend(str(item) for item in research_readiness.get("blocking_reasons", []))
        blockers.extend(data_quality.get("blockers", []))
        blockers.extend(execution_readiness["blockers"])
        blockers = list(dict.fromkeys(str(blocker) for blocker in blockers))
        ready = (
            bool(diagnostics["ready"])
            and bool(research_readiness.get("ready", True))
            and bool(data_quality.get("ready", True))
            and compliance_counts["blocked_count"] == 0
            and execution_readiness["ready"]
        )
        latest_dir = latest_report_dir(self._config.data_dir)
        return {
            "ready": ready,
            "blockers": blockers,
            "diagnostics": diagnostics,
            "preflight": validation["preflight"],
            "broker_status": broker_status,
            "broker_validation": validation["broker_validation"],
            "research_readiness": research_readiness,
            "data_quality": data_quality,
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

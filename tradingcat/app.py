from __future__ import annotations

import csv
import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from io import StringIO

from fastapi import FastAPI

from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.market import sample_instruments
from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    AlgoExecution,
    AssetClass,
    DailyTradingPlanNote,
    DailyTradingSummaryNote,
    Instrument,
    ManualFill,
    Market,
    OrderIntent,
    OrderSide,
    PortfolioSnapshot,
    Signal,
)
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.repositories.state import (
    AlertRepository,
    ApprovalRepository,
    AuditLogRepository,
    ComplianceRepository,
    DailyTradingPlanRepository,
    DailyTradingSummaryRepository,
    ExecutionStateRepository,
    HistorySyncRunRepository,
    KillSwitchRepository,
    OperationsJournalRepository,
    OrderRepository,
    PortfolioHistoryRepository,
    PortfolioRepository,
    RecoveryAttemptRepository,
    RolloutPolicyRepository,
    RolloutPromotionRepository,
    StrategyAllocationRepository,
    StrategySelectionRepository,
)
from tradingcat.services.alerts import AlertService
from tradingcat.services.allocation import StrategyAllocationService
from tradingcat.services.alpha_radar import AlphaRadarService
from tradingcat.services.approval import ApprovalService
from tradingcat.services.audit import AuditService
from tradingcat.services.compliance import ComplianceService
from tradingcat.services.data_sync import HistorySyncService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.macro_calendar import MacroCalendarService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.operations import OperationsJournalService, RecoveryService
from tradingcat.services.portfolio import PortfolioService
from tradingcat.services.preflight import build_startup_preflight, summarize_validation_diagnostics
from tradingcat.services.reporting import (
    build_incident_replay,
    build_operations_period_report,
    build_postmortem_report,
    filter_recent_items,
    latest_report_dir,
)
from tradingcat.services.research import ResearchService
from tradingcat.services.risk import RiskEngine, RiskViolation
from tradingcat.services.rollout import RolloutPolicyService, RolloutPromotionService
from tradingcat.services.rule_engine import RuleEngine, TriggerRepository
from tradingcat.services.scheduler import SchedulerService
from tradingcat.services.selection import StrategySelectionService
from tradingcat.services.trading_journal import TradingJournalService
from tradingcat.strategies.simple import (
    AllWeatherStrategy,
    DefensiveTrendStrategy,
    EquityMomentumStrategy,
    EtfRotationStrategy,
    Jianfang3LStrategy,
    MeanReversionStrategy,
    OptionHedgeStrategy,
)


logger = logging.getLogger(__name__)


class TradingCatApplication:
    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.from_env()
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        self.adapter_factory = AdapterFactory(self.config)
        self.market_calendar = MarketCalendarService()
        self.scheduler = SchedulerService(self.market_calendar, backend=self.config.scheduler.backend)

        self.instrument_catalog_repository = InstrumentCatalogRepository(self.config)
        self.market_history_repository = HistoricalMarketDataRepository(self.config)
        self.backtest_repository = BacktestExperimentRepository(self.config)
        self.order_repository = OrderRepository(self.config)
        self.execution_state_repository = ExecutionStateRepository(self.config)

        self.risk = RiskEngine(self.config.risk, kill_switch_repository=KillSwitchRepository(self.config))
        self.audit = AuditService(AuditLogRepository(self.config))
        self.alerts = AlertService(AlertRepository(self.config))
        self.approvals = ApprovalService(ApprovalRepository(self.config), expiry_minutes=self.config.approval_expiry_minutes)
        self.compliance = ComplianceService(ComplianceRepository(self.config))
        self.portfolio = PortfolioService(self.config, PortfolioRepository(self.config), PortfolioHistoryRepository(self.config))
        self.selection = StrategySelectionService(StrategySelectionRepository(self.config))
        self.allocations = StrategyAllocationService(StrategyAllocationRepository(self.config))
        self.history_sync = HistorySyncService(HistorySyncRunRepository(self.config))
        self.operations = OperationsJournalService(OperationsJournalRepository(self.config))
        self.recovery = RecoveryService(RecoveryAttemptRepository(self.config))
        self.rollout_policy = RolloutPolicyService(RolloutPolicyRepository(self.config))
        self.rollout_promotions = RolloutPromotionService(RolloutPromotionRepository(self.config))
        self.trading_journal = TradingJournalService(
            DailyTradingPlanRepository(self.config),
            DailyTradingSummaryRepository(self.config),
        )

        self._market_data_adapter = None
        self._live_broker = None
        self._manual_broker = None
        self.market_history: MarketDataService
        self.execution: ExecutionService
        self.research: ResearchService
        self.strategy_analysis = None
        self.research_ideas = None
        self.alpha_radar: AlphaRadarService
        self.rule_engine: RuleEngine
        self.macro_calendar: MacroCalendarService

        self._build_runtime_components()
        self._register_jobs()

    @property
    def research_strategies(self) -> list[object]:
        return [
            EtfRotationStrategy(),
            EquityMomentumStrategy(),
            OptionHedgeStrategy(),
            MeanReversionStrategy(),
            DefensiveTrendStrategy(),
            AllWeatherStrategy(),
            Jianfang3LStrategy(),
        ]

    @property
    def _default_execution_strategy_ids(self) -> list[str]:
        return [
            "strategy_a_etf_rotation",
            "strategy_b_equity_momentum",
            "strategy_c_option_overlay",
        ]

    def startup(self) -> None:
        if self.config.seed_demo_data and not self.portfolio.has_history():
            self.portfolio.seed_demo_history()
        if self.config.scheduler.autostart:
            self.scheduler.start()

    def shutdown(self) -> None:
        self.scheduler.stop()

    def reset_state(self) -> None:
        self.execution.clear()
        self.approvals.clear()
        self.audit.clear()
        self.alerts.clear()
        self.selection.clear()
        self.allocations.clear()
        self.operations.clear()
        self.recovery.clear()
        self.rollout_promotions.clear()
        self.trading_journal.clear()
        self.portfolio.reset()
        self.market_history.reset_cache()
        self.risk.set_kill_switch(False, reason="reset_state")
        self.research.clear()

    def _build_runtime_components(self) -> None:
        self._market_data_adapter = self.adapter_factory.create_market_data_adapter()
        self._live_broker = self.adapter_factory.create_live_broker_adapter()
        self._manual_broker = self.adapter_factory.create_manual_broker_adapter()
        self.market_history = MarketDataService(
            adapter=self._market_data_adapter,
            instruments=self.instrument_catalog_repository,
            history=self.market_history_repository,
        )
        self.execution = ExecutionService(
            live_broker=self._live_broker,
            manual_broker=self._manual_broker,
            approvals=self.approvals,
            repository=self.order_repository,
            state_repository=self.execution_state_repository,
        )
        self.research = ResearchService(repository=self.backtest_repository, market_data=self.market_history)
        self.strategy_analysis = self.research.strategy_analysis
        self.research_ideas = self.research.research_ideas
        self.alpha_radar = AlphaRadarService(self.config, self.market_history)
        self.macro_calendar = MacroCalendarService(self.config)
        self.rule_engine = RuleEngine(self.config, TriggerRepository(self.config), market_data=self.market_history, execution=self.execution)
        self.research.register_strategies(self.research_strategies)

    def recover_runtime(self, trigger: str = "manual") -> dict[str, object]:
        before = self.adapter_factory.broker_diagnostics()
        previous_market_history = self.market_history
        previous_execution = self.execution
        self._build_runtime_components()
        after = self.adapter_factory.broker_diagnostics()
        attempt = self.recovery.record(
            trigger=trigger,
            retries=1,
            before_healthy=bool(before.get("healthy", False)),
            after_healthy=bool(after.get("healthy", False)),
            changed=(self.market_history is not previous_market_history or self.execution is not previous_execution),
            detail=str(after.get("detail", "")),
            before_backend=str(before.get("backend", "unknown")),
            after_backend=str(after.get("backend", "unknown")),
        )
        return {
            "attempted": True,
            "attempt": attempt,
            "before": {
                "broker_status": before,
                "market_history_service": type(previous_market_history).__name__,
                "execution_service": type(previous_execution).__name__,
            },
            "after": {
                "broker_status": after,
                "market_history_service": type(self.market_history).__name__,
                "execution_service": type(self.execution).__name__,
                "live_broker_adapter": type(self._live_broker).__name__,
            },
        }

    def strategy_by_id(self, strategy_id: str):
        for strategy in self.research_strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        raise KeyError(strategy_id)

    def active_execution_strategy_ids(self) -> list[str]:
        explicit = self.explicit_execution_strategy_ids()
        if explicit:
            return explicit
        return list(self._default_execution_strategy_ids)

    def explicit_execution_strategy_ids(self) -> list[str]:
        allocated = self.allocations.active_strategy_ids()
        if allocated:
            return allocated
        selected = self.selection.active_strategy_ids()
        if selected:
            return selected
        return []

    def active_execution_strategies(self) -> list[object]:
        active = set(self.active_execution_strategy_ids())
        return [strategy for strategy in self.research_strategies if strategy.strategy_id in active]

    def _execution_signals_for_strategy(self, strategy, as_of: date) -> list[Signal]:
        return [
            signal
            for signal in strategy.generate_signals(as_of)
            if str(signal.metadata.get("execution_mode", "live")) != "research_only"
        ]

    def _execution_signals_with_fallback(self, as_of: date) -> list[Signal]:
        signals = self.get_signals(as_of)
        if len(signals) >= 3:
            return signals
        fallback_ids = set(self._default_execution_strategy_ids)
        fallback: list[Signal] = []
        for strategy in self.research_strategies:
            if strategy.strategy_id in fallback_ids:
                fallback.extend(self._execution_signals_for_strategy(strategy, as_of))
        return fallback or signals

    def get_signals(self, as_of: date) -> list[Signal]:
        signals: list[Signal] = []
        for strategy in self.active_execution_strategies():
            signals.extend(self._execution_signals_for_strategy(strategy, as_of))
        return signals

    def _strategy_signal_map(self, as_of: date, *, include_candidates: bool = False) -> dict[str, list[Signal]]:
        strategies = self.research_strategies if include_candidates else [
            strategy for strategy in self.research_strategies if strategy.strategy_id in self._default_execution_strategy_ids
        ]
        return {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies}

    def _dedupe_instruments(self, signals: list[Signal]) -> list[Instrument]:
        seen: set[str] = set()
        result: list[Instrument] = []
        for signal in signals:
            key = f"{signal.instrument.market.value}:{signal.instrument.symbol}"
            if key in seen:
                continue
            seen.add(key)
            result.append(signal.instrument)
        return result

    def _load_prices(self, signals: list[Signal]) -> dict[str, float]:
        instruments = self._dedupe_instruments(signals)
        if not instruments:
            return {}
        prices = self.market_history.fetch_quotes(instruments)
        if not prices:
            logger.warning("No live prices available for current execution preview")
        return prices

    def _available_cash_by_market(self) -> dict[Market, float]:
        if hasattr(self._live_broker, "get_cash_by_market"):
            try:
                cash_map = self._live_broker.get_cash_by_market()
                return {Market(key.value if isinstance(key, Market) else key): float(value) for key, value in cash_map.items()}
            except Exception:
                logger.exception("Failed to fetch market-level cash balances")
                return {}
        return {}

    def preview_execution(self, as_of: date) -> dict[str, object]:
        signals = self._execution_signals_with_fallback(as_of)
        prices = self._load_prices(signals)
        snapshot = self.portfolio.current_snapshot()
        intents = self.risk.check(
            signals,
            portfolio_nav=snapshot.nav,
            drawdown=snapshot.drawdown,
            daily_pnl=snapshot.daily_pnl,
            weekly_pnl=snapshot.weekly_pnl,
            prices=prices,
            available_cash=snapshot.cash,
            available_cash_by_market=self._available_cash_by_market(),
        )
        manual_count = sum(1 for intent in intents if intent.requires_approval)
        return {
            "as_of": as_of,
            "signal_count": len(signals),
            "signals": signals,
            "intent_count": len(intents),
            "manual_count": manual_count,
            "prices": prices,
            "order_intents": intents,
        }

    def run_execution_cycle(self, as_of: date, *, enforce_gate: bool = False) -> dict[str, object]:
        gate = self.execution_gate_summary(as_of)
        if enforce_gate and gate["should_block"]:
            return gate
        preview = self.preview_execution(as_of)
        intents = list(preview["order_intents"])
        self.execution.register_expected_prices(intents, dict(preview["prices"]))
        submitted = []
        failed = []
        approval_count = 0
        for intent in intents:
            try:
                submitted.append(self.execution.submit(intent))
                if intent.requires_approval:
                    approval_count += 1
            except Exception as exc:
                logger.exception("Execution cycle submission failed", extra={"order_intent_id": intent.id, "symbol": intent.instrument.symbol})
                failed.append({"order_intent_id": intent.id, "symbol": intent.instrument.symbol, "error": str(exc)})
        return {
            **preview,
            "submitted_orders": submitted,
            "failed_orders": failed,
            "approval_count": approval_count,
            "gate": gate,
        }

    def _instrument_for_order(self, order_intent_id: str) -> tuple[Instrument, OrderSide] | None:
        intent = self.execution._intents.get(order_intent_id)
        if intent is not None:
            return intent.instrument, intent.side
        context = self.execution.resolve_intent_context(order_intent_id)
        if context is None:
            return None
        instrument = Instrument(
            symbol=str(context["symbol"]),
            market=Market(str(context["market"])),
            asset_class=str(context["asset_class"]),
            currency=str(context["currency"]),
        )
        return instrument, OrderSide(str(context.get("side", "buy")))

    def _apply_fill_to_portfolio(self, order_intent_id: str, filled_quantity: float, average_price: float | None, side: OrderSide | None = None):
        resolved = self._instrument_for_order(order_intent_id)
        if resolved is None or average_price is None or average_price <= 0:
            return self.portfolio.current_snapshot()
        instrument, inferred_side = resolved
        return self.portfolio.apply_fill(instrument, side or inferred_side, filled_quantity, average_price)

    def parse_manual_fill_import(self, csv_text: str, delimiter: str = ",") -> list[ManualFill]:
        reader = csv.DictReader(StringIO(csv_text), delimiter=delimiter)
        return [ManualFill.model_validate(row) for row in reader]

    def generate_daily_trading_plan(self, as_of: date, account: str = "total") -> DailyTradingPlanNote:
        try:
            preview = self.preview_execution(as_of)
            gate = self.execution_gate_summary(as_of)
            status = "planned" if not gate["should_block"] else "blocked"
            headline = f"Prepared {preview['intent_count']} order intents across {preview['signal_count']} signals."
            reasons = list(gate["reasons"]) if gate["should_block"] else ["Execution gate is open for the current preview."]
            note = DailyTradingPlanNote(
                as_of=as_of,
                account=account,
                status=status,
                headline=headline,
                reasons=reasons,
                counts={
                    "signal_count": int(preview["signal_count"]),
                    "intent_count": int(preview["intent_count"]),
                    "manual_count": int(preview["manual_count"]),
                },
                metrics={"gate": gate},
                items=[
                    {
                        "strategy_id": intent.signal_id.split(":", 1)[0] if intent.signal_id and ":" in intent.signal_id else intent.signal_id,
                        "symbol": intent.instrument.symbol,
                        "market": intent.instrument.market.value,
                        "side": intent.side.value,
                        "quantity": intent.quantity,
                        "requires_approval": intent.requires_approval,
                    }
                    for intent in preview["order_intents"]
                ],
            )
        except RiskViolation as exc:
            note = DailyTradingPlanNote(
                as_of=as_of,
                account=account,
                status="blocked",
                headline="Execution preview blocked by current risk state.",
                reasons=[str(exc)],
            )
        return self.trading_journal.save_plan(note)

    def generate_daily_trading_summary(self, as_of: date) -> DailyTradingSummaryNote:
        orders = self.execution.list_orders()
        alerts = self.alerts.latest_summary()
        gate = self.execution_gate_summary(as_of)
        note = DailyTradingSummaryNote(
            as_of=as_of,
            headline=f"Tracked {len(orders)} orders with {alerts['count']} recorded alerts.",
            highlights=[
                f"{len(orders)} orders currently exist in local execution state.",
                f"Execution gate ready={gate['ready']} policy_stage={gate['policy_stage']}.",
            ],
            blockers=list(gate["reasons"])[:5],
            next_actions=list(gate["next_actions"])[:5],
            metrics={"order_count": len(orders), "alert_count": alerts["count"], "gate": gate},
        )
        return self.trading_journal.save_summary(note)

    def review_strategy_selections(self, as_of: date) -> dict[str, object]:
        report = self.strategy_analysis.recommend_strategy_actions(as_of, self._strategy_signal_map(as_of, include_candidates=True))
        return self.selection.review(report)

    def review_strategy_allocations(self, as_of: date) -> dict[str, object]:
        report = self.strategy_analysis.recommend_strategy_actions(as_of, self._strategy_signal_map(as_of, include_candidates=True))
        return self.allocations.review(report)

    def data_quality_summary(self, lookback_days: int = 30) -> dict[str, object]:
        as_of = date.today()
        explicit_ids = set(self.explicit_execution_strategy_ids())
        explicit_signals: list[Signal] = []
        for strategy in self.research_strategies:
            if strategy.strategy_id in explicit_ids:
                explicit_signals.extend(self._execution_signals_for_strategy(strategy, as_of))
        target_symbols = sorted({signal.instrument.symbol for signal in explicit_signals})
        if not target_symbols:
            return {"ready": True, "target_symbols": [], "incomplete_count": 0, "reports": []}
        coverage = self.market_history.summarize_history_coverage(symbols=target_symbols, start=as_of - timedelta(days=lookback_days), end=as_of)
        incomplete = [report for report in coverage["reports"] if float(report.get("coverage_ratio", 0.0)) < 0.95]
        return {
            "ready": not incomplete,
            "target_symbols": target_symbols,
            "incomplete_count": len(incomplete),
            "reports": coverage["reports"],
        }

    def broker_status(self) -> dict[str, object]:
        return self.adapter_factory.broker_diagnostics()

    def broker_validation(self) -> dict[str, object]:
        return self.adapter_factory.validate_futu_connection()

    def run_market_data_smoke_test(
        self,
        symbols: list[str] | None = None,
        *,
        include_bars: bool = True,
        include_option_chain: bool = False,
    ) -> dict[str, object]:
        targets = [instrument for instrument in self.market_history.list_instruments() if not symbols or instrument.symbol in symbols]
        if not targets:
            targets = sample_instruments()
        failed_symbols: dict[str, str] = {}
        successful_symbols: list[str] = []
        quotes = self.market_history.fetch_quotes(targets)
        if not quotes:
            return {"successful_symbols": successful_symbols, "failed_symbols": {instrument.symbol: "missing quote" for instrument in targets}, "quotes": quotes}
        for instrument in targets:
            if instrument.symbol not in quotes:
                failed_symbols[instrument.symbol] = "missing quote"
                continue
            if include_bars:
                try:
                    self._market_data_adapter.fetch_bars(instrument, date.today() - timedelta(days=2), date.today())
                except Exception as exc:
                    logger.exception("Market-data smoke-test bar fetch failed", extra={"symbol": instrument.symbol})
                    failed_symbols[instrument.symbol] = str(exc)
                    continue
            successful_symbols.append(instrument.symbol)
        option_chain = []
        if include_option_chain and targets:
            try:
                option_chain = self._market_data_adapter.fetch_option_chain(targets[0].symbol, date.today())
            except Exception as exc:
                logger.exception("Market-data smoke-test option-chain fetch failed", extra={"symbol": targets[0].symbol})
                failed_symbols[f"{targets[0].symbol}:options"] = str(exc)
        return {
            "successful_symbols": successful_symbols,
            "failed_symbols": failed_symbols,
            "quote_count": len(quotes),
            "quotes": quotes,
            "option_chain_count": len(option_chain),
        }

    def sync_market_history(self, *, symbols: list[str] | None = None, start: date | None = None, end: date | None = None, include_corporate_actions: bool = True) -> dict[str, object]:
        sync = self.market_history.sync_history(symbols=symbols, start=start, end=end, include_corporate_actions=include_corporate_actions)
        coverage = self.market_history.summarize_history_coverage(symbols=symbols, start=sync["start"], end=sync["end"])
        run = self.history_sync.record_run(sync_result=sync, coverage_result=coverage, symbols=symbols, include_corporate_actions=include_corporate_actions)
        return {**sync, "coverage": coverage, "run": run}

    def _base_validation_snapshot(self, as_of: date) -> dict[str, object]:
        preflight = build_startup_preflight(self.config)
        broker_validation = self.broker_validation()
        market_data = None
        market_data_error = None
        preview = None
        preview_error = None
        try:
            market_data = self.run_market_data_smoke_test(symbols=self.config.smoke_symbols or None)
        except Exception as exc:
            logger.exception("Base validation market-data smoke-test failed")
            market_data_error = str(exc)
        try:
            preview = self.preview_execution(as_of)
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

    def history_sync_repair_plan(self, symbols: list[str] | None = None, start: date | None = None, end: date | None = None) -> dict[str, object]:
        coverage = self.market_history.summarize_history_coverage(symbols=symbols, start=start, end=end)
        return self.history_sync.repair_plan(coverage)

    def repair_market_history_gaps(self, *, symbols: list[str] | None = None, start: date | None = None, end: date | None = None, include_corporate_actions: bool = True) -> dict[str, object]:
        return self.market_history.repair_history_gaps(symbols=symbols, start=start, end=end, include_corporate_actions=include_corporate_actions)

    def _compliance_counts(self, summary: dict[str, object]) -> dict[str, int]:
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

    def execution_gate_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        validation = self._base_validation_snapshot(evaluation_date)
        diagnostics = validation["diagnostics"]
        rollout = self.operations_rollout()
        policy = self.rollout_policy.current()
        reasons = list(diagnostics["findings"])
        if not rollout["ready_for_rollout"]:
            reasons.extend(blocker for blocker in rollout["blockers"])
        return {
            "as_of": evaluation_date,
            "ready": bool(diagnostics["ready"]) and rollout["ready_for_rollout"],
            "should_block": (not bool(diagnostics["ready"])) or (not rollout["ready_for_rollout"]),
            "reasons": reasons,
            "next_actions": list(diagnostics["next_actions"]),
            "policy_stage": policy.stage,
            "recommended_stage": rollout["current_recommendation"],
            "preflight": validation["preflight"],
            "broker_validation": validation["broker_validation"],
            "market_data": validation["market_data"],
            "diagnostics": diagnostics,
        }

    def operations_execution_metrics(self) -> dict[str, object]:
        audit_metrics = self.audit.execution_metrics_summary()
        execution_quality = self.execution.execution_quality_summary()
        authorization = self.execution.authorization_summary()
        return {
            **audit_metrics,
            "filled_samples": execution_quality["filled_samples"],
            "slippage_within_limits": execution_quality["within_limits"],
            "authorization_ok": authorization["all_authorized"],
            "unauthorized_count": authorization["unauthorized_count"],
            "execution_quality": execution_quality,
            "authorization": authorization,
        }

    def operations_readiness(self) -> dict[str, object]:
        validation = self._base_validation_snapshot(date.today())
        broker_status = self.broker_status()
        alerts_summary = self.alerts.latest_summary()
        compliance_summary = self.compliance.summary()
        compliance_counts = self._compliance_counts(compliance_summary)
        diagnostics = validation["diagnostics"]
        ready = bool(diagnostics["ready"]) and alerts_summary["count"] == 0 and compliance_counts["blocked_count"] == 0
        latest_dir = latest_report_dir(self.config.data_dir)
        return {
            "ready": ready,
            "diagnostics": diagnostics,
            "preflight": validation["preflight"],
            "broker_status": broker_status,
            "broker_validation": validation["broker_validation"],
            "alerts": alerts_summary,
            "compliance": {**compliance_summary, **compliance_counts},
            "latest_report_dir": str(latest_dir) if latest_dir else None,
        }

    def operations_rollout(self) -> dict[str, object]:
        return self.operations.rollout_summary(
            readiness=self.operations_readiness(),
            compliance_summary=self.compliance.summary(),
            alerts_summary=self.alerts.latest_summary(),
        )

    def rollout_policy_summary(self) -> dict[str, object]:
        summary = self.rollout_policy.summary()
        summary["policy_matches_recommendation"] = summary["stage"] == self.operations_rollout()["current_recommendation"]
        return summary

    def record_operations_journal(self) -> dict[str, object]:
        entry = self.operations.record(self.operations_readiness())
        return {"entry": entry, "summary": self.operations.summary()}

    def promote_rollout_stage(self, stage: str, reason: str | None = None) -> dict[str, object]:
        rollout = self.operations_rollout()
        policy = self.rollout_policy.current()
        allowed = bool(rollout["ready_for_rollout"]) and stage == rollout["current_recommendation"]
        attempt = self.rollout_promotions.record(
            requested_stage=stage,
            recommended_stage=str(rollout["current_recommendation"]),
            current_stage=policy.stage,
            allowed=allowed,
            reason=reason,
            blocker=rollout["blockers"][0]["detail"] if rollout["blockers"] else None,
        )
        if allowed:
            policy = self.rollout_policy.set_policy(stage, reason=reason or "Promotion approved", source="manual")
        return {"allowed": allowed, "attempt": attempt, "policy": policy, "rollout": rollout}

    def rollout_checklist(self, stage: str | None = None, as_of: date | None = None) -> dict[str, object]:
        rollout = self.operations_rollout()
        target_stage = stage or str(rollout["current_recommendation"])
        blockers = [blocker["detail"] for blocker in rollout["blockers"]]
        return {"stage": target_stage, "ready": not blockers, "as_of": as_of or date.today(), "blockers": blockers}

    def go_live_summary(self, as_of: date | None = None) -> dict[str, object]:
        gate = self.execution_gate_summary(as_of or date.today())
        rollout = self.operations_rollout()
        milestones = self.operations.rollout_milestones()
        policy = self.rollout_policy_summary()
        return {
            "as_of": gate["as_of"],
            "promotion_allowed": bool(gate["ready"]) and bool(rollout["ready_for_rollout"]),
            "gate": gate,
            "rollout": rollout,
            "milestones": milestones,
            "policy": policy,
            "promotion_history": self.rollout_promotions.summary(),
        }

    def live_acceptance_summary(self, as_of: date | None = None, incident_window_days: int = 14) -> dict[str, object]:
        go_live = self.go_live_summary(as_of)
        metrics = self.operations_execution_metrics()
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=incident_window_days)
        blockers = []
        if not go_live["promotion_allowed"]:
            blockers.append("Go-live promotion is currently blocked.")
        auth_ok = metrics.get("authorization_ok", False)
        slip_ok = metrics.get("slippage_within_limits", False)
        if not auth_ok:
            blockers.append("Execution authorization summary is not clean.")
        if not slip_ok:
            blockers.append("Execution quality is outside the configured thresholds.")
        return {
            "as_of": as_of or date.today(),
            "ready_for_live": not blockers,
            "incident_count": len(alerts),
            "blockers": blockers,
            "go_live": go_live,
            "authorization_ok": auth_ok,
            "slippage_within_limits": slip_ok,
        }

    def operations_period_report(self, window_days: int, label: str) -> dict[str, object]:
        readiness = self.operations_readiness()
        execution_metrics = self.operations_execution_metrics()
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days)
        audit_events = filter_recent_items(self.audit.list_events(limit=500), timestamp_attr="created_at", window_days=window_days)
        recoveries = filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days)
        journal_entries = filter_recent_items(self.operations.list_entries(), timestamp_attr="recorded_at", window_days=window_days)
        return build_operations_period_report(
            label=label,
            window_days=window_days,
            readiness=readiness,
            acceptance=self.operations.acceptance_summary(),
            rollout=self.operations_rollout(),
            execution_metrics=execution_metrics,
            audit_events=audit_events,
            alerts=alerts,
            recoveries=recoveries,
            journal_entries=journal_entries,
        )

    def operations_postmortem(self, window_days: int = 7) -> dict[str, object]:
        return build_postmortem_report(
            window_days=window_days,
            readiness=self.operations_readiness(),
            execution_metrics=self.operations_execution_metrics(),
            audit_events=filter_recent_items(self.audit.list_events(limit=500), timestamp_attr="created_at", window_days=window_days),
            alerts=filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days),
            recoveries=filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days),
        )

    def incident_replay(self, window_days: int = 7) -> dict[str, object]:
        return build_incident_replay(
            window_days=window_days,
            audit_events=filter_recent_items(self.audit.list_events(limit=500), timestamp_attr="created_at", window_days=window_days),
            alerts=filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days),
            recoveries=filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days),
        )

    def rebalance_plan(self, as_of: date) -> dict[str, object]:
        snapshot = self.portfolio.current_snapshot()
        allocation_summary = self.allocations.summary()
        active_allocations = allocation_summary["active"]
        current_weights = {position.instrument.symbol: round(position.weight, 6) for position in snapshot.positions}
        target_weights: dict[str, float] = {}
        for record in active_allocations:
            strategy = self.strategy_by_id(str(record["strategy_id"]))
            signals = self._execution_signals_for_strategy(strategy, as_of)
            strategy_weight = float(record["target_weight"])
            signal_total = sum(abs(signal.target_weight) for signal in signals) or 1.0
            for signal in signals:
                target_weights[signal.instrument.symbol] = round(
                    target_weights.get(signal.instrument.symbol, 0.0) + strategy_weight * (signal.target_weight / signal_total),
                    6,
                )

        items = []
        for symbol in sorted(set(current_weights) | set(target_weights)):
            current_weight = current_weights.get(symbol, 0.0)
            target_weight = target_weights.get(symbol, 0.0)
            delta = round(target_weight - current_weight, 6)
            if abs(delta) < 0.0001:
                continue
            items.append(
                {
                    "symbol": symbol,
                    "current_weight": current_weight,
                    "target_weight": target_weight,
                    "delta": delta,
                    "estimated_notional": round(abs(delta) * snapshot.nav, 2),
                }
            )
        return {"as_of": as_of, "nav": snapshot.nav, "items": items, "allocation_summary": allocation_summary}

    def _account_keys(self) -> list[str]:
        return ["total", Market.CN.value, Market.HK.value, Market.US.value]

    def _account_positions(self, snapshot, account: str):
        if account == "total":
            return [position.model_dump(mode="json") for position in snapshot.positions]
        return [position.model_dump(mode="json") for position in snapshot.positions if position.instrument.market.value == account]

    def _account_cash_map(self, snapshot) -> dict[str, float]:
        cash_by_market = self._available_cash_by_market()
        return {
            "total": snapshot.cash,
            Market.CN.value: round(cash_by_market.get(Market.CN, 0.0), 4),
            Market.HK.value: round(cash_by_market.get(Market.HK, 0.0), 4),
            Market.US.value: round(cash_by_market.get(Market.US, 0.0), 4),
        }

    def _account_curves(self, limit: int = 90) -> dict[str, list[dict[str, object]]]:
        curves = {key: [] for key in self._account_keys()}
        history = self.portfolio.nav_history(limit=limit)
        if not history:
            return curves
        current_cash_map = self._account_cash_map(history[-1])
        for item in history:
            market_values = {
                Market.CN.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.CN), 4),
                Market.HK.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.HK), 4),
                Market.US.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.US), 4),
            }
            curves["total"].append({"t": item.timestamp.isoformat(), "v": round(item.nav, 4)})
            for market_key in (Market.CN.value, Market.HK.value, Market.US.value):
                curves[market_key].append({"t": item.timestamp.isoformat(), "v": round(market_values[market_key] + current_cash_map.get(market_key, 0.0), 4)})
        return curves

    def dashboard_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        snapshot = self.portfolio.current_snapshot()
        plan = self.trading_journal.latest_plan(as_of=evaluation_date) or self.generate_daily_trading_plan(evaluation_date)
        summary_note = self.trading_journal.latest_summary(as_of=evaluation_date) or self.generate_daily_trading_summary(evaluation_date)
        selection_summary = self.selection.summary()
        allocation_summary = self.allocations.summary()
        candidate_scorecard = self.strategy_analysis.build_profit_scorecard(evaluation_date, self._strategy_signal_map(evaluation_date, include_candidates=True))
        approval_requests = self.approvals.list_requests()
        accounts = {}
        curves = self._account_curves()
        for account in self._account_keys():
            positions = self._account_positions(snapshot, account)
            accounts[account] = {
                "positions": positions,
                "nav_curve": curves.get(account, []),
                "cash": self._account_cash_map(snapshot).get(account, 0.0),
            }
        return {
            "overview": {
                "as_of": evaluation_date,
                "nav": snapshot.nav,
                "cash": snapshot.cash,
                "drawdown": snapshot.drawdown,
                "daily_pnl": snapshot.daily_pnl,
                "weekly_pnl": snapshot.weekly_pnl,
                "position_count": len(snapshot.positions),
                "total_position_value": round(sum(p.market_value for p in snapshot.positions), 4),
                "cash_ratio": round(snapshot.cash / snapshot.nav, 4) if snapshot.nav else None,
            },
            "assets": {
                "position_value": round(sum(p.market_value for p in snapshot.positions), 4),
                "cash": snapshot.cash,
                "positions": [p.model_dump(mode="json") for p in snapshot.positions],
            },
            "accounts": accounts,
            "strategies": {
                "selection": selection_summary,
                "allocations": allocation_summary,
                "rows": selection_summary.get("rows", []),
                "next_actions": selection_summary.get("next_actions", []),
                "active_count": selection_summary.get("active_count", 0),
            },
            "candidates": {
                "rows": candidate_scorecard["rows"],
                "top_candidates": candidate_scorecard["rows"][:5],
                "deploy_candidate_count": sum(1 for row in candidate_scorecard["rows"] if row.get("verdict") == "deploy_candidate"),
                "paper_only_count": sum(1 for row in candidate_scorecard["rows"] if row.get("verdict") == "paper_only"),
                "rejected_count": sum(1 for row in candidate_scorecard["rows"] if row.get("verdict") == "reject"),
                "next_actions": candidate_scorecard.get("next_actions", []),
            },
            "trading_plan": {
                "status": plan.status,
                "headline": plan.headline,
                "reasons": plan.reasons,
                "counts": plan.counts,
                "items": plan.items,
                "signal_count": plan.counts.get("signal_count", 0),
                "intent_count": plan.counts.get("intent_count", 0),
                "manual_count": plan.counts.get("manual_count", 0),
                "pending_approvals": [request.model_dump(mode="json") for request in approval_requests if request.status.value == "pending"],
                "recent_approvals": [request.model_dump(mode="json") for request in approval_requests[:5]],
            },
            "journal": {
                "recent_plans": [note.model_dump(mode="json") for note in self.trading_journal.list_plans()[:7]],
                "recent_summaries": [note.model_dump(mode="json") for note in self.trading_journal.list_summaries()[:7]],
            },
            "summaries": {"plan": plan, "summary": summary_note},
            "details": {
                "execution_gate": self.execution_gate_summary(evaluation_date),
                "data_quality": self.data_quality_summary(),
                "operations": self.operations_readiness(),
            },
        }

    def submit_manual_order(
        self,
        *,
        symbol: str,
        side: str,
        market: str,
        quantity: float,
        emotional_tag: str | None = None,
        algo_strategy: str | None = None,
        algo_levels: int | None = None,
        algo_price_start: float | None = None,
        algo_price_end: float | None = None,
    ) -> dict[str, object]:
        snapshot = self.portfolio.current_snapshot()
        instrument = Instrument(symbol=symbol.upper(), market=Market(market), asset_class=AssetClass.STOCK)
        price = self.market_history.fetch_quotes([instrument]).get(instrument.symbol)
        if price is None or price <= 0:
            fallback_signal = Signal(
                strategy_id="manual_trader",
                generated_at=datetime.now(UTC),
                instrument=instrument,
                side=OrderSide(side),
                target_weight=0.0,
            )
            price = self.risk._fallback_reference_price(fallback_signal)
        implicit_weight = (quantity * price) / snapshot.nav if snapshot.nav > 0 else 0.0
        signal = Signal(
            strategy_id="manual_trader",
            generated_at=datetime.now(UTC),
            instrument=instrument,
            side=OrderSide(side),
            target_weight=implicit_weight,
            reason=emotional_tag or "Manual Quick Trade",
        )
        self.risk.check(
            [signal],
            portfolio_nav=snapshot.nav,
            drawdown=snapshot.drawdown,
            daily_pnl=snapshot.daily_pnl,
            weekly_pnl=snapshot.weekly_pnl,
            prices={instrument.symbol: price},
            available_cash=snapshot.cash,
            available_cash_by_market=self._available_cash_by_market(),
        )
        algo = None
        if algo_strategy and algo_strategy != "NONE":
            algo = AlgoExecution(strategy=algo_strategy, levels=algo_levels, price_start=algo_price_start, price_end=algo_price_end)
        requires_approval = instrument.market == Market.CN or self.config.manual_order_requires_approval
        intent = OrderIntent(
            signal_id=signal.id,
            instrument=instrument,
            side=signal.side,
            quantity=quantity,
            requires_approval=requires_approval,
            algo=algo,
            notes=emotional_tag,
        )
        self.execution.register_expected_prices([intent], {instrument.symbol: price})
        report = self.execution.submit(intent)
        report.emotional_tag = emotional_tag
        self.execution._orders[intent.id] = report
        self.execution._save_state()
        self.audit.log(
            category="execution",
            action="manual_order_submitted",
            status="warning" if requires_approval else "ok",
            details={
                "symbol": instrument.symbol,
                "quantity": quantity,
                "broker_order_id": report.broker_order_id,
                "emotional_tag": emotional_tag,
                "requires_approval": requires_approval,
                "strategy": algo_strategy or "DIRECT",
            },
        )
        return {"message": "Manual order submitted", "report": report}

    def set_kill_switch(self, enabled: bool = True, reason: str | None = None):
        event = self.risk.set_kill_switch(enabled, reason=reason)
        self.audit.log(category="risk", action="kill_switch_set", status="warning", details={"enabled": enabled, "reason": reason or ""})
        return event

    def expire_stale_approvals(self, reason: str | None = None) -> dict[str, object]:
        requests = self.approvals.expire_stale(timedelta(minutes=self.config.approval_expiry_minutes), reason=reason)
        self.audit.log(category="approval", action="expire_stale", details={"expired_count": len(requests)})
        return {"expired_count": len(requests), "requests": requests}

    def update_risk_config(self, **changes: float) -> dict[str, object]:
        config = self.risk._config
        for key, value in changes.items():
            setattr(config, key, value)
        self.audit.log(category="risk", action="config_update", details=changes)
        return {"status": "ok", "config": config.model_dump(mode="json")}

    def _run_daily_signal_cycle(self) -> str:
        result = self.run_execution_cycle(date.today(), enforce_gate=False)
        if "submitted_orders" not in result:
            return "Execution gate blocked"
        return f"Generated {result['signal_count']} signals and submitted {len(result['submitted_orders'])} orders"

    def _run_market_history_sync_job(self) -> str:
        result = self.sync_market_history(start=date.today() - timedelta(days=7), end=date.today())
        return f"Synced {result['instrument_count']} instruments"

    def _run_market_history_gap_repair_job(self) -> str:
        result = self.repair_market_history_gaps(start=date.today() - timedelta(days=30), end=date.today())
        return f"Repaired {result['repair_count']} symbols"

    def _run_backtests_job(self) -> str:
        experiments = []
        evaluation_date = date.today()
        for strategy in self.research_strategies:
            signals = strategy.generate_signals(evaluation_date)
            experiments.append(self.research.run_experiment(strategy.strategy_id, evaluation_date, signals))
        return f"Ran {len(experiments)} backtests"

    def _run_research_selection_review_job(self) -> str:
        result = self.review_strategy_selections(date.today())
        self.review_strategy_allocations(date.today())
        return f"Updated {len(result['updated'])} strategy selections"

    def _run_portfolio_snapshot_job(self) -> str:
        snapshot = self.portfolio.snapshot()
        return f"Persisted portfolio snapshot: NAV={snapshot.nav:.2f}"

    def _run_broker_auto_recovery_job(self) -> str:
        result = self.recover_runtime(trigger="automatic")
        return str(result["after"]["broker_status"]["detail"])

    def _run_approval_expiry_job(self) -> str:
        expired = self.approvals.expire_stale(timedelta(minutes=self.config.approval_expiry_minutes), reason="Scheduled expiry sweep")
        return f"Expired {len(expired)} approval requests"

    def _run_operations_journal_job(self) -> str:
        self.record_operations_journal()
        return "Recorded operations journal entry"

    def _run_daily_trading_plan_job(self) -> str:
        return self.generate_daily_trading_plan(date.today()).headline

    def _run_daily_trading_summary_job(self) -> str:
        return self.generate_daily_trading_summary(date.today()).headline

    def _register_jobs(self) -> None:
        self.scheduler.register(
            job_id="us_signal_generation",
            name="US Signal Generation",
            description="Generate and risk-check daily US/HK/CN signals",
            timezone="America/New_York",
            local_time=time(8, 45),
            market=Market.US,
            handler=self._run_daily_signal_cycle,
        )
        self.scheduler.register(
            job_id="market_data_history_sync",
            name="Market Data History Sync",
            description="Refresh recent local history coverage for tracked instruments",
            timezone="Asia/Shanghai",
            local_time=time(7, 30),
            market=Market.CN,
            handler=self._run_market_history_sync_job,
        )
        self.scheduler.register(
            job_id="market_data_gap_repair",
            name="Market Data Gap Repair",
            description="Repair missing history windows for tracked instruments",
            timezone="Asia/Shanghai",
            local_time=time(7, 40),
            market=Market.CN,
            handler=self._run_market_history_gap_repair_job,
        )
        self.scheduler.register(
            job_id="research_backtest_refresh",
            name="Research Backtest Refresh",
            description="Run all strategy backtests and persist experiment snapshots",
            timezone="Asia/Shanghai",
            local_time=time(7, 0),
            market=Market.CN,
            handler=self._run_backtests_job,
        )
        self.scheduler.register(
            job_id="research_selection_review",
            name="Research Selection Review",
            description="Refresh persisted strategy admission decisions and target allocations",
            timezone="Asia/Shanghai",
            local_time=time(7, 10),
            market=Market.CN,
            handler=self._run_research_selection_review_job,
        )
        self.scheduler.register(
            job_id="portfolio_risk_snapshot",
            name="Portfolio Risk Snapshot",
            description="Persist current portfolio snapshot for dashboard review",
            timezone="Asia/Shanghai",
            local_time=time(18, 0),
            market=Market.CN,
            handler=self._run_portfolio_snapshot_job,
        )
        self.scheduler.register(
            job_id="broker_auto_recovery",
            name="Broker Auto Recovery",
            description="Attempt runtime rebuild when broker validation degrades",
            timezone="Asia/Shanghai",
            local_time=time(8, 55),
            market=Market.CN,
            handler=self._run_broker_auto_recovery_job,
        )
        self.scheduler.register(
            job_id="approval_expiry_sweep",
            name="Approval Expiry Sweep",
            description="Expire stale manual approval requests",
            timezone="Asia/Shanghai",
            local_time=time(8, 30),
            market=Market.CN,
            handler=self._run_approval_expiry_job,
        )
        self.scheduler.register(
            job_id="operations_readiness_journal",
            name="Operations Readiness Journal",
            description="Persist daily readiness evidence for paper trading acceptance",
            timezone="Asia/Shanghai",
            local_time=time(18, 15),
            market=Market.CN,
            handler=self._run_operations_journal_job,
        )
        self.scheduler.register(
            job_id="daily_trading_plan_archive",
            name="Daily Trading Plan Archive",
            description="Generate and archive the daily trading plan",
            timezone="Asia/Shanghai",
            local_time=time(8, 20),
            market=Market.CN,
            handler=self._run_daily_trading_plan_job,
        )
        self.scheduler.register(
            job_id="daily_trading_summary_archive",
            name="Daily Trading Summary Archive",
            description="Generate and archive the daily trading summary",
            timezone="Asia/Shanghai",
            local_time=time(18, 20),
            market=Market.CN,
            handler=self._run_daily_trading_summary_job,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_state = app.state.app_state
    app_state.startup()
    try:
        yield
    finally:
        app_state.shutdown()

from __future__ import annotations

import csv
import logging
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from io import StringIO
from time import monotonic

from fastapi import FastAPI

from tradingcat.adapters.factory import AdapterFactory
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
    Signal,
)
from tradingcat.facades import AlertsFacade, DashboardFacade, JournalFacade, OperationsFacade, ResearchFacade
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.research import BacktestExperimentRepository, DashboardSnapshotRepository
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
from tradingcat.services.notifier import build_default_dispatcher
from tradingcat.services.allocation import StrategyAllocationService
from tradingcat.services.approval import ApprovalService
from tradingcat.services.audit import AuditService
from tradingcat.services.compliance import ComplianceService
from tradingcat.services.data_sync import HistorySyncService
from tradingcat.services.dashboard_snapshots import DashboardSnapshotService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.operations_analytics import OperationsAnalyticsService
from tradingcat.services.operations import OperationsJournalService, RecoveryService
from tradingcat.services.portfolio import PortfolioService
from tradingcat.services.portfolio_projections import PortfolioProjectionService
from tradingcat.services.query_services import DashboardQueryService, DataQualityQueryService, ReadinessQueryService, ResearchQueryService
from tradingcat.services.reporting import (
    build_incident_replay,
    build_operations_period_report,
    build_postmortem_report,
    filter_recent_items,
)
from tradingcat.services.research import ResearchService
from tradingcat.services.risk import RiskEngine, RiskViolation
from tradingcat.services.rollout import RolloutPolicyService, RolloutPromotionService
from tradingcat.services.rule_engine import RuleEngine
from tradingcat.services.scheduler import SchedulerService
from tradingcat.services.selection import StrategySelectionService
from tradingcat.services.trading_journal import TradingJournalService
from tradingcat.runtime import ApplicationRuntime, ApplicationRuntimeManager
from tradingcat.scheduler_runtime import ApplicationSchedulerRuntime


logger = logging.getLogger(__name__)


class TradingCatApplication:
    # Cache heavy read aggregations briefly so one UI refresh does not recompute
    # the same summary chain several times. A 60s TTL means state transitions may
    # be reflected with a short delay. reset_state() clears the cache explicitly,
    # and daily cache keys rotate naturally because evaluation_date is part of the key.
    _SUMMARY_CACHE_TTL_SECONDS = 60.0

    def __init__(self, config: AppConfig | None = None) -> None:
        self.config = config or AppConfig.from_env()
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        self.adapter_factory = AdapterFactory(self.config)
        self.market_calendar = MarketCalendarService()
        dispatcher = build_default_dispatcher(
            telegram_bot_token=self.config.notifier.telegram_bot_token,
            telegram_chat_id=self.config.notifier.telegram_chat_id,
            smtp_host=self.config.notifier.smtp_host,
            smtp_port=self.config.notifier.smtp_port,
            smtp_username=self.config.notifier.smtp_username,
            smtp_password=self.config.notifier.smtp_password,
            email_from=self.config.notifier.email_from,
            email_to=self.config.notifier.email_to,
            min_severity=self.config.notifier.min_severity,
        )
        self.alerts = AlertService(AlertRepository(self.config), dispatcher=dispatcher)
        self.scheduler = SchedulerService(
            self.market_calendar,
            backend=self.config.scheduler.backend,
            failure_listener=self._record_scheduler_failure_alert,
        )

        self.instrument_catalog_repository = InstrumentCatalogRepository(self.config)
        self.market_history_repository = HistoricalMarketDataRepository(self.config)
        self.backtest_repository = BacktestExperimentRepository(self.config)
        self.dashboard_snapshot_repository = DashboardSnapshotRepository(self.config)
        self.order_repository = OrderRepository(self.config)
        self.execution_state_repository = ExecutionStateRepository(self.config)

        self.risk = RiskEngine(self.config.risk, kill_switch_repository=KillSwitchRepository(self.config))
        self.audit = AuditService(AuditLogRepository(self.config))
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
        self.operations_analytics = OperationsAnalyticsService()

        self.runtime: ApplicationRuntime | None = None
        self._summary_cache: dict[tuple[object, ...], tuple[float, object]] = {}
        self.runtime_manager = ApplicationRuntimeManager(self)
        self.scheduler_runtime = ApplicationSchedulerRuntime(self)
        self.dashboard_facade = DashboardFacade(self)
        self.research_facade = ResearchFacade(self)
        self.operations_facade = OperationsFacade(self)
        self.journal_facade = JournalFacade(self)
        self.alerts_facade = AlertsFacade(self)
        self.portfolio_projections = PortfolioProjectionService(
            available_cash_by_market=self.available_cash_by_market,
            nav_history=self.portfolio.nav_history,
        )
        self.dashboard_snapshot_service = DashboardSnapshotService(
            self.dashboard_snapshot_repository,
            strategy_signal_provider_getter=lambda: self._require_runtime().strategy_signal_provider,
            strategy_analysis_getter=lambda: self.strategy_analysis,
            experiments_getter=lambda: self.research.list_experiments(),
        )
        self.data_quality_queries = DataQualityQueryService(
            config=self.config,
            market_history_getter=lambda: self.market_history,
            strategy_registry_getter=lambda: self._require_runtime().strategy_registry,
            strategy_signal_provider_getter=lambda: self._require_runtime().strategy_signal_provider,
            explicit_execution_strategy_ids_getter=self.explicit_execution_strategy_ids,
        )
        self.readiness_queries = ReadinessQueryService(
            config=self.config,
            strategy_signal_provider_getter=lambda: self._require_runtime().strategy_signal_provider,
            strategy_registry_getter=lambda: self._require_runtime().strategy_registry,
            strategy_experiment_getter=lambda: self.research.experiment_service,
            default_execution_strategy_ids_getter=lambda: list(self._default_execution_strategy_ids),
            broker_validation=self.broker_validation,
            broker_status=self.broker_status,
            run_market_data_smoke_test=self.run_market_data_smoke_test,
            preview_execution=self.preview_execution,
            data_quality_summary=lambda: self.data_quality_summary(),
            operations_rollout=lambda: self.operations_rollout(),
            alerts_summary=lambda: self.alerts.latest_summary(),
            compliance_summary=lambda: self.compliance.summary(),
            order_state_summary=lambda: self.execution.order_state_summary(),
            execution_authorization_summary=lambda: self.execution.authorization_summary(),
            operations_execution_readiness=self.operations_analytics.execution_readiness,
        )
        self.research_queries = ResearchQueryService(
            market_awareness_getter=lambda: self.market_awareness,
            strategy_signal_provider_getter=lambda: self._require_runtime().strategy_signal_provider,
            strategy_analysis_getter=lambda: self.strategy_analysis,
            strategy_registry_getter=lambda: self._require_runtime().strategy_registry,
            research_getter=lambda: self.research,
            default_execution_strategy_ids_getter=lambda: list(self._default_execution_strategy_ids),
            review_strategy_selections=self.review_strategy_selections,
            review_strategy_allocations=self.review_strategy_allocations,
            sentiment_history_getter=lambda: self.sentiment_history,
        )
        self.dashboard_queries = DashboardQueryService(
            market_awareness_getter=lambda: self.market_awareness,
            execution_gate_summary=self.execution_gate_summary,
            operations_period_report=self.operations_period_report,
            live_acceptance_summary=lambda as_of: self.live_acceptance_summary(as_of),
            operations_rollout=self.operations_rollout,
            operations_readiness=self.operations_readiness,
            data_quality_summary=self.data_quality_summary,
            active_execution_strategy_ids_getter=self.active_execution_strategy_ids,
            selection_summary=self.selection.summary,
            allocation_summary=self.allocations.summary,
            dashboard_snapshot_getter=lambda as_of: self.dashboard_snapshot_service.load(as_of),
            list_orders=lambda: self.execution.list_orders(),
            resolve_intent_context=lambda intent_id: self.execution.resolve_intent_context(intent_id),
            resolve_price_context=lambda intent_id: self.execution.resolve_price_context(intent_id),
        )

        self.runtime_manager.initialize()
        self.scheduler_runtime.register_jobs()

    def _require_runtime(self) -> ApplicationRuntime:
        if self.runtime is None:
            raise RuntimeError("Application runtime has not been initialized")
        return self.runtime

    @property
    def _market_data_adapter(self):
        return self._require_runtime().market_data_adapter

    @property
    def _live_broker(self):
        return self._require_runtime().live_broker

    @property
    def _manual_broker(self):
        return self._require_runtime().manual_broker

    @property
    def market_history(self) -> MarketDataService:
        return self._require_runtime().market_history

    @property
    def market_awareness(self):
        return self._require_runtime().market_awareness

    @property
    def market_sentiment(self):
        """Sentiment service mirroring the awareness property shape."""

        return self._require_runtime().market_sentiment

    @property
    def sentiment_history(self):
        """Sentiment history repository for sparkline data."""

        return self._require_runtime().sentiment_history

    @property
    def execution(self) -> ExecutionService:
        return self._require_runtime().execution

    @property
    def research(self) -> ResearchService:
        return self._require_runtime().research

    @property
    def strategy_analysis(self):
        return self._require_runtime().strategy_analysis

    @property
    def strategy_reporting(self):
        return self._require_runtime().strategy_reporting

    @property
    def research_ideas(self):
        return self._require_runtime().research_ideas

    @property
    def alpha_radar(self):
        return self._require_runtime().alpha_radar

    @property
    def macro_calendar(self):
        return self._require_runtime().macro_calendar

    @property
    def rule_engine(self) -> RuleEngine:
        return self._require_runtime().rule_engine

    @property
    def strategy_registry(self):
        return self._require_runtime().strategy_registry

    @property
    def strategy_signal_provider(self):
        return self._require_runtime().strategy_signal_provider

    @property
    def research_strategies(self) -> list[object]:
        return self.strategy_registry.all()

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
        # Release runtime-owned resources (sentiment HTTP pool, etc). The
        # runtime guards each close with a broad except so shutdown never
        # raises — we just need to call it.
        runtime = getattr(self, "runtime", None)
        if runtime is not None and hasattr(runtime, "close"):
            runtime.close()

    def reset_state(self) -> None:
        self._clear_summary_cache()
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
        self.dashboard_snapshot_service.clear()

    def _clear_summary_cache(self) -> None:
        self._summary_cache.clear()

    def _cached_summary(self, cache_key: tuple[object, ...], builder):
        cached = self._summary_cache.get(cache_key)
        now = monotonic()
        if cached is not None and (now - cached[0]) <= self._SUMMARY_CACHE_TTL_SECONDS:
            return cached[1]
        value = builder()
        self._summary_cache[cache_key] = (now, value)
        return value

    def _build_runtime_components(self) -> None:
        self.runtime_manager.initialize()

    def recover_runtime(self, trigger: str = "manual") -> dict[str, object]:
        return self.runtime_manager.recover(trigger)

    def strategy_by_id(self, strategy_id: str):
        try:
            return self.strategy_registry.get(strategy_id)
        except KeyError as exc:
            raise KeyError(strategy_id) from exc

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
        return self.strategy_registry.select(self.active_execution_strategy_ids())

    def _execution_signals_for_strategy(self, strategy, as_of: date) -> list[Signal]:
        return self.strategy_signal_provider.execution_signals_for_strategy(strategy, as_of)

    def _execution_signals_with_fallback(self, as_of: date) -> list[Signal]:
        with self.market_history.local_history_only():
            return self.strategy_signal_provider.execution_signals_with_fallback(
                as_of,
                strategy_ids=self.active_execution_strategy_ids(),
                fallback_strategy_ids=self._default_execution_strategy_ids,
            )

    def get_signals(self, as_of: date) -> list[Signal]:
        return self.strategy_signal_provider.execution_signals(
            as_of,
            strategy_ids=self.active_execution_strategy_ids(),
        )

    def _strategy_signal_map(self, as_of: date, *, include_candidates: bool = False) -> dict[str, list[Signal]]:
        strategy_ids = None if include_candidates else self._default_execution_strategy_ids
        return self.strategy_signal_provider.strategy_signal_map(as_of, strategy_ids=strategy_ids)

    def strategy_signal_map(self, as_of: date, *, include_candidates: bool = False) -> dict[str, list[Signal]]:
        return self._strategy_signal_map(as_of, include_candidates=include_candidates)

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
        prices = self.market_history.fetch_quotes(instruments, fallback_to_synthetic=True)
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

    def available_cash_by_market(self) -> dict[Market, float]:
        return self._available_cash_by_market()

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
        self.execution.register_expected_prices(intents, dict(preview["prices"]), source="execution_preview_quote")
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
        intent = self.execution.get_registered_intent(order_intent_id)
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

    def apply_fill_to_portfolio(self, order_intent_id: str, filled_quantity: float, average_price: float | None, side: OrderSide | None = None):
        return self._apply_fill_to_portfolio(order_intent_id, filled_quantity, average_price, side)

    def parse_manual_fill_import(self, csv_text: str, delimiter: str = ",") -> list[ManualFill]:
        reader = csv.DictReader(StringIO(csv_text), delimiter=delimiter)
        return [ManualFill.model_validate(row) for row in reader]

    def reconcile_portfolio_with_live_broker(self):
        return self.portfolio.reconcile_with_broker(self._live_broker)

    def reconcile_manual_fill(self, fill: ManualFill) -> dict[str, object]:
        before_snapshot = self.portfolio.current_snapshot()
        previous_report = self.execution.get_order(fill.order_intent_id)
        report = self.execution.reconcile_manual_fill(fill)
        snapshot = self.apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price, fill.side)
        reconciliation = self.execution.build_reconciliation_trace(
            order_intent_id=fill.order_intent_id,
            report=report,
            before_snapshot=before_snapshot,
            after_snapshot=snapshot,
            fill_source="manual_fill",
        )
        self.audit.log(
            category="execution",
            action="manual_fill",
            details=self.audit.build_order_details(
                order_intent_id=fill.order_intent_id,
                broker_order_id=report.broker_order_id,
                previous_order_status=previous_report.status.value if previous_report is not None else None,
                order_status=report.status.value,
                authorization_context=reconciliation["authorization"],
                reconciliation_source=str(reconciliation["authorization"].get("external_source") or reconciliation["fill_source"]),
                extra={
                    "symbol": reconciliation["order"]["symbol"],
                    "market": reconciliation["order"]["market"],
                    "portfolio_effect": reconciliation["portfolio_effect"],
                    "pricing": reconciliation["pricing"],
                },
            ),
        )
        return {"status": "ok", "report": report, "snapshot": snapshot, "reconciliation": reconciliation}

    def reconcile_manual_fill_import(self, fills: list[ManualFill]) -> dict[str, object]:
        reports = []
        snapshots = []
        reconciliations = []
        for fill in fills:
            reconciled = self.reconcile_manual_fill(fill)
            reports.append(reconciled["report"])
            snapshot = reconciled["snapshot"]
            snapshots.append({"order_intent_id": fill.order_intent_id, "cash": snapshot.cash, "nav": snapshot.nav})
            reconciliations.append(reconciled["reconciliation"])
        self.audit.log(category="execution", action="manual_fill_import", details={"count": len(fills)})
        return {"count": len(fills), "reports": reports, "snapshots": snapshots, "reconciliations": reconciliations}

    def reconcile_execution_cycle(self) -> dict[str, object]:
        previous_statuses = {
            order.order_intent_id: order.status.value
            for order in self.execution.list_orders()
        }
        summary = self.execution.reconcile_live_state()
        applied_snapshots = []
        reconciliations = []
        for order_id in summary.applied_fill_order_ids:
            report = self.execution.get_order(order_id)
            if report is None or report.average_price is None:
                continue
            before_snapshot = self.portfolio.current_snapshot()
            snapshot = self.apply_fill_to_portfolio(order_id, report.filled_quantity, report.average_price)
            applied_snapshots.append({"order_intent_id": order_id, "nav": snapshot.nav, "cash": snapshot.cash})
            reconciliations.append(
                self.execution.build_reconciliation_trace(
                    order_intent_id=order_id,
                    report=report,
                    before_snapshot=before_snapshot,
                    after_snapshot=snapshot,
                    fill_source="live_reconcile",
                )
            )
            reconciliation = reconciliations[-1]
            self.audit.log(
                category="execution",
                action="live_reconcile",
                details=self.audit.build_order_details(
                    order_intent_id=order_id,
                    broker_order_id=report.broker_order_id,
                    previous_order_status=previous_statuses.get(order_id),
                    order_status=report.status.value,
                    authorization_context=reconciliation["authorization"],
                    reconciliation_source=str(reconciliation["fill_source"]),
                    extra={
                        "symbol": reconciliation["order"]["symbol"],
                        "market": reconciliation["order"]["market"],
                        "portfolio_effect": reconciliation["portfolio_effect"],
                        "pricing": reconciliation["pricing"],
                    },
                ),
            )
        return {"summary": summary, "applied_snapshots": applied_snapshots, "reconciliations": reconciliations}

    def risk_config(self) -> dict[str, object]:
        return self.risk.config_snapshot()

    def _build_plan_items_from_preview(self, preview: dict[str, object]) -> list[dict[str, object]]:
        signals = {
            signal.id: signal
            for signal in preview.get("signals", [])
            if isinstance(signal, Signal)
        }
        prices = {
            str(symbol): float(price)
            for symbol, price in dict(preview.get("prices", {})).items()
        }
        items: list[dict[str, object]] = []
        for intent in preview.get("order_intents", []):
            if not isinstance(intent, OrderIntent):
                continue
            signal = signals.get(intent.signal_id or "")
            strategy_id = signal.strategy_id if signal is not None else (
                intent.signal_id.split(":", 1)[0] if intent.signal_id and ":" in intent.signal_id else (intent.signal_id or "manual_trader")
            )
            items.append(
                {
                    "intent_id": intent.id,
                    "strategy_id": strategy_id,
                    "symbol": intent.instrument.symbol,
                    "market": intent.instrument.market.value,
                    "side": intent.side.value,
                    "quantity": intent.quantity,
                    "target_weight": signal.target_weight if signal is not None else None,
                    "reference_price": prices.get(intent.instrument.symbol),
                    "requires_approval": intent.requires_approval,
                    "reason": intent.notes or (signal.reason if signal is not None else None),
                }
            )
        return items

    @staticmethod
    def _plan_reason_text(reason: object) -> str:
        if isinstance(reason, str):
            return reason
        if isinstance(reason, dict):
            reason_type = str(reason.get("type") or "gate")
            detail = str(reason.get("detail") or "").strip()
            return f"{reason_type}: {detail}" if detail else reason_type
        return str(reason)

    def generate_daily_trading_plan(self, as_of: date, account: str = "total") -> DailyTradingPlanNote:
        try:
            preview = self.preview_execution(as_of)
            gate = self.execution_gate_summary(as_of)
            market_awareness = self.research_queries.market_awareness(as_of)
            participation = market_awareness.get("participation", {}) if isinstance(market_awareness, dict) else {}
            participation_line = (
                f"Participation {participation.get('decision', 'wait')} / "
                f"p={float(participation.get('probability', 0.0)):.2f} / "
                f"odds={float(participation.get('odds', 1.0)):.2f}."
            )
            posture_line = (
                f"Market posture {market_awareness.get('overall_regime', 'unknown')} / "
                f"{market_awareness.get('risk_posture', 'hold_pace')} / "
                f"{market_awareness.get('confidence', 'low')} confidence."
            )
            status = "planned" if not gate["should_block"] else "blocked"
            headline = (
                f"Prepared {preview['intent_count']} order intents across {preview['signal_count']} signals. "
                f"{posture_line} {participation_line}"
            )
            reasons = (
                [self._plan_reason_text(reason) for reason in gate["reasons"]]
                if gate["should_block"]
                else ["Execution gate is open for the current preview."]
            )
            reasons.append(posture_line)
            reasons.append(participation_line)
            reasons.extend(
                f"Market cue: {action.get('text')}"
                for action in list(market_awareness.get("actions", []))[:2]
                if isinstance(action, dict) and action.get("text")
            )
            reasons = list(dict.fromkeys(reason for reason in reasons if reason))
            items = self._build_plan_items_from_preview(preview)
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
                    "automated_count": int(preview["intent_count"]) - int(preview["manual_count"]),
                },
                metrics={"gate": gate, "market_awareness": market_awareness},
                items=items,
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
        report = self.research_queries.recommendations(as_of)
        return self.selection.review(report)

    def review_strategy_allocations(self, as_of: date) -> dict[str, object]:
        report = self.research_queries.recommendations(as_of)
        return self.allocations.review(report)

    def data_quality_summary(self, lookback_days: int = 30) -> dict[str, object]:
        return self.data_quality_queries.data_quality_summary(lookback_days=lookback_days)

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
        targets = self.market_history.diagnostic_targets(symbols)
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
        baseline_applied = not symbols
        requested_symbols = list(symbols or self.history_baseline_symbols(as_of=end or date.today()))
        sync_start = start or (date(2018, 1, 1) if baseline_applied else None)
        sync = self.market_history.sync_history(
            symbols=requested_symbols,
            start=sync_start,
            end=end,
            include_corporate_actions=include_corporate_actions,
        )
        coverage = self.market_history.summarize_history_coverage(symbols=requested_symbols, start=sync["start"], end=sync["end"])
        fx_sync = self.market_history.sync_fx_rates(
            base_currency=self.config.base_currency,
            quote_currencies=self._baseline_quote_currencies(requested_symbols),
            start=sync["start"],
            end=sync["end"],
        )
        run = self.history_sync.record_run(
            sync_result=sync,
            coverage_result=coverage,
            symbols=requested_symbols,
            include_corporate_actions=include_corporate_actions,
        )
        return {
            **sync,
            "coverage": coverage,
            "run": run,
            "baseline_applied": baseline_applied,
            "baseline_symbols": requested_symbols,
            "fx_sync": fx_sync,
        }

    def _base_validation_snapshot(self, as_of: date) -> dict[str, object]:
        return self._cached_summary(
            ("base_validation_snapshot", as_of.isoformat()),
            lambda: self._build_base_validation_snapshot(as_of),
        )

    def _build_base_validation_snapshot(self, as_of: date) -> dict[str, object]:
        return self.readiness_queries.base_validation_snapshot(
            as_of,
            preflight=self.startup_preflight_summary(as_of),
        )

    def research_readiness_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        return self._cached_summary(
            ("research_readiness_summary", evaluation_date.isoformat()),
            lambda: self._build_research_readiness_summary(evaluation_date),
        )

    def _build_research_readiness_summary(self, evaluation_date: date) -> dict[str, object]:
        return self.readiness_queries.research_readiness_summary(evaluation_date)

    def startup_preflight_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        return self._cached_summary(
            ("startup_preflight_summary", evaluation_date.isoformat()),
            lambda: self._build_startup_preflight_summary(evaluation_date),
        )

    def _build_startup_preflight_summary(self, evaluation_date: date) -> dict[str, object]:
        return self.readiness_queries.startup_preflight_summary(
            evaluation_date,
            research_readiness=self.research_readiness_summary(evaluation_date),
        )

    def history_sync_repair_plan(self, symbols: list[str] | None = None, start: date | None = None, end: date | None = None) -> dict[str, object]:
        coverage = self.market_history.summarize_history_coverage(symbols=symbols, start=start, end=end)
        return self.history_sync.repair_plan(coverage, priority_symbols=self._repair_priority_symbols(symbols))

    def repair_market_history_gaps(self, *, symbols: list[str] | None = None, start: date | None = None, end: date | None = None, include_corporate_actions: bool = True) -> dict[str, object]:
        return self.market_history.repair_history_gaps(symbols=symbols, start=start, end=end, include_corporate_actions=include_corporate_actions)

    def _compliance_counts(self, summary: dict[str, object]) -> dict[str, int]:
        return self.readiness_queries.compliance_counts(summary)

    def _repair_priority_symbols(self, symbols: list[str] | None = None, as_of: date | None = None) -> list[str]:
        return self.data_quality_queries.repair_priority_symbols(symbols=symbols, as_of=as_of)

    def history_baseline_symbols(self, *, as_of: date | None = None, limit: int = 5) -> list[str]:
        return self.data_quality_queries.history_baseline_symbols(as_of=as_of, limit=limit)

    def _baseline_quote_currencies(self, symbols: list[str]) -> list[str]:
        return self.data_quality_queries.baseline_quote_currencies(symbols)

    def execution_gate_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        return self._cached_summary(
            ("execution_gate_summary", evaluation_date.isoformat()),
            lambda: self._build_execution_gate_summary(evaluation_date),
        )

    def _build_execution_gate_summary(self, evaluation_date: date) -> dict[str, object]:
        return {
            **self.readiness_queries.execution_gate_summary(
                evaluation_date,
                validation=self._base_validation_snapshot(evaluation_date),
            ),
            "policy_stage": self.rollout_policy.current().stage,
        }

    def operations_execution_metrics(self) -> dict[str, object]:
        audit_metrics = self.audit.execution_metrics_summary()
        execution_quality = self.execution.execution_quality_summary()
        execution_tca = self.execution.transaction_cost_summary()
        authorization = self.execution.authorization_summary()
        return self.operations_analytics.execution_metrics(
            audit_metrics=audit_metrics,
            execution_quality=execution_quality,
            execution_tca=execution_tca,
            authorization=authorization,
        )

    def operations_readiness(self) -> dict[str, object]:
        return self._cached_summary(
            ("operations_readiness", date.today().isoformat()),
            self._build_operations_readiness,
        )

    def _build_operations_readiness(self) -> dict[str, object]:
        evaluation_date = date.today()
        return self.readiness_queries.operations_readiness(
            evaluation_date=evaluation_date,
            validation=self._base_validation_snapshot(evaluation_date),
            data_quality=self.data_quality_summary(),
        )

    def operations_rollout(self) -> dict[str, object]:
        return self._cached_summary(
            ("operations_rollout", date.today().isoformat()),
            lambda: self.operations.rollout_summary(
                readiness=self.operations_readiness(),
                compliance_summary=self.compliance.summary(),
                alerts_summary=self.alerts.latest_summary(),
            ),
        )

    def rollout_policy_summary(self) -> dict[str, object]:
        summary = self.rollout_policy.summary()
        recommended_stage = self.operations_rollout()["current_recommendation"]
        summary["recommended_stage"] = recommended_stage
        summary["policy_matches_recommendation"] = summary["stage"] == recommended_stage
        summary["blocking_reasons"] = (
            []
            if summary["policy_matches_recommendation"]
            else [f"Active rollout policy {summary['stage']} does not match recommended stage {recommended_stage}."]
        )
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
            blocker=str(rollout["blockers"][0]) if rollout["blockers"] else None,
        )
        if allowed:
            policy = self.rollout_policy.set_policy(stage, reason=reason or "Promotion approved", source="manual")
        return {"allowed": allowed, "attempt": attempt, "policy": policy, "rollout": rollout}

    def rollout_checklist(self, stage: str | None = None, as_of: date | None = None) -> dict[str, object]:
        rollout = self.operations_rollout()
        target_stage = stage or str(rollout["current_recommendation"])
        blockers = [str(blocker) for blocker in rollout["blockers"]]
        return {"stage": target_stage, "ready": not blockers, "as_of": as_of or date.today(), "blockers": blockers}

    def go_live_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        return self._cached_summary(
            ("go_live_summary", evaluation_date.isoformat()),
            lambda: self._build_go_live_summary(evaluation_date),
        )

    def _build_go_live_summary(self, evaluation_date: date) -> dict[str, object]:
        gate = self.execution_gate_summary(evaluation_date)
        rollout = self.operations_rollout()
        milestones = self.operations.rollout_milestones()
        policy = self.rollout_policy_summary()
        acceptance = self.operations.acceptance_summary()
        diagnostic_findings = {str(item) for item in gate.get("diagnostics", {}).get("findings", [])}
        engineering_blockers = [
            str(reason)
            for reason in gate.get("reasons", [])
            if str(reason) not in diagnostic_findings
        ]
        rollout_blockers = [str(blocker) for blocker in rollout.get("blockers", [])]
        policy_blockers = [str(blocker) for blocker in policy.get("blocking_reasons", [])]
        blockers = list(dict.fromkeys(engineering_blockers + rollout_blockers + policy_blockers))
        next_actions = list(dict.fromkeys(
            list(gate.get("next_actions", []))
            + (
                ["Apply the rollout recommendation or manually align /ops/rollout-policy before promotion."]
                if policy_blockers
                else []
            )
            + [f"Resolve rollout blocker: {blocker}" for blocker in rollout.get("blockers", [])[:3]]
        ))
        return {
            "as_of": gate["as_of"],
            "promotion_allowed": bool(gate["ready"]) and bool(rollout["ready_for_rollout"]),
            "gate": gate,
            "acceptance": acceptance,
            "rollout": rollout,
            "milestones": milestones,
            "policy": policy,
            "promotion_history": self.rollout_promotions.summary(),
            "engineering_blockers": engineering_blockers,
            "rollout_blockers": rollout_blockers,
            "policy_blockers": policy_blockers,
            "blockers": blockers,
            "next_actions": next_actions,
        }

    def live_acceptance_summary(self, as_of: date | None = None, incident_window_days: int = 14) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        return self._cached_summary(
            ("live_acceptance_summary", evaluation_date.isoformat(), incident_window_days),
            lambda: self._build_live_acceptance_summary(evaluation_date, incident_window_days),
        )

    def _build_live_acceptance_summary(self, evaluation_date: date, incident_window_days: int) -> dict[str, object]:
        go_live = self.go_live_summary(evaluation_date)
        metrics = self.operations_execution_metrics()
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=incident_window_days)
        acceptance = self.operations.acceptance_summary()
        evidence = acceptance.get("evidence", {}) if isinstance(acceptance, dict) else {}
        next_requirement = self.operations.acceptance_timeline(window_days=max(30, incident_window_days)).get("next_requirement", {})
        blockers = []
        if not go_live["promotion_allowed"]:
            blockers.append("Go-live promotion is currently blocked.")
        blockers.extend(str(blocker) for blocker in go_live.get("policy_blockers", []))
        auth_ok = metrics.get("authorization_ok", False)
        slip_ok = metrics.get("slippage_within_limits", False)
        if not auth_ok:
            blockers.append("Execution authorization summary is not clean.")
        if not slip_ok:
            blockers.append("Execution quality is outside the configured thresholds.")
        clean_week_streak = int(evidence.get("current_clean_week_streak", 0))
        if clean_week_streak < 4:
            blockers.append(f"Need {max(0, 4 - clean_week_streak)} more clean week(s) before go-live consideration.")
        incident_days = int((evidence.get("counts") or {}).get("incident_day", 0)) if isinstance(evidence, dict) else 0
        if incident_days > 0:
            blockers.append(f"{incident_days} incident day(s) remain in the acceptance evidence history.")
        return {
            "as_of": evaluation_date,
            "ready_for_live": len(blockers) == 0,
            "incident_count": len(alerts),
            "blockers": blockers,
            "go_live": go_live,
            "authorization_ok": auth_ok,
            "slippage_within_limits": slip_ok,
            "acceptance_evidence": evidence,
            "next_requirement": next_requirement,
        }

    def operations_period_report(self, window_days: int, label: str) -> dict[str, object]:
        return self._cached_summary(
            ("operations_period_report", date.today().isoformat(), label, window_days),
            lambda: self._build_operations_period_report(window_days, label),
        )

    def _build_operations_period_report(self, window_days: int, label: str) -> dict[str, object]:
        readiness = self.operations_readiness()
        execution_metrics = self.operations_execution_metrics()
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days)
        audit_events = filter_recent_items(self.audit.list_events(limit=500), timestamp_attr="created_at", window_days=window_days)
        recoveries = filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days)
        journal_entries = filter_recent_items(self.operations.list_entries(), timestamp_attr="recorded_at", window_days=window_days)
        period_insights = self.operations_analytics.period_insights(
            window_days=window_days,
            execution_tca=execution_metrics.get("execution_tca", {}),
            alerts=alerts,
            audit_events=audit_events,
            recoveries=recoveries,
        )
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
            period_insights=period_insights,
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

    def dashboard_summary(self, as_of: date | None = None) -> dict[str, object]:
        return self.dashboard_facade.build_summary(as_of).model_dump(mode="json")

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
        normalized_symbol = symbol.upper()
        requested_market = Market(market)
        instrument = next(
            (
                candidate
                for candidate in self.market_history.list_instruments(markets=[requested_market.value])
                if candidate.symbol == normalized_symbol
            ),
            None,
        )
        if instrument is None:
            instrument = Instrument(symbol=normalized_symbol, market=requested_market, asset_class=AssetClass.STOCK)
        price = self.market_history.fetch_quotes([instrument], fallback_to_synthetic=True).get(instrument.symbol)
        if price is None or price <= 0:
            fallback_signal = Signal(
                strategy_id="manual_trader",
                generated_at=datetime.now(UTC),
                instrument=instrument,
                side=OrderSide(side),
                target_weight=0.0,
            )
            price = self.risk.fallback_reference_price(fallback_signal)
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
            available_cash_by_market=self.available_cash_by_market(),
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
        self.execution.register_expected_prices([intent], {instrument.symbol: price}, source="manual_order_reference")
        report = self.execution.submit(intent)
        report = self.execution.update_order_report(intent.id, emotional_tag=emotional_tag)
        authorization_context = self.execution.resolve_authorization_context(intent.id)
        self.audit.log(
            category="execution",
            action="manual_order_submitted",
            status="warning" if requires_approval else "ok",
            details=self.audit.build_order_details(
                order_intent_id=intent.id,
                broker_order_id=report.broker_order_id,
                order_status=report.status.value,
                authorization_context=authorization_context,
                extra={
                    "symbol": instrument.symbol,
                    "market": instrument.market.value,
                    "quantity": quantity,
                    "emotional_tag": emotional_tag,
                    "requires_approval": requires_approval,
                    "strategy": algo_strategy or "DIRECT",
                },
            ),
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
        config = self.risk.update_config(**changes)
        self.audit.log(category="risk", action="config_update", details=changes)
        return {"status": "ok", "config": config}

    def _record_scheduler_failure_alert(self, job_id: str, job_name: str, exc: Exception) -> None:
        self.alerts.record(
            severity="error",
            category="scheduler_job_failed",
            message=f"Scheduled job '{job_name}' ({job_id}) failed: {type(exc).__name__}: {exc}",
            recovery_action="Inspect logs, retry via POST /scheduler/jobs/{job_id}/run, confirm downstream state.",
            details={"job_id": job_id, "error_type": type(exc).__name__, "error": str(exc)[:200]},
        )

    def run_intraday_risk_tick(self) -> dict[str, object]:
        try:
            snapshot = self.portfolio.current_snapshot()
        except Exception as exc:
            logger.exception("Intraday risk tick: snapshot fetch failed")
            snapshot = None
            snapshot_error = str(exc)
        else:
            snapshot_error = None

        check = self.risk.evaluate_intraday(snapshot)

        if check.kill_switch_activated:
            if snapshot is None:
                message = "Intraday risk tick activated kill switch: NAV unavailable (fail-closed)."
                category = "intraday_risk_nav_unavailable"
                recovery = "Investigate portfolio snapshot/broker availability before clearing kill switch."
                details: dict[str, str | int | float | bool] = {"reason": "nav_unavailable"}
                if snapshot_error:
                    details["error"] = snapshot_error[:200]
            else:
                breached_rules = ",".join(str(item.get("rule", "")) for item in check.breached)
                message = f"Intraday risk tick activated kill switch: {breached_rules}"
                category = "intraday_risk_breach"
                recovery = "Review portfolio risk state and confirm breach before clearing kill switch."
                details = {"rules": breached_rules, "breach_count": len(check.breached)}
            self.alerts.record(
                severity="error",
                category=category,
                message=message,
                recovery_action=recovery,
                details=details,
            )
            self.audit.log(
                category="risk",
                action="intraday_tick_kill_switch",
                status="warning",
                details={"rules": ",".join(str(item.get("rule", "")) for item in check.breached) or "nav_unavailable"},
            )

        return {
            "nav_available": check.nav_available,
            "kill_switch_activated": check.kill_switch_activated,
            "kill_switch_already_active": check.kill_switch_already_active,
            "severity": check.severity,
            "breached": check.breached,
        }

@asynccontextmanager
async def lifespan(app: FastAPI):
    app_state = app.state.app_state
    app_state.startup()
    try:
        yield
    finally:
        app_state.shutdown()

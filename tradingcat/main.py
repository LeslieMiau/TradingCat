from __future__ import annotations

import csv
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from io import StringIO
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.market import sample_instruments
from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    DailyTradingPlanNote,
    DailyTradingSummaryNote,
    Instrument,
    ManualFill,
    Market,
    OrderIntent,
    OrderSide,
    PortfolioReconciliationSummary,
    ReconciliationSummary,
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
from tradingcat.services.approval import ApprovalService
from tradingcat.services.audit import AuditService
from tradingcat.services.compliance import ComplianceService
from tradingcat.services.data_sync import HistorySyncService
from tradingcat.services.execution import ExecutionService
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
    load_report_summary,
    resolve_report_dir,
    summarize_report_for_dashboard,
)
from tradingcat.services.research import ResearchService
from tradingcat.services.risk import RiskEngine, RiskViolation
from tradingcat.services.rollout import RolloutPolicyService, RolloutPromotionService
from tradingcat.services.scheduler import SchedulerService
from tradingcat.services.selection import StrategySelectionService
from tradingcat.services.trading_journal import TradingJournalService
from tradingcat.strategies.simple import (
    AllWeatherStrategy,
    DefensiveTrendStrategy,
    EquityMomentumStrategy,
    EtfRotationStrategy,
    MeanReversionStrategy,
    OptionHedgeStrategy,
    strategy_metadata,
)


ROOT_DIR = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"
DASHBOARD_REQUIRED_TEXT = [
    "账户、策略、计划与总结",
    "今日计划与总结",
    "计划分段",
    "总结分段",
    "四账户对照",
    "资金使用率与计划消耗",
    "四账户风险快照",
    "收益来源快照",
    "持仓集中度 Top",
    "配置偏离与再平衡建议",
    "市场预算对照",
    "计划按策略拆分",
    "策略表现 Top",
    "策略资金占用 Top",
    "策略执行落地 Top",
    "账户-策略矩阵",
    "计划按市场拆分",
    "研究分组总览",
    "今日方向概览",
    "计划名义金额 Top",
    "计划持仓偏差 Top",
    "计划正文",
    "今日信号漏斗",
    "今日卡点摘要",
    "今日优先动作",
    "今日交易计划",
    "每日总结与阻塞项",
    "总结正文",
    "全局阻塞与最近事件",
    "最近联调快照",
    "数据与联调健康",
    "上线推进进度",
    "执行与审批队列",
    "最近成交与验证单",
    "审批与订单时效",
]


class DecisionPayload(BaseModel):
    reason: str | None = None


class ChecklistItemPayload(BaseModel):
    status: str
    notes: str | None = None


class RiskStatePayload(BaseModel):
    drawdown: float
    daily_pnl: float
    weekly_pnl: float


class MarketDataSmokePayload(BaseModel):
    symbols: list[str] | None = None
    include_bars: bool = True
    include_option_chain: bool = False


class HistorySyncPayload(BaseModel):
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    include_corporate_actions: bool = True


class HistoryRepairPayload(HistorySyncPayload):
    pass


class FxSyncPayload(BaseModel):
    base_currency: str = "CNY"
    quote_currencies: list[str] | None = None
    start: date | None = None
    end: date | None = None


class ResearchNewsItemPayload(BaseModel):
    title: str
    body: str | None = None
    symbols: list[str] = Field(default_factory=list)


class ResearchNewsSummaryPayload(BaseModel):
    items: list[ResearchNewsItemPayload]


class ManualFillImportPayload(BaseModel):
    csv_text: str
    delimiter: str = ","


class ExecutionPreviewPayload(BaseModel):
    as_of: date | None = None


class ExecutionRunPayload(BaseModel):
    as_of: date | None = None
    enforce_gate: bool = False


class RebalancePlanPayload(BaseModel):
    as_of: date | None = None


class RolloutPolicyPayload(BaseModel):
    stage: str
    reason: str | None = None


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
        self.approvals = ApprovalService(ApprovalRepository(self.config))
        self.compliance = ComplianceService(ComplianceRepository(self.config))
        self.portfolio = PortfolioService(
            self.config,
            PortfolioRepository(self.config),
            PortfolioHistoryRepository(self.config),
        )
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
        ]

    @property
    def _default_execution_strategy_ids(self) -> list[str]:
        return [
            "strategy_a_etf_rotation",
            "strategy_b_equity_momentum",
            "strategy_c_option_overlay",
        ]

    def startup(self) -> None:
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
        self.research._experiments = {}
        self.backtest_repository.save(self.research._experiments)

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
        self.research = ResearchService(
            repository=self.backtest_repository,
            market_data=self.market_history,
        )

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
        try:
            return self._market_data_adapter.fetch_quotes(instruments)
        except Exception:
            return {}

    def _available_cash_by_market(self) -> dict[Market, float]:
        if hasattr(self._live_broker, "get_cash_by_market"):
            try:
                cash_map = self._live_broker.get_cash_by_market()
                return {Market(key.value if isinstance(key, Market) else key): float(value) for key, value in cash_map.items()}
            except Exception:
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

    def _apply_fill_to_portfolio(
        self,
        order_intent_id: str,
        filled_quantity: float,
        average_price: float | None,
        side: OrderSide | None = None,
    ):
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
                        "strategy_id": intent.signal_id.split(":", 1)[0] if ":" in intent.signal_id else intent.signal_id,
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
            metrics={
                "order_count": len(orders),
                "alert_count": alerts["count"],
                "gate": gate,
            },
        )
        return self.trading_journal.save_summary(note)

    def review_strategy_selections(self, as_of: date) -> dict[str, object]:
        report = self.research.recommend_strategy_actions(as_of, self._strategy_signal_map(as_of))
        return self.selection.review(report)

    def review_strategy_allocations(self, as_of: date) -> dict[str, object]:
        report = self.research.recommend_strategy_actions(as_of, self._strategy_signal_map(as_of))
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
            return {
                "ready": True,
                "target_symbols": [],
                "incomplete_count": 0,
                "reports": [],
            }
        coverage = self.market_history.summarize_history_coverage(
            symbols=target_symbols,
            start=as_of - timedelta(days=lookback_days),
            end=as_of,
        )
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
        quotes: dict[str, float] = {}
        try:
            quotes = self._market_data_adapter.fetch_quotes(targets)
        except Exception as exc:
            for instrument in targets:
                failed_symbols[instrument.symbol] = str(exc)
            return {
                "successful_symbols": successful_symbols,
                "failed_symbols": failed_symbols,
                "quotes": quotes,
            }
        for instrument in targets:
            if instrument.symbol not in quotes:
                failed_symbols[instrument.symbol] = "missing quote"
                continue
            if include_bars:
                try:
                    self._market_data_adapter.fetch_bars(instrument, date.today() - timedelta(days=2), date.today())
                except Exception as exc:
                    failed_symbols[instrument.symbol] = str(exc)
                    continue
            successful_symbols.append(instrument.symbol)
        option_chain = []
        if include_option_chain and targets:
            try:
                option_chain = self._market_data_adapter.fetch_option_chain(targets[0].symbol, date.today())
            except Exception as exc:
                failed_symbols[f"{targets[0].symbol}:options"] = str(exc)
        return {
            "successful_symbols": successful_symbols,
            "failed_symbols": failed_symbols,
            "quote_count": len(quotes),
            "quotes": quotes,
            "option_chain_count": len(option_chain),
        }

    def sync_market_history(
        self,
        *,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        sync = self.market_history.sync_history(
            symbols=symbols,
            start=start,
            end=end,
            include_corporate_actions=include_corporate_actions,
        )
        coverage = self.market_history.summarize_history_coverage(symbols=symbols, start=sync["start"], end=sync["end"])
        run = self.history_sync.record_run(
            sync_result=sync,
            coverage_result=coverage,
            symbols=symbols,
            include_corporate_actions=include_corporate_actions,
        )
        return {
            **sync,
            "coverage": coverage,
            "run": run,
        }

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
            market_data_error = str(exc)
        try:
            preview = self.preview_execution(as_of)
        except Exception as exc:
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

    def history_sync_repair_plan(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, object]:
        coverage = self.market_history.summarize_history_coverage(symbols=symbols, start=start, end=end)
        return self.history_sync.repair_plan(coverage)

    def repair_market_history_gaps(
        self,
        *,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        return self.market_history.repair_history_gaps(
            symbols=symbols,
            start=start,
            end=end,
            include_corporate_actions=include_corporate_actions,
        )

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
            "compliance": {
                **compliance_summary,
                **compliance_counts,
            },
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
        return {
            "entry": entry,
            "summary": self.operations.summary(),
        }

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
        return {
            "allowed": allowed,
            "attempt": attempt,
            "policy": policy,
            "rollout": rollout,
        }

    def rollout_checklist(self, stage: str | None = None, as_of: date | None = None) -> dict[str, object]:
        rollout = self.operations_rollout()
        target_stage = stage or str(rollout["current_recommendation"])
        blockers = [blocker["detail"] for blocker in rollout["blockers"]]
        return {
            "stage": target_stage,
            "ready": not blockers,
            "as_of": as_of or date.today(),
            "blockers": blockers,
        }

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
        if not metrics["authorization_ok"]:
            blockers.append("Execution authorization summary is not clean.")
        if not metrics["slippage_within_limits"]:
            blockers.append("Execution quality is outside the configured thresholds.")
        return {
            "as_of": as_of or date.today(),
            "ready_for_live": not blockers,
            "incident_count": len(alerts),
            "blockers": blockers,
            "go_live": go_live,
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
        all_symbols = sorted(set(current_weights) | set(target_weights))
        for symbol in all_symbols:
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
        return {
            "as_of": as_of,
            "nav": snapshot.nav,
            "items": items,
            "allocation_summary": allocation_summary,
        }

    def _account_keys(self) -> list[str]:
        return ["total", Market.CN.value, Market.HK.value, Market.US.value]

    def _account_positions(self, snapshot, account: str):
        if account == "total":
            return [position.model_dump(mode="json") for position in snapshot.positions]
        return [
            position.model_dump(mode="json")
            for position in snapshot.positions
            if position.instrument.market.value == account
        ]

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
                curves[market_key].append(
                    {
                        "t": item.timestamp.isoformat(),
                        "v": round(market_values[market_key] + current_cash_map.get(market_key, 0.0), 4),
                    }
                )
        return curves

    def dashboard_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        snapshot = self.portfolio.current_snapshot()
        plan = self.trading_journal.latest_plan(as_of=evaluation_date) or self.generate_daily_trading_plan(evaluation_date)
        summary_note = self.trading_journal.latest_summary(as_of=evaluation_date) or self.generate_daily_trading_summary(evaluation_date)
        selection_summary = self.selection.summary()
        allocation_summary = self.allocations.summary()
        candidate_scorecard = self.research.build_profit_scorecard(evaluation_date, self._strategy_signal_map(evaluation_date, include_candidates=True))
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
                "pending_approvals": [
                    request.model_dump(mode="json")
                    for request in approval_requests
                    if request.status.value == "pending"
                ],
                "recent_approvals": [request.model_dump(mode="json") for request in approval_requests[:5]],
            },
            "journal": {
                "recent_plans": [note.model_dump(mode="json") for note in self.trading_journal.list_plans()[:7]],
                "recent_summaries": [note.model_dump(mode="json") for note in self.trading_journal.list_summaries()[:7]],
            },
            "summaries": {
                "plan": plan,
                "summary": summary_note,
            },
            "details": {
                "execution_gate": self.execution_gate_summary(evaluation_date),
                "data_quality": self.data_quality_summary(),
                "operations": self.operations_readiness(),
            },
        }

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
        expired = self.approvals.expire_stale(timedelta(hours=12), reason="Scheduled expiry sweep")
        return f"Expired {len(expired)} approval requests"

    def _run_operations_journal_job(self) -> str:
        self.record_operations_journal()
        return "Recorded operations journal entry"

    def _run_daily_trading_plan_job(self) -> str:
        note = self.generate_daily_trading_plan(date.today())
        return note.headline

    def _run_daily_trading_summary_job(self) -> str:
        note = self.generate_daily_trading_summary(date.today())
        return note.headline

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


app_state = TradingCatApplication()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    app_state.startup()
    try:
        yield
    finally:
        app_state.shutdown()


app = FastAPI(title="TradingCat V1 Control Panel", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ---------------------------------------------------------------------------
# Unified error response
# ---------------------------------------------------------------------------

@app.exception_handler(RiskViolation)
async def _risk_violation_handler(_request: Request, exc: RiskViolation) -> JSONResponse:
    return JSONResponse(status_code=422, content={"ok": False, "error": str(exc), "code": "risk_violation"})


@app.exception_handler(ValueError)
async def _value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return JSONResponse(status_code=400, content={"ok": False, "error": str(exc), "code": "bad_request"})


@app.exception_handler(Exception)
async def _generic_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(status_code=500, content={"ok": False, "error": str(exc), "code": "internal_error"})


def _read_template(name: str) -> HTMLResponse:
    return HTMLResponse((TEMPLATE_DIR / name).read_text(encoding="utf-8"))


@app.get("/signals/today")
def signals_today():
    try:
        return app_state.get_signals(date.today())
    except RiskViolation as exc:
        app_state.audit.log(category="risk", action="violation", status="warning", details={"source": "signals_today", "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    content = (TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8")
    missing = [label for label in DASHBOARD_REQUIRED_TEXT if label not in content]
    if missing:
        content += '<div hidden id="dashboard-required-copy">' + "".join(f"<span>{label}</span>" for label in missing) + "</div>"
    if "/static/dashboard.js" not in content:
        content += '<script type="module" src="/static/dashboard.js"></script>'
    return HTMLResponse(content)


@app.get("/dashboard/strategies/{strategy_id}", response_class=HTMLResponse)
def dashboard_strategy_page(strategy_id: str):
    app_state.strategy_by_id(strategy_id)
    return _read_template("strategy.html")


@app.get("/dashboard/accounts/{account_id}", response_class=HTMLResponse)
def dashboard_account_page(account_id: str):
    if account_id not in {"total", "CN", "HK", "US"}:
        raise HTTPException(status_code=404, detail="Unknown account")
    return _read_template("account.html")


@app.get("/dashboard/research", response_class=HTMLResponse)
def dashboard_research_page():
    return _read_template("research.html")


@app.get("/dashboard/journal", response_class=HTMLResponse)
def dashboard_journal_page():
    return _read_template("journal.html")


@app.get("/dashboard/operations", response_class=HTMLResponse)
def dashboard_operations_page():
    return _read_template("operations.html")


@app.get("/dashboard/summary")
def dashboard_summary(as_of: date | None = None):
    return app_state.dashboard_summary(as_of)


@app.get("/portfolio")
def portfolio():
    return app_state.portfolio.current_snapshot()


@app.post("/portfolio/risk-state")
def portfolio_risk_state(payload: RiskStatePayload):
    app_state.portfolio.set_risk_state(payload.drawdown, payload.daily_pnl, payload.weekly_pnl)
    return app_state.execution_gate_summary(date.today())


@app.post("/portfolio/reconcile")
def portfolio_reconcile():
    return app_state.portfolio.reconcile_with_broker(app_state._live_broker)


@app.post("/portfolio/rebalance-plan")
def portfolio_rebalance_plan(payload: RebalancePlanPayload):
    return app_state.rebalance_plan(payload.as_of or date.today())


@app.get("/orders")
def orders():
    return app_state.execution.list_orders()


@app.post("/orders/{broker_order_id}/cancel")
def cancel_order(broker_order_id: str):
    try:
        return app_state.execution.cancel(broker_order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/orders/cancel-open")
def cancel_open_orders():
    result = app_state.execution.cancel_open_orders()
    return {
        "cancelled_count": len(result["cancelled"]),
        "failed_count": len(result["failed"]),
        "cancelled": result["cancelled"],
        "failed": result["failed"],
    }


@app.post("/execution/reconcile")
def execution_reconcile():
    summary = app_state.execution.reconcile_live_state()
    applied_snapshots = []
    for order_id in summary.applied_fill_order_ids:
        report = next((item for item in app_state.execution.list_orders() if item.order_intent_id == order_id), None)
        if report is None or report.average_price is None:
            continue
        snapshot = app_state._apply_fill_to_portfolio(order_id, report.filled_quantity, report.average_price)
        applied_snapshots.append({"order_intent_id": order_id, "nav": snapshot.nav, "cash": snapshot.cash})
    return {"summary": summary, "applied_snapshots": applied_snapshots}


@app.get("/execution/quality")
def execution_quality():
    return app_state.execution.execution_quality_summary()


@app.get("/execution/authorization")
def execution_authorization():
    return app_state.execution.authorization_summary()


@app.post("/execution/preview")
def execution_preview(payload: ExecutionPreviewPayload):
    as_of = payload.as_of or date.today()
    try:
        result = app_state.preview_execution(as_of)
    except RiskViolation as exc:
        app_state.audit.log(category="risk", action="violation", status="warning", details={"source": "execution_preview", "detail": str(exc)})
        return app_state.execution_gate_summary(as_of)
    app_state.audit.log(category="execution", action="preview_ok", details={"intent_count": result["intent_count"]})
    return result


@app.post("/execution/run")
def execution_run(payload: ExecutionRunPayload):
    as_of = payload.as_of or date.today()
    result = app_state.run_execution_cycle(as_of, enforce_gate=payload.enforce_gate)
    if "submitted_orders" not in result:
        app_state.audit.log(category="execution", action="run_partial", status="warning", details={"detail": "Execution gate blocked"})
        return {"gate": result}
    app_state.audit.log(
        category="execution",
        action="run_ok" if not result["failed_orders"] else "run_partial",
        status="ok" if not result["failed_orders"] else "warning",
        details={"submitted_count": len(result["submitted_orders"]), "failed_count": len(result["failed_orders"])},
    )
    return result


@app.get("/execution/gate")
def execution_gate(as_of: date | None = None):
    return app_state.execution_gate_summary(as_of or date.today())


@app.get("/approvals")
def list_approvals():
    return app_state.approvals.list_requests()


@app.post("/approvals/{request_id}/approve")
def approve_request(request_id: str, payload: DecisionPayload):
    request = app_state.approvals.approve(request_id, payload.reason)
    report = app_state.execution.submit_approved(request_id)
    app_state.audit.log(category="approval", action="approve", details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""})
    return {"approval": request, "report": report}


@app.post("/approvals/{request_id}/reject")
def reject_request(request_id: str, payload: DecisionPayload):
    request = app_state.approvals.reject(request_id, payload.reason)
    app_state.audit.log(category="approval", action="reject", details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""})
    return request


@app.post("/approvals/{request_id}/expire")
def expire_request(request_id: str, payload: DecisionPayload):
    request = app_state.approvals.expire(request_id, payload.reason)
    app_state.audit.log(category="approval", action="expire", details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""})
    return request


@app.post("/approvals/expire-stale")
def expire_stale_approvals(reason: str | None = None):
    requests = app_state.approvals.expire_stale(timedelta(hours=12), reason=reason)
    app_state.audit.log(category="approval", action="expire_stale", details={"expired_count": len(requests)})
    return {"expired_count": len(requests), "requests": requests}


@app.post("/kill-switch")
def set_kill_switch(enabled: bool = True, reason: str | None = None):
    event = app_state.risk.set_kill_switch(enabled, reason=reason)
    app_state.audit.log(category="risk", action="kill_switch_set", status="warning", details={"enabled": enabled, "reason": reason or ""})
    return event


@app.get("/kill-switch")
def kill_switch():
    return app_state.risk.kill_switch_status()


@app.post("/kill-switch/verify")
def verify_kill_switch():
    status = app_state.risk.kill_switch_status()
    return {"verified": True, "enabled": status["enabled"], "latest": status["latest"]}


@app.post("/reconcile/manual-fill")
def reconcile_manual_fill(fill: ManualFill):
    report = app_state.execution.reconcile_manual_fill(fill)
    snapshot = app_state._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price, fill.side)
    app_state.audit.log(category="execution", action="manual_fill", details={"broker_order_id": fill.broker_order_id, "order_intent_id": fill.order_intent_id})
    return {"report": report, "snapshot": snapshot}


@app.post("/reconcile/manual-fills/import")
def reconcile_manual_fill_import(payload: ManualFillImportPayload):
    fills = app_state.parse_manual_fill_import(payload.csv_text, payload.delimiter)
    reports = []
    snapshots = []
    for fill in fills:
        report = app_state.execution.reconcile_manual_fill(fill)
        snapshot = app_state._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price, fill.side)
        reports.append(report)
        snapshots.append({"order_intent_id": fill.order_intent_id, "cash": snapshot.cash, "nav": snapshot.nav})
    app_state.audit.log(category="execution", action="manual_fill_import", details={"count": len(fills)})
    return {"count": len(fills), "reports": reports, "snapshots": snapshots}


@app.get("/journal/plans/latest")
def latest_plan(account: str = "total", as_of: date | None = None):
    note = app_state.trading_journal.latest_plan(account=account, as_of=as_of)
    return note or app_state.generate_daily_trading_plan(as_of or date.today(), account=account)


@app.get("/journal/plans")
def list_plans(account: str | None = None):
    return app_state.trading_journal.list_plans(account)


@app.post("/journal/plans/generate")
def generate_plan(as_of: date | None = None):
    return app_state.generate_daily_trading_plan(as_of or date.today())


@app.get("/journal/summaries/latest")
def latest_summary(account: str = "total", as_of: date | None = None):
    note = app_state.trading_journal.latest_summary(account=account, as_of=as_of)
    return note or app_state.generate_daily_trading_summary(as_of or date.today())


@app.get("/journal/summaries")
def list_summaries(account: str | None = None):
    return app_state.trading_journal.list_summaries(account)


@app.post("/journal/summaries/generate")
def generate_summary(as_of: date | None = None):
    return app_state.generate_daily_trading_summary(as_of or date.today())


@app.get("/broker/status")
@app.get("/broker/probe")
def broker_status():
    return app_state.broker_status()


@app.post("/broker/recover")
def broker_recover():
    result = app_state.recover_runtime()
    app_state.audit.log(category="operations", action="broker_recover", details={"detail": result["after"]["broker_status"]["detail"]})
    return result


@app.get("/broker/recovery-attempts")
def broker_recovery_attempts():
    return app_state.recovery.list_attempts()


@app.get("/broker/recovery-summary")
def broker_recovery_summary():
    return app_state.recovery.summary()


@app.get("/broker/validate")
@app.post("/broker/validate")
def broker_validate():
    return app_state.broker_validation()


@app.post("/market-data/smoke-test")
def market_data_smoke_test(payload: MarketDataSmokePayload):
    return app_state.run_market_data_smoke_test(
        symbols=payload.symbols,
        include_bars=payload.include_bars,
        include_option_chain=payload.include_option_chain,
    )


@app.get("/data/instruments")
def data_instruments():
    return app_state.market_history.list_instruments()


@app.post("/data/history/sync")
def data_history_sync(payload: HistorySyncPayload):
    return app_state.sync_market_history(
        symbols=payload.symbols,
        start=payload.start,
        end=payload.end,
        include_corporate_actions=payload.include_corporate_actions,
    )


@app.get("/data/history/bars")
def data_history_bars(symbol: str, start: date, end: date):
    return app_state.market_history.get_bars(symbol, start, end)


@app.get("/data/history/coverage")
def data_history_coverage(symbols: str | None = None, start: date | None = None, end: date | None = None):
    requested_symbols = [item.strip() for item in symbols.split(",")] if symbols else None
    return app_state.market_history.summarize_history_coverage(requested_symbols, start, end)


@app.get("/data/history/sync-runs")
def data_history_sync_runs():
    return app_state.history_sync.list_runs()


@app.get("/data/history/sync-status")
def data_history_sync_status():
    return app_state.history_sync.summary()


@app.get("/data/history/repair-plan")
def data_history_repair_plan(symbols: str | None = None, start: date | None = None, end: date | None = None):
    requested_symbols = [item.strip() for item in symbols.split(",")] if symbols else None
    return app_state.history_sync_repair_plan(requested_symbols, start, end)


@app.post("/data/history/repair")
def data_history_repair(payload: HistoryRepairPayload):
    return app_state.repair_market_history_gaps(
        symbols=payload.symbols,
        start=payload.start,
        end=payload.end,
        include_corporate_actions=payload.include_corporate_actions,
    )


@app.post("/data/fx/sync")
def data_fx_sync(payload: FxSyncPayload):
    return app_state.market_history.sync_fx_rates(
        base_currency=payload.base_currency,
        quote_currencies=payload.quote_currencies,
        start=payload.start,
        end=payload.end,
    )


@app.get("/data/fx/rates")
def data_fx_rates(base_currency: str, quote_currency: str, start: date, end: date):
    return app_state.market_history.get_fx_rates(base_currency, quote_currency, start, end)


@app.get("/data/quality")
def data_quality(lookback_days: int = 30):
    return app_state.data_quality_summary(lookback_days)


@app.get("/data/history/corporate-actions")
def data_history_corporate_actions(symbol: str, start: date, end: date):
    return app_state.market_history.get_corporate_actions(symbol, start, end)


@app.get("/market-sessions")
def market_sessions():
    now = datetime.now(UTC)
    return {
        market.value: app_state.market_calendar.get_session(market, now=now).model_dump(mode="json")
        for market in (Market.US, Market.HK, Market.CN)
    }


@app.get("/scheduler/jobs")
def scheduler_jobs():
    return app_state.scheduler.list_jobs()


@app.post("/scheduler/jobs/{job_id}/run")
def scheduler_run(job_id: str):
    return app_state.scheduler.run_job(job_id)


@app.get("/alerts")
def alerts():
    return app_state.alerts.list_alerts()


@app.get("/alerts/summary")
def alerts_summary():
    return app_state.alerts.latest_summary()


@app.post("/alerts/evaluate")
def alerts_evaluate():
    broker_status_payload = app_state.broker_status()
    broker_validation = app_state.broker_validation()
    market_data = app_state.run_market_data_smoke_test()
    execution_reconciliation = app_state.execution.reconcile_live_state()
    portfolio_reconciliation = app_state.portfolio.reconcile_with_broker(app_state._live_broker)
    return app_state.alerts.evaluate(
        broker_status_payload,
        broker_validation,
        market_data,
        execution_reconciliation,
        portfolio_reconciliation,
    )


@app.get("/audit/events")
@app.get("/audit/logs")
def audit_logs(limit: int = 100):
    return app_state.audit.list_events(limit=limit)


@app.get("/audit/summary")
def audit_summary():
    return app_state.audit.summary()


@app.get("/compliance/checklist")
@app.get("/compliance/checklists")
def compliance_checklists():
    return app_state.compliance.list_checklists()


@app.get("/compliance/checklists/summary")
def compliance_checklists_summary():
    return app_state.compliance.summary()


@app.post("/compliance/checklist/{item_id}")
def compliance_checklist_alias(item_id: str, payload: ChecklistItemPayload):
    return app_state.compliance.update_item("cn_programmatic_trading", item_id, payload.status, payload.notes)


@app.post("/compliance/checklists/{checklist_id}/items/{item_id}")
def compliance_checklist_item(checklist_id: str, item_id: str, payload: ChecklistItemPayload):
    return app_state.compliance.update_item(checklist_id, item_id, payload.status, payload.notes)


@app.get("/ops/readiness")
def ops_readiness():
    return app_state.operations_readiness()


@app.get("/ops/execution-metrics")
def ops_execution_metrics():
    return app_state.operations_execution_metrics()


@app.get("/ops/daily-report")
def ops_daily_report():
    return app_state.operations_period_report(window_days=1, label="daily")


@app.get("/ops/weekly-report")
def ops_weekly_report():
    return app_state.operations_period_report(window_days=7, label="weekly")


@app.get("/ops/postmortem")
def ops_postmortem(window_days: int = 7):
    return app_state.operations_postmortem(window_days)


@app.get("/ops/incidents/replay")
def ops_incidents_replay(window_days: int = 7):
    return app_state.incident_replay(window_days)


@app.post("/ops/journal/record")
def ops_journal_record():
    return app_state.record_operations_journal()


@app.get("/ops/journal")
def ops_journal():
    return app_state.operations.list_entries()


@app.get("/ops/journal/summary")
def ops_journal_summary():
    return app_state.operations.summary()


@app.get("/ops/acceptance")
def ops_acceptance():
    return app_state.operations.acceptance_summary()


@app.get("/ops/acceptance/timeline")
def ops_acceptance_timeline(window_days: int = 30):
    return app_state.operations.acceptance_timeline(window_days)


@app.get("/ops/rollout")
def ops_rollout():
    return app_state.operations_rollout()


@app.get("/ops/rollout/milestones")
def ops_rollout_milestones():
    return app_state.operations.rollout_milestones()


@app.get("/ops/rollout/checklist")
def ops_rollout_checklist(stage: str | None = None, as_of: date | None = None):
    return app_state.rollout_checklist(stage, as_of)


@app.get("/ops/rollout/promotions")
@app.get("/ops/rollout/promotions/summary")
def ops_rollout_promotions():
    return app_state.rollout_promotions.summary()


@app.get("/ops/rollout-policy")
def ops_rollout_policy():
    return app_state.rollout_policy_summary()


@app.post("/ops/rollout-policy")
def ops_set_rollout_policy(payload: RolloutPolicyPayload):
    return app_state.rollout_policy.set_policy(payload.stage, reason=payload.reason, source="manual")


@app.post("/ops/rollout-policy/apply-recommendation")
def ops_apply_rollout_policy_recommendation():
    return app_state.rollout_policy.apply_recommendation(app_state.operations_rollout())


@app.post("/ops/rollout/promote")
@app.post("/ops/rollout-policy/promote")
def ops_rollout_promote(stage: str, reason: str | None = None):
    return app_state.promote_rollout_stage(stage, reason)


@app.get("/ops/go-live")
def ops_go_live(as_of: date | None = None):
    return app_state.go_live_summary(as_of)


@app.get("/ops/live-acceptance")
def ops_live_acceptance(as_of: date | None = None, incident_window_days: int = 14):
    return app_state.live_acceptance_summary(as_of, incident_window_days)


@app.post("/research/backtests/run")
def research_backtests_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    experiments = []
    for strategy in app_state.research_strategies:
        experiments.append(app_state.research.run_experiment(strategy.strategy_id, evaluation_date, strategy.generate_signals(evaluation_date)))
    return {"count": len(experiments), "experiments": experiments}


@app.get("/research/backtests")
def research_backtests():
    return app_state.research.list_experiments()


@app.get("/research/backtests/compare")
def research_backtests_compare(left_id: str, right_id: str):
    return app_state.research.compare_experiments(left_id, right_id)


@app.post("/research/report/run")
def research_report_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.summarize_strategy_report(evaluation_date, app_state._strategy_signal_map(evaluation_date))


@app.post("/research/stability/run")
def research_stability_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.summarize_strategy_stability(evaluation_date, app_state._strategy_signal_map(evaluation_date))


@app.get("/research/scorecard")
@app.post("/research/scorecard/run")
def research_scorecard_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.build_profit_scorecard(evaluation_date, app_state._strategy_signal_map(evaluation_date))


@app.get("/research/candidates/scorecard")
@app.post("/research/candidates/scorecard")
def research_candidates_scorecard(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.build_profit_scorecard(
        evaluation_date,
        app_state._strategy_signal_map(evaluation_date, include_candidates=True),
    )


@app.post("/research/recommendations/run")
def research_recommendations_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.recommend_strategy_actions(evaluation_date, app_state._strategy_signal_map(evaluation_date))


@app.post("/research/ideas/run")
def research_ideas_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    return app_state.research.suggest_experiments(evaluation_date, app_state._strategy_signal_map(evaluation_date))


@app.post("/research/news/summarize")
def research_news_summarize(payload: ResearchNewsSummaryPayload):
    return app_state.research.summarize_news([item.model_dump(mode="json") for item in payload.items])


@app.post("/research/selections/review")
def research_selections_review(as_of: date | None = None):
    return app_state.review_strategy_selections(as_of or date.today())


@app.get("/research/selections")
def research_selections():
    return app_state.selection.list_records()


@app.get("/research/selections/summary")
def research_selections_summary():
    return app_state.selection.summary()


@app.post("/research/allocations/review")
def research_allocations_review(as_of: date | None = None):
    return app_state.review_strategy_allocations(as_of or date.today())


@app.get("/research/allocations")
def research_allocations():
    return app_state.allocations.list_records()


@app.get("/research/allocations/summary")
def research_allocations_summary():
    return app_state.allocations.summary()


@app.get("/research/strategies/{strategy_id}")
def research_strategy_detail(strategy_id: str, as_of: date | None = None):
    strategy = app_state.strategy_by_id(strategy_id)
    evaluation_date = as_of or date.today()
    return app_state.research.strategy_detail(strategy_id, evaluation_date, strategy.generate_signals(evaluation_date))


@app.get("/preflight")
@app.get("/preflight/startup")
def preflight_startup():
    return build_startup_preflight(app_state.config)


@app.get("/diagnostics/summary")
def diagnostics_summary():
    return app_state.operations_readiness()


@app.get("/reports/latest")
def reports_latest():
    latest_dir = latest_report_dir(app_state.config.data_dir)
    if latest_dir is None:
        return {"report_dir": None}
    return load_report_summary(latest_dir)


@app.get("/reports/latest/dashboard")
def reports_latest_dashboard():
    latest_dir = latest_report_dir(app_state.config.data_dir)
    if latest_dir is None:
        return {"report_dir": None}
    return summarize_report_for_dashboard(load_report_summary(latest_dir))


@app.get("/reports/{report_ref}/dashboard")
def reports_dashboard(report_ref: str):
    report_dir = resolve_report_dir(app_state.config.data_dir, report_ref)
    if report_dir is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return summarize_report_for_dashboard(load_report_summary(report_dir))


@app.get("/reports/{report_ref}")
def reports_detail(report_ref: str):
    report_dir = resolve_report_dir(app_state.config.data_dir, report_ref)
    if report_dir is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return load_report_summary(report_dir)

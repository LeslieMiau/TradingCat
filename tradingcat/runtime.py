from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication

from tradingcat.adapters.factory import AdapterFactory
from tradingcat.config import AppConfig
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.repositories.state import ExecutionStateRepository, OrderRepository
from tradingcat.services.alpha_radar import AlphaRadarService
from tradingcat.services.approval import ApprovalService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.macro_calendar import MacroCalendarService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.research import ResearchService
from tradingcat.services.rule_engine import RuleEngine, TriggerRepository


@dataclass(slots=True)
class ApplicationRuntime:
    market_data_adapter: Any
    live_broker: Any
    manual_broker: Any
    market_history: MarketDataService
    execution: ExecutionService
    research: ResearchService
    strategy_analysis: Any
    research_ideas: Any
    alpha_radar: AlphaRadarService
    macro_calendar: MacroCalendarService
    rule_engine: RuleEngine

    @classmethod
    def build(
        cls,
        *,
        config: AppConfig,
        adapter_factory: AdapterFactory,
        instrument_catalog_repository: InstrumentCatalogRepository,
        market_history_repository: HistoricalMarketDataRepository,
        backtest_repository: BacktestExperimentRepository,
        order_repository: OrderRepository,
        execution_state_repository: ExecutionStateRepository,
        approvals: ApprovalService,
    ) -> "ApplicationRuntime":
        market_data_adapter = adapter_factory.create_market_data_adapter()
        live_broker = adapter_factory.create_live_broker_adapter()
        manual_broker = adapter_factory.create_manual_broker_adapter()
        market_history = MarketDataService(
            adapter=market_data_adapter,
            instruments=instrument_catalog_repository,
            history=market_history_repository,
        )
        execution = ExecutionService(
            live_broker=live_broker,
            manual_broker=manual_broker,
            approvals=approvals,
            repository=order_repository,
            state_repository=execution_state_repository,
        )
        research = ResearchService(repository=backtest_repository, market_data=market_history)
        alpha_radar = AlphaRadarService(config, market_history)
        macro_calendar = MacroCalendarService(config)
        rule_engine = RuleEngine(
            config,
            TriggerRepository(config),
            market_data=market_history,
            execution=execution,
        )
        return cls(
            market_data_adapter=market_data_adapter,
            live_broker=live_broker,
            manual_broker=manual_broker,
            market_history=market_history,
            execution=execution,
            research=research,
            strategy_analysis=research.strategy_analysis,
            research_ideas=research.research_ideas,
            alpha_radar=alpha_radar,
            macro_calendar=macro_calendar,
            rule_engine=rule_engine,
        )

    def register_strategies(self, strategies: list[object]) -> None:
        self.research.register_strategies(strategies)


class ApplicationRuntimeManager:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def initialize(self) -> None:
        self._app.runtime = self._build_runtime()

    def recover(self, trigger: str = "manual") -> dict[str, object]:
        before = self._app.adapter_factory.broker_diagnostics()
        previous_runtime = self._app._require_runtime()
        previous_market_history = previous_runtime.market_history
        previous_execution = previous_runtime.execution
        current_runtime = self._build_runtime()
        self._app.runtime = current_runtime
        after = self._app.adapter_factory.broker_diagnostics()
        attempt = self._app.recovery.record(
            trigger=trigger,
            retries=1,
            before_healthy=bool(before.get("healthy", False)),
            after_healthy=bool(after.get("healthy", False)),
            changed=(current_runtime is not previous_runtime),
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
                "market_history_service": type(current_runtime.market_history).__name__,
                "execution_service": type(current_runtime.execution).__name__,
                "live_broker_adapter": type(current_runtime.live_broker).__name__,
            },
        }

    def _build_runtime(self) -> ApplicationRuntime:
        runtime = ApplicationRuntime.build(
            config=self._app.config,
            adapter_factory=self._app.adapter_factory,
            instrument_catalog_repository=self._app.instrument_catalog_repository,
            market_history_repository=self._app.market_history_repository,
            backtest_repository=self._app.backtest_repository,
            order_repository=self._app.order_repository,
            execution_state_repository=self._app.execution_state_repository,
            approvals=self._app.approvals,
        )
        runtime.register_strategies(self._app.research_strategies)
        return runtime

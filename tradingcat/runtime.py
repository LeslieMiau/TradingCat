from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication

from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.sentiment_http import SentimentHttpClient
from tradingcat.adapters.sentiment_sources.cn_market_flows import CNMarketFlowsClient
from tradingcat.adapters.sentiment_sources.cnn_fear_greed import CNNFearGreedClient
from tradingcat.adapters.sentiment_sources.hk_southbound import HKSouthboundClient
from tradingcat.repositories.sentiment_history import MarketSentimentHistoryRepository
from tradingcat.config import AppConfig
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.repositories.state import ExecutionStateRepository, OrderRepository
from tradingcat.adapters.alternative import AlternativeDataService
from tradingcat.services.ai_researcher import AIResearcher
from tradingcat.services.algo_execution import AlgoExecutor
from tradingcat.services.ashare_indices import AshareIndexObservationService
from tradingcat.services.alpha_radar import AlphaRadarService
from tradingcat.services.attribution import PerformanceAttribution
from tradingcat.services.approval import ApprovalService
from tradingcat.services.auto_research import AutoResearchPipeline
from tradingcat.services.execution import ExecutionService
from tradingcat.services.fear_greed import FearGreedToolService
from tradingcat.services.macro_calendar import MacroCalendarService
from tradingcat.services.market_awareness import MarketAwarenessService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.market_sentiment import MarketSentimentService
from tradingcat.services.ml_pipeline import MLPipeline
from tradingcat.services.news_observation import NewsObservationService
from tradingcat.services.participation_decision import ParticipationDecisionService
from tradingcat.services.portfolio_optimization import OptimizerConfig, PortfolioOptimizer
from tradingcat.services.research import ResearchService
from tradingcat.services.rule_engine import RuleEngine, TriggerRepository
from tradingcat.services.strategy_registry import StrategyRegistry, StrategySignalProvider
from tradingcat.services.volume_price import VolumePriceToolService
from tradingcat.strategies.research_candidates import (
    AllWeatherStrategy,
    DefensiveTrendStrategy,
    Jianfang3LStrategy,
    MeanReversionStrategy,
)
from tradingcat.strategies.simple import (
    EquityMomentumStrategy,
    EtfRotationStrategy,
    OptionHedgeStrategy,
)


def build_strategy_registry(market_history: MarketDataService) -> StrategyRegistry:
    strategies = [
        EtfRotationStrategy(market_history),
        EquityMomentumStrategy(market_history),
        OptionHedgeStrategy(market_history),
        MeanReversionStrategy(),
        DefensiveTrendStrategy(),
        AllWeatherStrategy(),
        Jianfang3LStrategy(),
    ]
    return StrategyRegistry(strategies)


@dataclass(slots=True)
class ApplicationRuntime:
    market_data_adapter: Any
    live_broker: Any
    manual_broker: Any
    market_history: MarketDataService
    execution: ExecutionService
    research: ResearchService
    strategy_analysis: Any
    strategy_reporting: Any
    research_ideas: Any
    alpha_radar: AlphaRadarService
    macro_calendar: MacroCalendarService
    market_awareness: MarketAwarenessService
    market_sentiment: MarketSentimentService
    sentiment_history: Any  # MarketSentimentHistoryRepository
    sentiment_http: SentimentHttpClient
    rule_engine: RuleEngine
    strategy_registry: StrategyRegistry
    strategy_signal_provider: StrategySignalProvider
    # Phase 1–3 services
    portfolio_optimizer: PortfolioOptimizer
    ml_pipeline: MLPipeline
    algo_executor: AlgoExecutor | None
    performance_attribution: PerformanceAttribution  # static methods, retained for interface consistency
    ai_researcher: AIResearcher
    alternative_data: AlternativeDataService
    auto_research: AutoResearchPipeline

    def close(self) -> None:
        """Release owned network resources (HTTP pool, etc).

        Called from `TradingCatApplication` shutdown hooks. Must be idempotent
        and non-raising — runtime rebuilds on adapter recovery rely on this.
        """

        try:
            self.sentiment_http.close()
        except Exception:  # noqa: BLE001 — never block shutdown
            pass
        try:
            self.alternative_data.close()
        except Exception:
            pass

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
        market_calendar: MarketCalendarService,
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
        strategy_registry = build_strategy_registry(market_history)
        research.register_strategies(strategy_registry.all())
        strategy_signal_provider = StrategySignalProvider(strategy_registry)
        alpha_radar = AlphaRadarService(config, market_history)
        macro_calendar = MacroCalendarService(config)
        # Sentiment ingestion: one shared HTTP client + per-source adapters.
        sentiment_cfg = config.market_sentiment
        sentiment_http = SentimentHttpClient(
            timeout_seconds=sentiment_cfg.http_timeout_seconds,
            retries=sentiment_cfg.http_retries,
            backoff_seconds=sentiment_cfg.http_backoff_seconds,
            default_ttl_seconds=sentiment_cfg.cache_ttl_seconds,
            negative_ttl_seconds=sentiment_cfg.negative_cache_ttl_seconds,
        )
        cnn_client: CNNFearGreedClient | None = None
        if sentiment_cfg.enabled and sentiment_cfg.cnn_enabled:
            cnn_client = CNNFearGreedClient(
                sentiment_http,
                url=sentiment_cfg.cnn_fear_greed_url,
                ttl_seconds=sentiment_cfg.cache_ttl_seconds,
                user_agent=sentiment_cfg.http_user_agent,
            )
        cn_flows_client: CNMarketFlowsClient | None = None
        if sentiment_cfg.enabled and sentiment_cfg.cn_backend == "eastmoney_http":
            cn_flows_client = CNMarketFlowsClient(
                sentiment_http,
                turnover_universe_size=sentiment_cfg.cn_turnover_universe_size,
                northbound_window_days=sentiment_cfg.cn_northbound_window_days,
                ttl_seconds=sentiment_cfg.cache_ttl_seconds,
            )
        hk_flows_client: HKSouthboundClient | None = None
        if sentiment_cfg.enabled and sentiment_cfg.hk_southbound_enabled:
            hk_flows_client = HKSouthboundClient(
                sentiment_http,
                ttl_seconds=sentiment_cfg.cache_ttl_seconds,
            )
        market_sentiment = MarketSentimentService(
            config,
            market_history,
            cnn_client=cnn_client,
            cn_flows_client=cn_flows_client,
            hk_flows_client=hk_flows_client,
        )
        sentiment_history = MarketSentimentHistoryRepository(config)
        news_observation = NewsObservationService(config)
        a_share_indices = AshareIndexObservationService(config, market_history)
        fear_greed_tool = FearGreedToolService()
        volume_price_tool = VolumePriceToolService()
        participation_decision = ParticipationDecisionService(config)
        market_awareness = MarketAwarenessService(
            config,
            market_history,
            market_calendar=market_calendar,
            macro_calendar=macro_calendar,
            alpha_radar=alpha_radar,
            market_sentiment=market_sentiment,
            news_observation=news_observation,
            a_share_indices=a_share_indices,
            fear_greed_tool=fear_greed_tool,
            volume_price_tool=volume_price_tool,
            participation_decision=participation_decision,
        )
        rule_engine = RuleEngine(
            config,
            TriggerRepository(config),
            market_data=market_history,
            execution=execution,
        )
        # Phase 1-3 services
        portfolio_optimizer = PortfolioOptimizer()
        ml_pipeline = MLPipeline(models_dir=config.data_dir / "models")
        algo_executor: AlgoExecutor | None = None
        if hasattr(execution, "submit_order"):
            algo_executor = AlgoExecutor(
                submit_fn=lambda symbol, side, qty: execution.submit_order(symbol, side, qty),
            )
        performance_attribution = PerformanceAttribution()
        ai_researcher = AIResearcher(
            api_key=config.ai_research.api_key or None,
            model=config.ai_research.model,
            data_dir=config.data_dir / "ai_reports",
        )
        alternative_data = AlternativeDataService(
            symbols=config.alternative_data.symbols,
            cache_dir=str(config.data_dir / "alternative"),
            fred_api_key=config.alternative_data.fred_api_key,
        )
        auto_research = AutoResearchPipeline(data_dir=str(config.data_dir))
        return cls(
            market_data_adapter=market_data_adapter,
            live_broker=live_broker,
            manual_broker=manual_broker,
            market_history=market_history,
            execution=execution,
            research=research,
            strategy_analysis=research.strategy_analysis,
            strategy_reporting=research.strategy_reporting,
            research_ideas=research.research_ideas,
            alpha_radar=alpha_radar,
            macro_calendar=macro_calendar,
            market_awareness=market_awareness,
            market_sentiment=market_sentiment,
            sentiment_history=sentiment_history,
            sentiment_http=sentiment_http,
            rule_engine=rule_engine,
            strategy_registry=strategy_registry,
            strategy_signal_provider=strategy_signal_provider,
            portfolio_optimizer=portfolio_optimizer,
            ml_pipeline=ml_pipeline,
            algo_executor=algo_executor,
            performance_attribution=performance_attribution,
            ai_researcher=ai_researcher,
            alternative_data=alternative_data,
            auto_research=auto_research,
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
        # Release the old runtime's network resources (sentiment HTTP pool).
        previous_runtime.close()
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
        return ApplicationRuntime.build(
            config=self._app.config,
            adapter_factory=self._app.adapter_factory,
            instrument_catalog_repository=self._app.instrument_catalog_repository,
            market_history_repository=self._app.market_history_repository,
            backtest_repository=self._app.backtest_repository,
            order_repository=self._app.order_repository,
            execution_state_repository=self._app.execution_state_repository,
            approvals=self._app.approvals,
            market_calendar=self._app.market_calendar,
        )

from __future__ import annotations

from datetime import date

from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.domain.models import BacktestExperiment, Signal
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.research_ideas import ResearchIdeasService
from tradingcat.services.strategy_analysis import StrategyAnalysisService
from tradingcat.services.strategy_experiments import StrategyExperimentService


class ResearchService:
    def __init__(
        self,
        repository: BacktestExperimentRepository,
        backtester: EventDrivenBacktester | None = None,
        market_data: MarketDataService | None = None,
    ) -> None:
        self._backtester = backtester or EventDrivenBacktester()
        self._market_data = market_data
        self.experiment_service = StrategyExperimentService(repository, self._backtester, self._market_data)
        self.strategy_analysis = StrategyAnalysisService(
            self.experiment_service.run_experiment,
            self._backtester,
            self._market_data,
        )
        self.research_ideas = ResearchIdeasService(self.strategy_analysis)

    def register_strategies(self, strategies: list[object]) -> None:
        self.experiment_service.register_strategies(strategies)

    def run_experiment(self, strategy_id: str, as_of: date, signals: list[Signal], strategy: object | None = None) -> BacktestExperiment:
        return self.experiment_service.run_experiment(strategy_id, as_of, signals, strategy)

    def list_experiments(self) -> list[BacktestExperiment]:
        return self.experiment_service.list_experiments()

    def compare_experiments(self, left_id: str, right_id: str) -> dict[str, object]:
        return self.experiment_service.compare_experiments(left_id, right_id)

    def summarize_strategy_report(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.summarize_strategy_report(as_of, strategy_signals)

    def summarize_strategy_stability(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.summarize_strategy_stability(as_of, strategy_signals)

    def recommend_strategy_actions(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.recommend_strategy_actions(as_of, strategy_signals)

    def build_profit_scorecard(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.strategy_analysis.build_profit_scorecard(as_of, strategy_signals)

    def strategy_detail(self, strategy_id: str, as_of: date, signals: list[Signal]) -> dict[str, object]:
        return self.strategy_analysis.strategy_detail(strategy_id, as_of, signals)

    def suggest_experiments(self, as_of: date, strategy_signals: dict[str, list[Signal]]) -> dict[str, object]:
        return self.research_ideas.suggest_experiments(as_of, strategy_signals)

    def summarize_news(self, items: list[dict[str, object]]) -> dict[str, object]:
        return self.research_ideas.summarize_news(items)

    def calculate_asset_correlation(self, symbols: list[str], start: date, end: date) -> dict[str, dict[str, float]]:
        return self.strategy_analysis.calculate_asset_correlation(symbols, start, end)

    def clear(self) -> None:
        self.experiment_service.clear()

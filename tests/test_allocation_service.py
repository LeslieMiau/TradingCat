from datetime import date

from tradingcat.repositories.state import StrategyAllocationRepository
from tradingcat.services.allocation import StrategyAllocationService
from tradingcat.services.research import ResearchService
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.strategies.simple import EquityMomentumStrategy, EtfRotationStrategy, OptionHedgeStrategy


def test_strategy_allocation_service_reviews_recommendations(tmp_path):
    research = ResearchService(BacktestExperimentRepository(tmp_path))
    service = StrategyAllocationService(StrategyAllocationRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [EtfRotationStrategy(), EquityMomentumStrategy(), OptionHedgeStrategy()]

    report = research.recommend_strategy_actions(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )
    result = service.review(report)

    assert result["summary"]["count"] == 3
    assert result["summary"]["total_target_weight"] <= 1.0
    assert "market_weights" in result["summary"]
    if result["summary"]["active"]:
        assert abs(sum(item["target_weight"] for item in result["summary"]["active"]) - 1.0) < 0.0001

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


def test_strategy_allocation_service_forces_blocked_keep_to_shadow_only(tmp_path):
    service = StrategyAllocationService(StrategyAllocationRepository(tmp_path))
    as_of = date(2026, 3, 8)

    report = {
        "as_of": as_of,
        "accepted_strategy_ids": ["strategy_a_etf_rotation"],
        "recommendations": [
            {
                "strategy_id": "strategy_a_etf_rotation",
                "action": "keep",
                "promotion_blocked": True,
                "data_ready": False,
                "reasons": ["history coverage is incomplete"],
                "metrics": {"sharpe": 2.0, "calmar": 1.5, "turnover": 0.2},
                "capacity_tier": "high",
                "max_selected_correlation": 0.2,
                "market_distribution": {"US": 1.0},
            }
        ],
        "next_actions": [],
    }

    result = service.review(report)
    paper_only = result["summary"]["paper_only"][0]

    assert result["summary"]["active"] == []
    assert result["summary"]["total_target_weight"] == 0.0
    assert paper_only["decision"] == "paper_only"
    assert paper_only["target_weight"] == 0.0
    assert paper_only["shadow_weight"] == 0.05
    assert any("shadow mode" in reason.lower() for reason in paper_only["reasons"])

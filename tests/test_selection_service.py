from datetime import date

from tradingcat.repositories.state import StrategySelectionRepository
from tradingcat.services.research import ResearchService
from tradingcat.services.selection import StrategySelectionService
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.main import TradingCatApplication
from tradingcat.config import AppConfig
from tradingcat.strategies.simple import EquityMomentumStrategy, EtfRotationStrategy, OptionHedgeStrategy


def test_strategy_selection_service_reviews_recommendations(tmp_path):
    research = ResearchService(BacktestExperimentRepository(tmp_path))
    service = StrategySelectionService(StrategySelectionRepository(tmp_path))
    as_of = date(2026, 3, 8)
    strategies = [EtfRotationStrategy(), EquityMomentumStrategy(), OptionHedgeStrategy()]

    report = research.recommend_strategy_actions(
        as_of,
        {strategy.strategy_id: strategy.generate_signals(as_of) for strategy in strategies},
    )
    result = service.review(report)

    assert len(result["updated"]) == 3
    summary = service.summary()
    assert "active" in summary
    assert "paper_only" in summary
    assert "rejected" in summary
    assert summary["active"] == []
    assert summary["paper_only"]


def test_strategy_selection_service_forces_blocked_keep_to_paper_only(tmp_path):
    service = StrategySelectionService(StrategySelectionRepository(tmp_path))
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
                "metrics": {},
                "capacity_tier": "high",
                "max_selected_correlation": 0.2,
            }
        ],
        "next_actions": [],
    }

    result = service.review(report)

    assert result["updated"][0].recommended_action == "paper_only"
    assert result["updated"][0].decision == "paper_only"
    assert result["updated"][0].selected_for_next_phase is False
    assert service.summary()["active"] == []
    assert service.summary()["paper_only"] == ["strategy_a_etf_rotation"]


def test_app_execution_signals_follow_active_strategy_selection(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()
    as_of = date(2026, 3, 8)

    report = {
        "as_of": as_of,
        "accepted_strategy_ids": ["strategy_a_etf_rotation"],
        "recommendations": [
            {
                "strategy_id": "strategy_a_etf_rotation",
                "action": "keep",
                "reasons": ["ok"],
                "metrics": {},
                "capacity_tier": "high",
                "max_selected_correlation": 0.2,
            },
            {
                "strategy_id": "strategy_b_equity_momentum",
                "action": "drop",
                "reasons": ["test drop"],
                "metrics": {},
                "capacity_tier": "medium",
                "max_selected_correlation": 0.8,
            },
        ],
        "next_actions": [],
    }
    app.selection.review(report)

    signals = app.get_signals(as_of)

    assert signals
    assert all(signal.strategy_id == "strategy_a_etf_rotation" for signal in signals)


def test_app_execution_signals_prefer_active_strategy_allocations(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()
    as_of = date(2026, 3, 8)

    recommendation_report = {
        "as_of": as_of,
        "accepted_strategy_ids": ["strategy_b_equity_momentum"],
        "recommendations": [
            {
                "strategy_id": "strategy_a_etf_rotation",
                "action": "drop",
                "reasons": ["test drop"],
                "metrics": {},
                "capacity_tier": "high",
                "max_selected_correlation": 0.8,
                "market_distribution": {"US": 1.0},
            },
            {
                "strategy_id": "strategy_b_equity_momentum",
                "action": "keep",
                "reasons": ["ok"],
                "metrics": {"sharpe": 1.5, "calmar": 1.2, "turnover": 0.8},
                "capacity_tier": "medium",
                "max_selected_correlation": 0.2,
                "market_distribution": {"HK": 0.5, "US": 0.5},
            },
        ],
        "next_actions": [],
    }
    app.selection.review(recommendation_report)
    app.allocations.review(recommendation_report)

    signals = app.get_signals(as_of)

    assert signals
    assert all(signal.strategy_id == "strategy_b_equity_momentum" for signal in signals)


def test_app_data_quality_targets_active_execution_symbols(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()
    as_of = date(2026, 3, 8)

    report = {
        "as_of": as_of,
        "accepted_strategy_ids": ["strategy_b_equity_momentum"],
        "recommendations": [
            {
                "strategy_id": "strategy_b_equity_momentum",
                "action": "keep",
                "reasons": ["ok"],
                "metrics": {"sharpe": 1.5, "calmar": 1.2, "turnover": 0.8},
                "capacity_tier": "medium",
                "max_selected_correlation": 0.2,
                "market_distribution": {"HK": 1.0},
            }
        ],
        "next_actions": [],
    }
    app.selection.review(report)
    app.allocations.review(report)

    summary = app.data_quality_summary()

    assert summary["target_symbols"] == ["0700"]
    assert summary["scope"] == "active_execution"


def test_app_data_quality_falls_back_to_research_universe_without_active_strategies(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()

    summary = app.data_quality_summary()

    assert summary["scope"] == "research_universe"
    assert summary["target_symbols"]
    assert "blockers" in summary

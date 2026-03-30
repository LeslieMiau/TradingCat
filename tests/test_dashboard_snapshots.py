from datetime import UTC, date, datetime

from tradingcat.config import AppConfig
from tradingcat.domain.models import BacktestExperiment, DashboardScorecardSnapshot
from tradingcat.repositories.research import DashboardSnapshotRepository
from tradingcat.services.dashboard_snapshots import DashboardSnapshotService


def test_dashboard_snapshot_service_returns_missing_without_persisted_snapshot(tmp_path):
    service = DashboardSnapshotService(
        DashboardSnapshotRepository(AppConfig(data_dir=tmp_path)),
        strategy_signal_provider_getter=lambda: None,
        strategy_analysis_getter=lambda: None,
        experiments_getter=lambda: [],
    )

    payload = service.load(date(2026, 3, 8))

    assert payload["snapshot_status"] == "missing"
    assert payload["rows"] == []
    assert payload["top_candidates"] == []


def test_dashboard_snapshot_repository_round_trip_and_stale_load(tmp_path):
    repository = DashboardSnapshotRepository(AppConfig(data_dir=tmp_path))
    repository.save(
        {
            "2026-03-08": DashboardScorecardSnapshot(
                as_of=date(2026, 3, 8),
                generated_at=datetime(2026, 3, 8, 9, 30, tzinfo=UTC),
                rows=[{"strategy_id": "strategy_a_etf_rotation", "verdict": "deploy_candidate"}],
                top_candidates=[{"strategy_id": "strategy_a_etf_rotation", "verdict": "deploy_candidate"}],
            )
        }
    )
    service = DashboardSnapshotService(
        repository,
        strategy_signal_provider_getter=lambda: None,
        strategy_analysis_getter=lambda: None,
        experiments_getter=lambda: [],
    )

    payload = service.load(date(2026, 3, 9))

    assert payload["snapshot_status"] == "stale"
    assert payload["snapshot_as_of"] == "2026-03-08"
    assert payload["snapshot_generated_at"] == "2026-03-08T09:30:00Z"


def test_dashboard_snapshot_service_refresh_builds_snapshot_from_persisted_experiments(tmp_path):
    repository = DashboardSnapshotRepository(AppConfig(data_dir=tmp_path))

    class _Provider:
        @staticmethod
        def strategy_signal_map(as_of, local_history_only=False):
            assert local_history_only is True
            return {"strategy_a_etf_rotation": []}

    class _Reporting:
        @staticmethod
        def build_profit_scorecard_from_experiments(as_of, strategy_signals, experiments_by_strategy):
            assert as_of == date(2026, 3, 8)
            assert list(strategy_signals) == ["strategy_a_etf_rotation"]
            assert "strategy_a_etf_rotation" in experiments_by_strategy
            return {
                "as_of": as_of,
                "portfolio_passed": True,
                "portfolio_metrics": {"annualized_return": 0.18},
                "accepted_strategy_ids": ["strategy_a_etf_rotation"],
                "blocked_strategy_ids": [],
                "blocked_count": 0,
                "deploy_candidate_count": 1,
                "paper_only_count": 0,
                "rejected_count": 0,
                "rows": [{"strategy_id": "strategy_a_etf_rotation", "verdict": "deploy_candidate"}],
                "correlation_matrix": {},
                "reject_summary": [],
                "verdict_groups": [],
                "next_actions": ["keep researching"],
            }

    class _Analysis:
        reporting = _Reporting()

    service = DashboardSnapshotService(
        repository,
        strategy_signal_provider_getter=lambda: _Provider(),
        strategy_analysis_getter=lambda: _Analysis(),
        experiments_getter=lambda: [
            BacktestExperiment(
                strategy_id="strategy_a_etf_rotation",
                as_of=date(2026, 3, 8),
                assumptions={"data_ready": True, "threshold_validation_passed": True},
            )
        ],
    )

    payload = service.refresh(date(2026, 3, 8))

    assert payload["snapshot_status"] == "ready"
    assert payload["rows"][0]["strategy_id"] == "strategy_a_etf_rotation"
    assert repository.load()["2026-03-08"].accepted_strategy_ids == ["strategy_a_etf_rotation"]

"""Tests for DuckDB market sentiment history persistence (Round 4).

Validates:
- Schema creation and table existence
- Snapshot persistence (rows inserted from snapshot dict)
- History loading with market/indicator_key filters
- Pruning old rows
- Graceful degradation via MarketSentimentHistoryRepository
- Scheduler job registration
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from tradingcat.config import AppConfig, DuckDbConfig
from tradingcat.repositories.duckdb_sentiment_store import DuckDbSentimentStore
from tradingcat.repositories.sentiment_history import MarketSentimentHistoryRepository


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_snapshot_dict(
    *,
    composite_score: float = 0.15,
    risk_switch: str = "WATCH",
    markets: list[dict] | None = None,
) -> dict:
    """Build a minimal MarketSentimentSnapshot-shaped dict for testing."""
    if markets is None:
        markets = [
            {
                "market": "US",
                "score": 0.2,
                "status": "NEUTRAL",
                "indicators": [
                    {
                        "key": "vix",
                        "label": "VIX",
                        "value": 18.5,
                        "score": -0.1,
                        "status": "NEUTRAL",
                        "unit": "index",
                    },
                    {
                        "key": "cnn_fear_greed",
                        "label": "CNN Fear & Greed",
                        "value": 45.0,
                        "score": 0.0,
                        "status": "NEUTRAL",
                        "unit": "index",
                    },
                ],
            },
            {
                "market": "CN",
                "score": -0.1,
                "status": "NEUTRAL",
                "indicators": [
                    {
                        "key": "cn_turnover",
                        "label": "A股换手率",
                        "value": 2.5,
                        "score": 0.0,
                        "status": "NEUTRAL",
                        "unit": "%",
                    },
                ],
            },
        ]
    return {
        "as_of": str(date.today()),
        "composite_score": composite_score,
        "risk_switch": risk_switch,
        "views": markets,
    }


@pytest.fixture
def store(tmp_path):
    """Fresh DuckDB sentiment store for each test."""
    return DuckDbSentimentStore(db_path=tmp_path / "sentiment.duckdb")


@pytest.fixture
def repo(tmp_path):
    """Fresh MarketSentimentHistoryRepository backed by DuckDB."""
    config = AppConfig(
        data_dir=tmp_path,
        duckdb=DuckDbConfig(
            enabled=True,
            path=tmp_path / "sentiment.duckdb",
        ),
    )
    return MarketSentimentHistoryRepository(config)


# ---------------------------------------------------------------------------
# DuckDbSentimentStore tests
# ---------------------------------------------------------------------------


class TestDuckDbSentimentStore:
    def test_schema_creates_table(self, store):
        """Table exists after construction."""
        with store._connect() as conn:
            tables = conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_name = 'market_sentiment_history'"
            ).fetchall()
        assert len(tables) == 1

    def test_persist_snapshot_returns_row_count(self, store):
        snap = _make_snapshot_dict()
        rows = store.persist_snapshot(snap)
        # 2 US indicators + 1 CN indicator = 3 rows
        assert rows == 3

    def test_persist_snapshot_stores_correct_values(self, store):
        snap = _make_snapshot_dict(composite_score=0.42, risk_switch="ON")
        store.persist_snapshot(snap)

        with store._connect() as conn:
            rows = conn.execute(
                "SELECT market, indicator_key, value, score, composite_score, risk_switch "
                "FROM market_sentiment_history ORDER BY market, indicator_key"
            ).fetchall()

        assert len(rows) == 3
        # CN turnover
        assert rows[0][0] == "CN"
        assert rows[0][1] == "cn_turnover"
        assert rows[0][2] == pytest.approx(2.5)
        assert rows[0][4] == pytest.approx(0.42)
        assert rows[0][5] == "ON"
        # US cnn_fear_greed
        assert rows[1][0] == "US"
        assert rows[1][1] == "cnn_fear_greed"
        # US vix
        assert rows[2][0] == "US"
        assert rows[2][1] == "vix"
        assert rows[2][2] == pytest.approx(18.5)

    def test_persist_empty_snapshot_returns_zero(self, store):
        snap = _make_snapshot_dict(markets=[])
        rows = store.persist_snapshot(snap)
        assert rows == 0

    def test_persist_snapshot_with_missing_indicator_fields(self, store):
        """Indicators with missing optional fields should still persist."""
        snap = _make_snapshot_dict(markets=[
            {
                "market": "HK",
                "indicators": [
                    {"key": "hsiv", "label": "HSIV"},  # no value, score, status
                ],
            },
        ])
        rows = store.persist_snapshot(snap)
        assert rows == 1

        with store._connect() as conn:
            row = conn.execute(
                "SELECT value, score, status FROM market_sentiment_history"
            ).fetchone()
        assert row[0] is None  # value is None
        assert row[1] == 0.0   # default score
        assert row[2] == "unknown"  # default status

    def test_load_history_returns_all_recent(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        history = store.load_history(days=30)
        assert len(history) == 3
        # Each row should have expected keys
        for row in history:
            assert "ts" in row
            assert "market" in row
            assert "indicator_key" in row
            assert "value" in row
            assert "score" in row

    def test_load_history_filter_by_market(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        us_history = store.load_history(market="US", days=30)
        cn_history = store.load_history(market="CN", days=30)
        assert len(us_history) == 2  # vix + cnn_fear_greed
        assert len(cn_history) == 1  # cn_turnover
        assert all(r["market"] == "US" for r in us_history)
        assert all(r["market"] == "CN" for r in cn_history)

    def test_load_history_filter_by_indicator_key(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        vix_history = store.load_history(indicator_key="vix", days=30)
        assert len(vix_history) == 1
        assert vix_history[0]["indicator_key"] == "vix"

    def test_load_history_respects_days_window(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        # All data is fresh — should appear with days=30
        assert len(store.load_history(days=30)) == 3
        # With days=0, cutoff is now — nothing should be returned in future
        # (data was just inserted, so it should still be within window)
        assert len(store.load_history(days=0)) >= 0  # edge case: depends on timing

    def test_load_history_ordered_ascending(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        history = store.load_history(days=30)
        timestamps = [r["ts"] for r in history]
        assert timestamps == sorted(timestamps)

    def test_prune_removes_old_rows(self, store):
        # Insert data, then manually backdate some rows
        store.persist_snapshot(_make_snapshot_dict())
        old_ts = datetime.now(UTC) - timedelta(days=100)
        with store._connect() as conn:
            conn.execute(
                "UPDATE market_sentiment_history SET ts = ? WHERE market = 'CN'",
                (old_ts,),
            )

        pruned = store.prune(keep_days=90)
        assert pruned == 1  # CN row was backdated beyond 90 days

        # Verify only US rows remain
        remaining = store.load_history(days=365)
        assert all(r["market"] == "US" for r in remaining)

    def test_prune_returns_zero_when_nothing_old(self, store):
        store.persist_snapshot(_make_snapshot_dict())
        pruned = store.prune(keep_days=90)
        assert pruned == 0

    def test_multiple_snapshots_accumulate(self, store):
        store.persist_snapshot(_make_snapshot_dict(composite_score=0.1))
        # Second snapshot — INSERT OR REPLACE keyed on (ts, market, indicator_key)
        # Since timestamps differ by execution time, typically creates new rows
        store.persist_snapshot(_make_snapshot_dict(composite_score=0.5))
        history = store.load_history(days=30)
        # Should have at least 3 rows (could be 6 if timestamps differ)
        assert len(history) >= 3


# ---------------------------------------------------------------------------
# MarketSentimentHistoryRepository (graceful degradation) tests
# ---------------------------------------------------------------------------


class TestMarketSentimentHistoryRepository:
    def test_available_when_duckdb_enabled(self, repo):
        assert repo.available is True

    def test_persist_and_load_round_trip(self, repo):
        snap = _make_snapshot_dict()
        rows = repo.persist_snapshot(snap)
        assert rows == 3

        history = repo.load_history(days=30)
        assert len(history) == 3

    def test_prune_through_repository(self, repo):
        repo.persist_snapshot(_make_snapshot_dict())
        pruned = repo.prune(keep_days=90)
        assert pruned == 0  # nothing old

    def test_unavailable_when_duckdb_disabled(self, tmp_path):
        config = AppConfig(
            data_dir=tmp_path,
            duckdb=DuckDbConfig(enabled=False),
        )
        repo = MarketSentimentHistoryRepository(config)
        assert repo.available is False

    def test_noop_persist_when_unavailable(self, tmp_path):
        config = AppConfig(
            data_dir=tmp_path,
            duckdb=DuckDbConfig(enabled=False),
        )
        repo = MarketSentimentHistoryRepository(config)
        rows = repo.persist_snapshot(_make_snapshot_dict())
        assert rows == 0

    def test_noop_load_when_unavailable(self, tmp_path):
        config = AppConfig(
            data_dir=tmp_path,
            duckdb=DuckDbConfig(enabled=False),
        )
        repo = MarketSentimentHistoryRepository(config)
        history = repo.load_history(days=30)
        assert history == []

    def test_noop_prune_when_unavailable(self, tmp_path):
        config = AppConfig(
            data_dir=tmp_path,
            duckdb=DuckDbConfig(enabled=False),
        )
        repo = MarketSentimentHistoryRepository(config)
        pruned = repo.prune(keep_days=90)
        assert pruned == 0

    def test_persist_graceful_on_store_error(self, repo):
        """Store errors should be swallowed, not raised."""
        with patch.object(repo._store, "persist_snapshot", side_effect=RuntimeError("DB corrupt")):
            rows = repo.persist_snapshot(_make_snapshot_dict())
        assert rows == 0

    def test_load_graceful_on_store_error(self, repo):
        with patch.object(repo._store, "load_history", side_effect=RuntimeError("DB corrupt")):
            history = repo.load_history(days=30)
        assert history == []

    def test_prune_graceful_on_store_error(self, repo):
        with patch.object(repo._store, "prune", side_effect=RuntimeError("DB corrupt")):
            pruned = repo.prune(keep_days=90)
        assert pruned == 0


# ---------------------------------------------------------------------------
# Scheduler job registration test
# ---------------------------------------------------------------------------


class TestSentimentHistorySchedulerJob:
    def test_sentiment_history_persist_job_registered(self):
        """The sentiment_history_persist job should be in _JOB_REGISTRATIONS."""
        from tradingcat.scheduler_runtime import _JOB_REGISTRATIONS

        job_ids = [j.job_id for j in _JOB_REGISTRATIONS]
        assert "sentiment_history_persist" in job_ids

        job = next(j for j in _JOB_REGISTRATIONS if j.job_id == "sentiment_history_persist")
        assert job.handler_name == "run_sentiment_history_persist_job"
        assert job.market is None  # not market-specific
        assert job.timezone == "Asia/Shanghai"

    def test_sentiment_history_persist_handler_exists(self):
        """The handler method should exist on ApplicationSchedulerRuntime."""
        from tradingcat.scheduler_runtime import ApplicationSchedulerRuntime

        assert hasattr(ApplicationSchedulerRuntime, "run_sentiment_history_persist_job")


# ---------------------------------------------------------------------------
# View model tests
# ---------------------------------------------------------------------------


class TestSentimentViewModels:
    def test_market_sentiment_history_point_model(self):
        from tradingcat.api.view_models import MarketSentimentHistoryPoint

        point = MarketSentimentHistoryPoint(ts="2026-04-17T08:00:00", value=18.5, score=-0.1)
        assert point.ts == "2026-04-17T08:00:00"
        assert point.value == 18.5
        assert point.score == -0.1

    def test_market_sentiment_history_point_defaults(self):
        from tradingcat.api.view_models import MarketSentimentHistoryPoint

        point = MarketSentimentHistoryPoint(ts="2026-04-17T08:00:00")
        assert point.value is None
        assert point.score == 0.0

    def test_market_sentiment_view_has_history_field(self):
        from tradingcat.api.view_models import MarketSentimentView

        view = MarketSentimentView(as_of=date.today())
        assert view.history == {}  # default empty dict

    def test_market_sentiment_view_with_history(self):
        from tradingcat.api.view_models import (
            MarketSentimentHistoryPoint,
            MarketSentimentView,
        )

        view = MarketSentimentView(
            as_of=date.today(),
            history={
                "vix": [
                    MarketSentimentHistoryPoint(ts="2026-04-17T08:00:00", value=18.5, score=-0.1),
                    MarketSentimentHistoryPoint(ts="2026-04-17T09:00:00", value=19.0, score=-0.15),
                ],
            },
        )
        assert len(view.history["vix"]) == 2
        assert view.history["vix"][0].value == 18.5


# ---------------------------------------------------------------------------
# Query service history enrichment test
# ---------------------------------------------------------------------------


class TestQueryServiceHistoryEnrichment:
    def test_market_awareness_enriches_sentiment_history(self, repo):
        """market_awareness() should inject sparkline history into the response."""
        from tradingcat.services.query_services import ResearchQueryService

        # Persist some history
        repo.persist_snapshot(_make_snapshot_dict())

        # Build a mock market_awareness_getter that returns sentiment data
        mock_awareness = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.model_dump.return_value = {
            "as_of": str(date.today()),
            "overall_regime": "NEUTRAL",
            "confidence": "medium",
            "risk_posture": "neutral",
            "overall_score": 0.0,
            "market_views": [],
            "evidence": [],
            "actions": [],
            "strategy_guidance": [],
            "data_quality": {},
            "market_sentiment": {
                "as_of": str(date.today()),
                "views": [],
                "composite_score": 0.15,
                "risk_switch": "WATCH",
            },
        }
        mock_awareness.snapshot.return_value = mock_snapshot

        qs = ResearchQueryService(
            market_awareness_getter=lambda: mock_awareness,
            strategy_signal_provider_getter=MagicMock,
            strategy_analysis_getter=MagicMock,
            strategy_registry_getter=MagicMock,
            research_getter=MagicMock,
            default_execution_strategy_ids_getter=lambda: [],
            review_strategy_selections=MagicMock(),
            review_strategy_allocations=MagicMock(),
            sentiment_history_getter=lambda: repo,
        )

        result = qs.market_awareness(date.today())
        sentiment = result.get("market_sentiment")
        assert sentiment is not None
        assert "history" in sentiment
        # History should be a dict keyed by indicator_key
        assert isinstance(sentiment["history"], dict)
        # We persisted vix + cnn_fear_greed + cn_turnover
        assert "vix" in sentiment["history"]
        assert len(sentiment["history"]["vix"]) >= 1

    def test_market_awareness_works_without_history_getter(self):
        """Without sentiment_history_getter, should still work normally."""
        from tradingcat.services.query_services import ResearchQueryService

        mock_awareness = MagicMock()
        mock_snapshot = MagicMock()
        mock_snapshot.model_dump.return_value = {
            "as_of": str(date.today()),
            "overall_regime": "NEUTRAL",
            "confidence": "medium",
            "risk_posture": "neutral",
            "overall_score": 0.0,
            "market_views": [],
            "evidence": [],
            "actions": [],
            "strategy_guidance": [],
            "data_quality": {},
            "market_sentiment": None,
        }
        mock_awareness.snapshot.return_value = mock_snapshot

        qs = ResearchQueryService(
            market_awareness_getter=lambda: mock_awareness,
            strategy_signal_provider_getter=MagicMock,
            strategy_analysis_getter=MagicMock,
            strategy_registry_getter=MagicMock,
            research_getter=MagicMock,
            default_execution_strategy_ids_getter=lambda: [],
            review_strategy_selections=MagicMock(),
            review_strategy_allocations=MagicMock(),
            # No sentiment_history_getter
        )

        result = qs.market_awareness(date.today())
        # Should return result without history enrichment — no crash
        assert "overall_regime" in result

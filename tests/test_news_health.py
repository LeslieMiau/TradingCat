"""Tests for news source health monitoring."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.services.news_health import NewsSourceHealthCheck, SourceHealth


class _HealthyProvider:
    source = "healthy"

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        now = datetime.now(UTC)
        return [
            {
                "source": self.source,
                "title": "Recent news",
                "published_at": now - timedelta(hours=2),
            }
        ]


class _StaleProvider:
    source = "stale"

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        old_time = datetime.now(UTC) - timedelta(hours=96)
        return [
            {
                "source": self.source,
                "title": "Old news",
                "published_at": old_time,
            }
        ]


class _OfflineProvider:
    source = "offline"

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        raise RuntimeError("Connection timeout")


def test_news_health_detects_healthy_provider():
    checker = NewsSourceHealthCheck()
    health = checker.check(_HealthyProvider())

    assert health.source == "healthy"
    assert health.online is True
    assert health.last_item_age <= timedelta(hours=3)
    assert health.is_healthy is True


def test_news_health_detects_stale_provider():
    checker = NewsSourceHealthCheck()
    health = checker.check(_StaleProvider())

    assert health.online is True
    assert health.last_item_age >= timedelta(hours=72)
    assert health.is_healthy is False  # Stale but degraded, not offline


def test_news_health_detects_offline_provider():
    checker = NewsSourceHealthCheck()
    health = checker.check(_OfflineProvider())

    assert health.source == "offline"
    assert health.online is False
    assert health.is_healthy is False


def test_news_health_tracks_consecutive_failures():
    checker = NewsSourceHealthCheck()

    # First failure
    health1 = checker.check(_OfflineProvider())
    assert health1.consecutive_failures == 1

    # Second failure (without success in between)
    health2 = checker.check(_OfflineProvider())
    assert health2.consecutive_failures == 2
    assert health2.is_healthy is False

    # Recovery
    health3 = checker.check(_HealthyProvider())
    assert health3.consecutive_failures == 0  # Reset after recovery


def test_news_health_degradation_factor():
    """Test quality weight calculation."""
    healthy = SourceHealth(source="ok", online=True, last_item_age=timedelta(hours=1))
    assert healthy.degradation_factor == 1.0

    degraded_1 = SourceHealth(source="deg1", online=True, consecutive_failures=1)
    assert degraded_1.degradation_factor == 0.5

    stale = SourceHealth(source="stale", online=True, last_item_age=timedelta(hours=48))
    assert stale.degradation_factor == 0.7

    offline = SourceHealth(source="down", online=False)
    assert offline.degradation_factor == 0.0


def test_news_health_get_healthy_sources():
    checker = NewsSourceHealthCheck()
    checker.check(_HealthyProvider())
    checker.check(_OfflineProvider())

    healthy = checker.get_healthy_sources()
    assert "healthy" in healthy
    assert "offline" not in healthy


def test_news_health_status_caching():
    checker = NewsSourceHealthCheck()
    health1 = checker.check(_HealthyProvider())
    health2 = checker.get_status("healthy")

    assert health1 == health2
    assert health2.online is True

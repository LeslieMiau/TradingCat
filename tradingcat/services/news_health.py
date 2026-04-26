"""News source health monitoring and resilience."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from time import monotonic

from tradingcat.services.news_observation import NewsFeedProvider


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceHealth:
    """Health status of a single news provider."""

    source: str
    online: bool = True
    latency_ms: float = 0.0
    last_item_age: timedelta | None = None
    last_check_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    consecutive_failures: int = 0

    @property
    def is_healthy(self) -> bool:
        """Source is healthy if online and recent items available."""
        if not self.online or self.consecutive_failures >= 2:
            return False
        if self.last_item_age is None:
            return False
        # Allow up to 72 hours of staleness before unhealthy
        return self.last_item_age <= timedelta(hours=72)

    @property
    def degradation_factor(self) -> float:
        """Weight multiplier for news filter (1.0 = full quality, 0.0 = offline)."""
        if not self.online:
            return 0.0
        if self.consecutive_failures >= 1:
            return 0.5
        if self.last_item_age and self.last_item_age > timedelta(hours=24):
            return 0.7
        return 1.0


class NewsSourceHealthCheck:
    """Monitor and track health of news providers."""

    def __init__(self, check_interval_seconds: int = 300) -> None:
        self._check_interval_seconds = max(60, int(check_interval_seconds))
        self._health: dict[str, SourceHealth] = {}
        self._last_check_time: dict[str, float] = {}

    def check(self, provider: NewsFeedProvider) -> SourceHealth:
        """Perform health check on a single provider."""
        start_time = monotonic()
        source = provider.source
        try:
            items = provider.fetch_items(limit=1)
            latency_ms = (monotonic() - start_time) * 1000
            if items and isinstance(items[0], dict):
                published_at = items[0].get("published_at")
                if published_at and isinstance(published_at, datetime):
                    age = datetime.now(UTC) - published_at.astimezone(UTC)
                else:
                    age = None
            else:
                age = timedelta(hours=24)  # Assume stale if empty
            previous = self._health.get(source)
            failures = 0 if previous is None else max(0, previous.consecutive_failures - 1)
            health = SourceHealth(
                source=source,
                online=True,
                latency_ms=latency_ms,
                last_item_age=age,
                last_check_at=datetime.now(UTC),
                consecutive_failures=failures,
            )
            logger.info(
                "News source %s healthy: latency=%.1fms age=%s",
                source,
                latency_ms,
                age if age else "unknown",
            )
        except Exception as exc:
            logger.warning("News source %s health check failed: %s", source, exc)
            previous = self._health.get(source, SourceHealth(source=source))
            health = SourceHealth(
                source=source,
                online=False,
                latency_ms=(monotonic() - start_time) * 1000,
                last_item_age=previous.last_item_age,
                last_check_at=datetime.now(UTC),
                consecutive_failures=previous.consecutive_failures + 1,
            )
        self._health[source] = health
        self._last_check_time[source] = monotonic()
        return health

    def get_status(self, source: str) -> SourceHealth | None:
        """Get cached health status for a source."""
        return self._health.get(source)

    def should_check(self, source: str) -> bool:
        """Determine if source needs re-checking based on interval."""
        last = self._last_check_time.get(source, 0.0)
        return monotonic() - last >= self._check_interval_seconds

    def get_all_status(self) -> dict[str, SourceHealth]:
        """Get health status of all monitored sources."""
        return dict(self._health)

    def get_healthy_sources(self) -> list[str]:
        """Get list of currently healthy sources."""
        return [source for source, health in self._health.items() if health.is_healthy]

    def get_degraded_sources(self) -> dict[str, SourceHealth]:
        """Get degraded (online but unhealthy) sources."""
        return {
            source: health
            for source, health in self._health.items()
            if health.online and not health.is_healthy
        }

    def get_offline_sources(self) -> dict[str, SourceHealth]:
        """Get offline sources."""
        return {source: health for source, health in self._health.items() if not health.online}

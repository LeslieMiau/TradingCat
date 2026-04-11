from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.config import AppConfig
from tradingcat.services.news_observation import NewsObservationService


class _StubProvider:
    def __init__(self, source: str, items: list[dict[str, object]], *, error: Exception | None = None) -> None:
        self.source = source
        self._items = items
        self._error = error

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        if self._error is not None:
            raise self._error
        return self._items[:limit]


def test_news_observation_deduplicates_and_keeps_ranked_items():
    now = datetime.now(UTC)
    service = NewsObservationService(
        AppConfig(),
        providers=[
            _StubProvider(
                "cn",
                [
                    {
                        "source": "cn",
                        "title": "A股 政策 刺激 市场 回升",
                        "url": "https://example.com/cn-policy",
                        "published_at": now - timedelta(hours=3),
                    },
                    {
                        "source": "cn",
                        "title": "A股 政策 刺激 市场 回升",
                        "url": "https://example.com/cn-policy",
                        "published_at": now - timedelta(hours=2),
                    },
                ],
            ),
            _StubProvider(
                "macro",
                [
                    {
                        "source": "macro",
                        "title": "Global macro risk selloff deepens",
                        "url": "https://example.com/macro-risk",
                        "published_at": now - timedelta(hours=1),
                    }
                ],
            ),
        ],
    )

    observation = service.observe()

    assert len(observation.key_items) == 2
    assert observation.key_items[0].importance >= observation.key_items[1].importance
    assert {item.title for item in observation.key_items} == {
        "A股 政策 刺激 市场 回升",
        "Global macro risk selloff deepens",
    }
    assert "policy" in observation.dominant_topics or "risk" in observation.dominant_topics
    assert observation.key_items[0].markets


def test_news_observation_returns_degraded_partial_success_when_a_feed_fails():
    now = datetime.now(UTC)
    service = NewsObservationService(
        AppConfig(),
        providers=[
            _StubProvider("broken", [], error=RuntimeError("feed offline")),
            _StubProvider(
                "macro",
                [
                    {
                        "source": "macro",
                        "title": "Fed macro policy keeps market mixed",
                        "url": "https://example.com/macro-mixed",
                        "published_at": now - timedelta(hours=4),
                    }
                ],
            ),
        ],
    )

    observation = service.observe()

    assert observation.degraded is True
    assert observation.key_items
    assert observation.blockers
    assert "broken" in observation.blockers[0]

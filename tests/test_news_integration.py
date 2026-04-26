"""Integration tests for unified news observation service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.adapters.news.providers import CLSNewsProvider, EastMoneyNewsProvider
from tradingcat.config import AppConfig
from tradingcat.services.news_observation import NewsObservationService


class _MockCLSProvider:
    """Mock CLS provider for testing."""

    def __init__(self, items: list[dict[str, object]] | None = None) -> None:
        self.source = "cls"
        self._items = items or []

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._items[:limit]


class _MockEastMoneyProvider:
    """Mock EastMoney provider for testing."""

    def __init__(self, items: list[dict[str, object]] | None = None) -> None:
        self.source = "eastmoney"
        self._items = items or []

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._items[:limit]


def test_news_observation_service_with_cls_and_eastmoney():
    """Verify CLS + EastMoney integration works."""
    now = datetime.now(UTC)
    service = NewsObservationService(
        AppConfig(),
        providers=[
            _MockCLSProvider(
                [
                    {
                        "source": "cls",
                        "title": "财联社：A股 政策 刺激 市场 回升",
                        "url": "https://www.cls.cn/detail/1",
                        "published_at": now - timedelta(hours=2),
                    },
                ]
            ),
            _MockEastMoneyProvider(
                [
                    {
                        "source": "eastmoney",
                        "title": "东方财富：半导体板块午后拉升 300308涨停",
                        "url": "https://finance.eastmoney.com/a/1.html",
                        "published_at": now - timedelta(hours=1),
                    }
                ]
            ),
        ],
    )

    observation = service.observe()

    assert len(observation.key_items) >= 1
    assert not observation.degraded or observation.key_items
    assert {item.source for item in observation.key_items} <= {"cls", "eastmoney"}


def test_news_observation_default_providers_use_cls_and_eastmoney():
    """Verify default providers are CLS and EastMoney when enabled."""
    config = AppConfig()
    config.cls_news.enabled = True
    config.eastmoney_news.enabled = True
    providers = NewsObservationService._default_providers(config)

    sources = [p.source for p in providers]
    assert "cls" in sources, "CLS provider should be in default providers"
    assert "eastmoney" in sources, "EastMoney provider should be in default providers"
    assert not any("google" in s for s in sources), "Google News should not be in default providers"


def test_news_observation_resilience_on_provider_failure():
    """Verify service works if one provider fails."""
    now = datetime.now(UTC)

    class _FailingProvider:
        source = "failing"

        def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
            raise RuntimeError("provider offline")

    service = NewsObservationService(
        AppConfig(),
        providers=[
            _FailingProvider(),
            _MockEastMoneyProvider(
                [
                    {
                        "source": "eastmoney",
                        "title": "东方财富：宏观 政策 刺激",
                        "url": "https://finance.eastmoney.com/a/2.html",
                        "published_at": now - timedelta(hours=3),
                    }
                ]
            ),
        ],
    )

    observation = service.observe()

    assert observation.degraded
    assert "failing" in observation.blockers[0]
    assert observation.key_items  # Should still have items from working provider

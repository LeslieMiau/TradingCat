"""News feed providers implementing NewsFeedProvider protocol."""

from __future__ import annotations

from tradingcat.adapters.news.alpha_vantage import AlphaVantageNewsClient
from tradingcat.adapters.news.cls import CLSNewsClient
from tradingcat.adapters.news.eastmoney import EastMoneyNewsClient
from tradingcat.adapters.news.finnhub import FinnhubNewsClient
from tradingcat.adapters.news.tushare_news import TushareNewsClient


class CLSNewsProvider:
    """Wraps CLSNewsClient as NewsFeedProvider."""

    def __init__(self, client: CLSNewsClient) -> None:
        self.source = client.source
        self._client = client

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._client.fetch_items(limit=limit)


class EastMoneyNewsProvider:
    """Wraps EastMoneyNewsClient as NewsFeedProvider."""

    def __init__(self, client: EastMoneyNewsClient) -> None:
        self.source = client.source
        self._client = client

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._client.fetch_items(limit=limit)


class FinnhubNewsProvider:
    """Wraps FinnhubNewsClient as NewsFeedProvider (conditional)."""

    def __init__(self, client: FinnhubNewsClient) -> None:
        self.source = client.source
        self._client = client

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._client.fetch_items(limit=limit)


class AlphaVantageNewsProvider:
    """Wraps AlphaVantageNewsClient as NewsFeedProvider (conditional)."""

    def __init__(self, client: AlphaVantageNewsClient) -> None:
        self.source = client.source
        self._client = client

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._client.fetch_items(limit=limit)


class TushareNewsProvider:
    """Wraps TushareNewsClient as NewsFeedProvider (official CN news)."""

    def __init__(self, client: TushareNewsClient) -> None:
        self.source = client.source
        self._client = client

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return self._client.fetch_items(limit=limit)

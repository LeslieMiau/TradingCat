"""Alpha Vantage NEWS_SENTIMENT adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from tradingcat.adapters.news.eastmoney import NewsItem
from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_ALPHA_VANTAGE_URL = "https://www.alphavantage.co/query"


class AlphaVantageNewsClient:
    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        api_key: str | None,
        tickers: list[str] | None = None,
        url: str = _ALPHA_VANTAGE_URL,
        page_size: int = 20,
        ttl_seconds: int = 900,
    ) -> None:
        self.source = "alpha_vantage"
        self._http = http or SentimentHttpClient(timeout_seconds=5.0, retries=1, default_ttl_seconds=ttl_seconds)
        self._api_key = (api_key or "").strip()
        self._tickers = [ticker.strip().upper() for ticker in (tickers or []) if ticker.strip()]
        self._url = url
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        if not self._api_key or not self._tickers:
            return []
        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        try:
            payload = self._http.get_json(
                self._url,
                params={
                    "function": "NEWS_SENTIMENT",
                    "tickers": ",".join(self._tickers),
                    "limit": str(requested),
                    "apikey": self._api_key,
                },
                ttl_seconds=self._ttl,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Alpha Vantage news fetch failure: %s", exc)
            return []
        rows = _extract_rows(payload)
        items = [_parse_item(row) for row in rows]
        return [item for item in items if item is not None][:requested]

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


def _extract_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    feed = payload.get("feed")
    if isinstance(feed, list):
        return [row for row in feed if isinstance(row, dict)]
    return []


def _parse_item(row: dict[str, Any]) -> NewsItem | None:
    title = str(row.get("title") or "").strip()
    if not title:
        return None
    url = str(row.get("url") or "").strip()
    summary = str(row.get("summary") or "").strip()
    symbols = []
    raw_ticker_sentiment = row.get("ticker_sentiment")
    if isinstance(raw_ticker_sentiment, list):
        for item in raw_ticker_sentiment:
            if isinstance(item, dict):
                ticker = str(item.get("ticker") or "").strip().upper()
                if ticker:
                    symbols.append(ticker)
    return NewsItem(
        source="alpha_vantage",
        title=title,
        url=url,
        published_at=_parse_time(row.get("time_published")),
        summary=summary,
        channel=str(row.get("source") or "alpha_vantage"),
        symbols=symbols,
        raw=dict(row),
    )


def _parse_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    for fmt in ("%Y%m%dT%H%M%S", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            continue
    return None

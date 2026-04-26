"""Finnhub company-news adapter."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradingcat.adapters.news.eastmoney import NewsItem
from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_FINNHUB_COMPANY_NEWS_URL = "https://finnhub.io/api/v1/company-news"


class FinnhubNewsClient:
    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        token: str | None,
        symbols: list[str] | None = None,
        url: str = _FINNHUB_COMPANY_NEWS_URL,
        lookback_days: int = 7,
        page_size: int = 20,
        ttl_seconds: int = 600,
    ) -> None:
        self.source = "finnhub"
        self._http = http or SentimentHttpClient(timeout_seconds=5.0, retries=1, default_ttl_seconds=ttl_seconds)
        self._token = (token or "").strip()
        self._symbols = [symbol.strip().upper() for symbol in (symbols or []) if symbol.strip()]
        self._url = url
        self._lookback_days = max(1, int(lookback_days))
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        if not self._token or not self._symbols:
            return []
        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        end = date.today()
        start = end - timedelta(days=self._lookback_days)
        items: list[NewsItem] = []
        for symbol in self._symbols:
            try:
                payload = self._http.get_json(
                    self._url,
                    params={
                        "symbol": symbol,
                        "from": start.isoformat(),
                        "to": end.isoformat(),
                        "token": self._token,
                    },
                    ttl_seconds=self._ttl,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("Finnhub news fetch failure for %s: %s", symbol, exc)
                continue
            rows = _extract_rows(payload)
            for row in rows:
                item = _parse_item(row, symbol)
                if item is not None:
                    items.append(item)
        return sorted(items, key=lambda item: item.published_at or datetime.min.replace(tzinfo=UTC), reverse=True)[:requested]

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


def _extract_rows(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if payload is None:
        return []
    data = payload.get("data", payload)
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _parse_item(row: dict[str, Any], symbol: str) -> NewsItem | None:
    title = str(row.get("headline") or row.get("title") or "").strip()
    if not title:
        return None
    url = str(row.get("url") or "").strip()
    summary = str(row.get("summary") or "").strip()
    published_at = _parse_time(row.get("datetime"))
    return NewsItem(
        source="finnhub",
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        channel=str(row.get("source") or "finnhub"),
        symbols=[symbol],
        raw=dict(row),
    )


def _parse_time(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        value = float(raw)
        if value > 10_000_000_000:
            value /= 1000.0
        return datetime.fromtimestamp(value, tz=UTC)
    text = str(raw).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)

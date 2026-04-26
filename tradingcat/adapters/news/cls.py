"""Cailian Press (CLS/财联社) news adapter."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from tradingcat.adapters.news.eastmoney import NewsItem
from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_CLS_URL = "https://www.cls.cn/api/sw"


class CLSNewsClient:
    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        url: str = _CLS_URL,
        page_size: int = 20,
        ttl_seconds: int = 300,
        user_agent: str = "Mozilla/5.0 TradingCat research bot",
    ) -> None:
        self.source = "cls"
        self._http = http or SentimentHttpClient(
            timeout_seconds=5.0,
            retries=1,
            default_ttl_seconds=ttl_seconds,
            default_headers={"User-Agent": user_agent},
        )
        self._url = url
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))
        self._user_agent = user_agent

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        params = {
            "app": "CailianpressWeb",
            "os": "web",
            "sv": "7.7.5",
            "limit": str(requested),
        }
        try:
            payload = self._http.get_json(
                self._url,
                params=params,
                headers={"User-Agent": self._user_agent},
                ttl_seconds=self._ttl,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("CLS news fetch failure: %s", exc)
            return []
        if payload is None:
            return []
        try:
            rows = _extract_rows(payload)
            items = [_parse_item(row) for row in rows]
            return [item for item in items if item is not None][:requested]
        except Exception as exc:  # noqa: BLE001
            logger.warning("CLS news parse failure: %s", exc)
            return []

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, dict):
        for key in ("roll_data", "list", "items", "data"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    return []


def _parse_item(row: dict[str, Any]) -> NewsItem | None:
    title = _first_str(row, "title", "brief", "content")
    if not title:
        return None
    url = _first_str(row, "shareurl", "url")
    ctime = row.get("ctime") or row.get("time") or row.get("publish_time")
    return NewsItem(
        source="cls",
        title=title,
        url=url,
        published_at=_parse_time(ctime),
        summary=_first_str(row, "summary", "content"),
        channel="cls",
        symbols=_extract_symbols(row),
        raw=dict(row),
    )


def _first_str(row: dict[str, Any], *keys: str) -> str:
    for key in keys:
        raw = row.get(key)
        if raw is None:
            continue
        value = str(raw).strip()
        if value and value != "-":
            return value
    return ""


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
    if text.isdigit():
        return _parse_time(int(text))
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _extract_symbols(row: dict[str, Any]) -> list[str]:
    raw = row.get("stock") or row.get("stocks") or row.get("symbols")
    if isinstance(raw, str):
        return [item.strip().upper() for item in raw.replace(";", ",").split(",") if item.strip()]
    if isinstance(raw, list):
        symbols = []
        for item in raw:
            if isinstance(item, str):
                symbols.append(item.strip().upper())
            elif isinstance(item, dict):
                symbol = _first_str(item, "symbol", "code", "secu_code")
                if symbol:
                    symbols.append(symbol.upper())
        return symbols
    return []

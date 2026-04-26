"""East Money news adapter.

East Money's public web news endpoint is used here as a research/advisory
source. The endpoint is not a trading signal source, and this adapter is not
wired into order generation or risk decisions.

Scope of this adapter (Round 05):
- Fetch a page of China market news from ``getNewsByColumns``.
- Parse common East Money JSON shapes into adapter-local ``NewsItem`` objects.
- Expose ``fetch_items`` as plain dictionaries for existing news observation
  providers.
- Return ``[]`` on HTTP, JSON, timeout, empty-data, or shape failures.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_EASTMONEY_NEWS_URL = "https://np-listapi.eastmoney.com/comm/web/getNewsByColumns"
_SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


class EastMoneyNewsUnavailable(RuntimeError):
    """Raised only for construction-time errors; fetch methods return [] on source errors."""


@dataclass(frozen=True, slots=True)
class NewsItem:
    source: str
    title: str
    url: str
    published_at: datetime | None = None
    summary: str = ""
    channel: str = "eastmoney"
    symbols: list[str] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    def as_observation_item(self) -> dict[str, object]:
        payload = asdict(self)
        payload.pop("channel", None)
        payload.pop("raw", None)
        return payload


class EastMoneyNewsClient:
    """Thin client for East Money market news.

    Args:
        http: Optional injected HTTP client. It only needs a ``get_json`` method
            with the same signature as ``SentimentHttpClient``.
        column: East Money news column id. ``"351"`` is the broad finance/news
            column used as the default because it is stable across the public
            web endpoint; callers may override as needed.
        page_size: Maximum items per fetch.
        ttl_seconds: Cache TTL passed through to the HTTP client.
        user_agent: Optional per-request User-Agent.
    """

    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        url: str = _EASTMONEY_NEWS_URL,
        column: str = "351",
        page_size: int = 20,
        ttl_seconds: int = 600,
        user_agent: str = "Mozilla/5.0 TradingCat research bot",
    ) -> None:
        self.source = "eastmoney"
        self._http = http or SentimentHttpClient(
            timeout_seconds=5.0,
            retries=1,
            default_ttl_seconds=ttl_seconds,
            default_headers={"User-Agent": user_agent},
        )
        self._url = url
        self._column = str(column)
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))
        self._user_agent = user_agent

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        params = {
            "client": "web",
            "biz": "web_news_col",
            "column": self._column,
            "order": "1",
            "needInteractData": "0",
            "page_index": "1",
            "page_size": str(requested),
            "types": "1",
        }
        try:
            payload = self._http.get_json(
                self._url,
                params=params,
                headers={"User-Agent": self._user_agent},
                ttl_seconds=self._ttl,
            )
        except Exception as exc:  # noqa: BLE001 - injected clients may raise
            logger.warning("East Money news fetch failure: %s", exc)
            return []
        if payload is None:
            return []
        try:
            rows = _extract_rows(payload)
            items = [_parse_item(row) for row in rows]
            return [item for item in items if item is not None][:requested]
        except Exception as exc:  # noqa: BLE001 - source shape is external
            logger.warning("East Money news parse failure: %s", exc)
            return []

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


def _extract_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = [
        payload.get("data"),
        (payload.get("result") or {}).get("data") if isinstance(payload.get("result"), dict) else None,
    ]
    for candidate in candidates:
        if isinstance(candidate, dict):
            for key in ("list", "news", "items", "data"):
                rows = candidate.get(key)
                if isinstance(rows, list):
                    return [row for row in rows if isinstance(row, dict)]
        if isinstance(candidate, list):
            return [row for row in candidate if isinstance(row, dict)]
    return []


def _parse_item(row: dict[str, Any]) -> NewsItem | None:
    title = _first_str(row, "title", "newsTitle", "Art_Title", "TITLE")
    if not title:
        return None
    url = _first_str(row, "url", "newsUrl", "arturl", "Art_Url", "URL")
    if not url:
        info_code = _first_str(row, "infoCode", "code", "Art_Code", "NEWS_ID")
        url = f"https://finance.eastmoney.com/a/{info_code}.html" if info_code else ""
    summary = _first_str(row, "summary", "digest", "abstract", "Art_Description", "CONTENT")
    published_at = _parse_time(_first_str(row, "showTime", "showtime", "publishTime", "Art_ShowTime", "DATE"))
    symbols = _extract_symbols(row)
    return NewsItem(
        source="eastmoney",
        title=title,
        url=url,
        published_at=published_at,
        summary=summary,
        symbols=symbols,
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


def _parse_time(raw: str) -> datetime | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
    except ValueError:
        parsed = None
    if parsed is None:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d", "%Y%m%d"):
            try:
                parsed = datetime.strptime(cleaned, fmt)
                break
            except ValueError:
                continue
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_SHANGHAI_TZ)
    return parsed.astimezone(UTC)


def _extract_symbols(row: dict[str, Any]) -> list[str]:
    raw_symbols = row.get("symbols") or row.get("stock_list") or row.get("stocks")
    if isinstance(raw_symbols, str):
        return [item.strip().upper() for item in raw_symbols.replace(";", ",").split(",") if item.strip()]
    if isinstance(raw_symbols, list):
        symbols: list[str] = []
        for item in raw_symbols:
            if isinstance(item, str):
                symbols.append(item.strip().upper())
            elif isinstance(item, dict):
                symbol = _first_str(item, "symbol", "code", "stockCode", "SECURITY_CODE")
                if symbol:
                    symbols.append(symbol.upper())
        return symbols
    return []

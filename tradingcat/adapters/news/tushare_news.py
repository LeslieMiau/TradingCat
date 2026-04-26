"""Tushare news adapter for A-share market official news."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from tradingcat.adapters.news.eastmoney import NewsItem
from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


class TushareNewsUnavailable(RuntimeError):
    """Raised when Tushare cannot provide news."""


try:
    import tushare as _tushare
    TUSHARE_AVAILABLE = True
except Exception:
    _tushare = None
    TUSHARE_AVAILABLE = False


class TushareNewsClient:
    """News client for A-share official announcements via Tushare Pro.

    Uses Tushare.news() interface for market-wide news feeds.
    Each call costs 60 积分 (points), so caching is important.
    """

    def __init__(
        self,
        *,
        token: str | None,
        tushare_module: Any | None = None,
        pro_client: Any | None = None,
        page_size: int = 20,
        ttl_seconds: int = 600,
        src: str = "",  # "" = all sources, "sina", "qq", "163", etc
    ) -> None:
        self.source = "tushare_news"
        self._token = (token or "").strip()
        self._ts = tushare_module if tushare_module is not None else _tushare
        self._pro = pro_client
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))
        self._src = src

        if not self._token and self._pro is None:
            raise TushareNewsUnavailable("Tushare token is required")
        if self._ts is None and self._pro is None:
            raise TushareNewsUnavailable("tushare module not installed")

    def _client(self) -> Any:
        """Get or initialize Tushare pro client."""
        if self._pro is not None:
            return self._pro
        try:
            self._pro = self._ts.pro_api(self._token)
        except Exception as exc:
            raise TushareNewsUnavailable(f"Failed to init Tushare pro_api: {exc}") from exc
        return self._pro

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        """Fetch A-share news from Tushare."""
        if not self._token and self._pro is None:
            return []

        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        try:
            pro = self._client()
            df = pro.news(src=self._src, limit=requested)
            if df is None or df.empty:
                return []
            items: list[NewsItem] = []
            for _, row in df.iterrows():
                item = _parse_row(row)
                if item is not None:
                    items.append(item)
            return items[:requested]
        except Exception as exc:
            logger.warning("Tushare news fetch failed: %s", exc)
            return []

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        """Return news items as dictionaries for observation service."""
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


def _parse_row(row: Any) -> NewsItem | None:
    """Parse Tushare news dataframe row."""
    title = str(row.get("title") or "").strip()
    if not title:
        return None

    url = str(row.get("url") or "").strip()
    content = str(row.get("content") or "").strip()
    src = str(row.get("src") or "tushare").strip()

    # Parse timestamp: Tushare returns "2024-01-02 10:30:00" string
    pub_time_str = str(row.get("pub_time") or "").strip()
    published_at = _parse_time(pub_time_str)

    # Extract symbols from title (e.g., "000001")
    symbols = _extract_symbols_from_title(title)

    return NewsItem(
        source="tushare_news",
        title=title,
        url=url,
        published_at=published_at,
        summary=content[:200] if content else "",
        channel=src,
        symbols=symbols,
        raw=dict(row) if hasattr(row, 'to_dict') else {},
    )


def _parse_time(raw: str) -> datetime | None:
    """Parse Tushare timestamp string."""
    if not raw:
        return None
    try:
        # Format: "2024-01-02 10:30:00"
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        logger.debug("Failed to parse Tushare timestamp: %s", raw)
        return None


def _extract_symbols_from_title(title: str) -> list[str]:
    """Extract A-share codes from title (e.g., 000001, 600000)."""
    symbols: list[str] = []
    words = title.replace("（", " ").replace("）", " ").replace("(", " ").replace(")", " ").split()
    for word in words:
        cleaned = word.strip()
        if cleaned.isdigit() and len(cleaned) == 6:
            if cleaned not in symbols:
                symbols.append(cleaned)
        if len(symbols) >= 3:
            break
    return symbols

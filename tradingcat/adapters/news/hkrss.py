"""HK financial news via RSS feeds (AAStocks, HKEX, etc.).

The default URL points to AAStocks market news. Users can override via
config to point at any RSS/Atom feed (HKEX disclosure, RTHK business, etc.).
``xml.etree.ElementTree`` is used for parsing — no additional dependencies.
"""
from __future__ import annotations

import email.utils as _email_utils
import logging
from datetime import UTC, datetime
from typing import Any
from xml.etree import ElementTree

from tradingcat.adapters.news.eastmoney import NewsItem
from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_DEFAULT_RSS_URL = "https://www.aastocks.com/tc/resources/rss.ashx"


class HkRssNewsClient:
    """RSS-fetched HK financial news client.

    Fetches and parses RSS 2.0 / Atom feeds. The default feed is AAStocks
    market news; set ``url`` to ``https://www.hkexnews.hk/rss/...`` or any
    other RSS feed to switch sources.
    """

    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        url: str = _DEFAULT_RSS_URL,
        page_size: int = 20,
        ttl_seconds: int = 600,
        user_agent: str = "Mozilla/5.0 TradingCat research bot",
        symbols: list[str] | None = None,
    ) -> None:
        self.source = "hkrss"
        self._http = http or SentimentHttpClient(
            timeout_seconds=8.0,
            retries=1,
            default_ttl_seconds=ttl_seconds,
            default_headers={"User-Agent": user_agent},
        )
        self._url = url
        self._page_size = max(1, int(page_size))
        self._ttl = max(1, int(ttl_seconds))
        self._user_agent = user_agent
        self._symbols = [s.strip().upper() for s in (symbols or []) if s.strip()]

    def fetch_news(self, *, limit: int | None = None) -> list[NewsItem]:
        requested = self._page_size if limit is None else max(1, min(int(limit), self._page_size))
        raw = self._http.get_json(
            self._url,
            headers={"User-Agent": self._user_agent},
            ttl_seconds=self._ttl,
        )
        if raw is None:
            return []

        xml_bytes: bytes | None = None
        # get_json wraps non-dict responses in {"data": ...}
        data = raw.get("data")
        if isinstance(data, bytes):
            xml_bytes = data
        elif isinstance(data, str):
            xml_bytes = data.encode("utf-8")

        if xml_bytes is None:
            return []

        return _parse_rss(xml_bytes, self._url, self._symbols)[:requested]

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]:
        return [item.as_observation_item() for item in self.fetch_news(limit=limit)]


# ---------------------------------------------------------------------------
# RSS parser (RSS 2.0 + Atom)
# ---------------------------------------------------------------------------


def _parse_rss(xml_bytes: bytes, source_url: str, known_symbols: list[str]) -> list[NewsItem]:
    try:
        root = ElementTree.fromstring(xml_bytes)
    except ElementTree.ParseError as exc:
        logger.warning("HKRSS XML parse error for %s: %s", source_url, exc)
        return []

    # Detect RSS 2.0 vs Atom
    is_atom = root.tag == "{http://www.w3.org/2005/Atom}feed"

    items: list[NewsItem] = []
    if is_atom:
        for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
            item = _parse_atom_entry(entry, known_symbols)
            if item is not None:
                items.append(item)
    else:
        channel = root.find("channel")
        if channel is None:
            return []
        for item_elem in channel.findall("item"):
            item = _parse_rss_item(item_elem, known_symbols)
            if item is not None:
                items.append(item)

    return items


def _parse_rss_item(item: ElementTree.Element, known_symbols: list[str]) -> NewsItem | None:
    title = _elem_text(item, "title")
    if not title:
        return None
    link = _elem_text(item, "link") or ""
    description = _elem_text(item, "description") or ""
    pub_date_raw = _elem_text(item, "pubDate")
    published_at = _parse_rss_date(pub_date_raw)
    return NewsItem(
        source="hkrss",
        title=title,
        url=link,
        published_at=published_at,
        summary=description,
        channel=_elem_text(item, "source") or "hkrss",
        symbols=_match_symbols(title + " " + description, known_symbols),
        raw={"title": title, "link": link, "pubDate": pub_date_raw},
    )


def _parse_atom_entry(entry: ElementTree.Element, known_symbols: list[str]) -> NewsItem | None:
    ns = "{http://www.w3.org/2005/Atom}"
    title = _elem_text(entry, f"{ns}title")
    if not title:
        return None
    link_el = entry.find(f"{ns}link")
    link = link_el.get("href", "") if link_el is not None and link_el.get("href") else ""
    summary = _elem_text(entry, f"{ns}summary") or ""
    published_raw = _elem_text(entry, f"{ns}published") or _elem_text(entry, f"{ns}updated")
    published_at = _parse_atom_date(published_raw)
    return NewsItem(
        source="hkrss",
        title=title,
        url=link,
        published_at=published_at,
        summary=summary,
        channel="hkrss",
        symbols=_match_symbols(title + " " + summary, known_symbols),
        raw={"title": title, "link": link, "published": published_raw},
    )


def _elem_text(parent: ElementTree.Element, tag: str) -> str:
    el = parent.find(tag)
    return el.text.strip() if el is not None and el.text else ""


def _parse_rss_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = _email_utils.parsedate_to_datetime(raw)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except Exception:  # noqa: BLE001
        return None


def _parse_atom_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _match_symbols(text: str, known_symbols: list[str]) -> list[str]:
    """Return known HK stock symbols found in *text*."""
    if not known_symbols:
        return []
    upper = text.upper()
    return [sym for sym in known_symbols if sym in upper]

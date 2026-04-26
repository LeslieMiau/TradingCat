"""Alternative data sources: sentiment, capital flows, macro events.

No real provider is wired here yet — fetchers return empty results when no
data source is configured. :class:`AlternativeDataService` marks each empty
source as ``degraded`` so consumers see the honest state instead of fake
data. Subclass any fetcher and override its ``fetch_*`` method to integrate
a real source. ``SentimentHttpClient`` is reused for HTTP-backed
implementations (single connection pool, TTL cache, exponential backoff).
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from tradingcat.adapters.sentiment_http import SentimentHttpClient

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data containers
# ---------------------------------------------------------------------------


@dataclass
class SocialMediaMention:
    source: str
    symbol: str
    mention_count: int
    positive_ratio: float  # 0..1
    negative_ratio: float  # 0..1
    neutral_ratio: float  # 0..1
    total_volume: float
    timestamp: datetime


@dataclass
class CapitalFlowRecord:
    market: str  # "northbound" / "southbound"
    date: date
    net_inflow: float  # CNY
    cumulative_5d: float | None = None
    cumulative_20d: float | None = None


@dataclass
class MacroEvent:
    date: date
    country: str
    event: str
    importance: Literal["high", "medium", "low"]  # noqa: F821
    previous: str | None = None
    forecast: str | None = None
    actual: str | None = None


@dataclass
class AlternativeDataSnapshot:
    """Aggregated view of all alternative data at a point in time."""

    timestamp: datetime = field(default_factory=datetime.now)
    social_media: dict[str, SocialMediaMention] = field(default_factory=dict)
    capital_flows: list[CapitalFlowRecord] = field(default_factory=list)
    macro_events: list[MacroEvent] = field(default_factory=list)
    sources_healthy: list[str] = field(default_factory=list)
    sources_degraded: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------


class SocialMediaFetcher:
    """Aggregate social-media mention data by symbol.

    No real provider is wired. If ``mock_data_path`` is given and the JSON
    file contains an entry for the requested symbol, that entry is returned;
    otherwise the symbol is omitted. Production deployments should subclass
    and override ``_fetch_single()`` to call a real provider (Brand24,
    StockTwits, etc.).
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        mock_data_path: str | Path | None = None,
    ) -> None:
        self._symbols = symbols or []
        self._mock_data_path = Path(mock_data_path) if mock_data_path else None
        self._client = SentimentHttpClient(timeout_seconds=8.0)

    def fetch(self, symbols: list[str] | None = None) -> dict[str, SocialMediaMention]:
        targets = symbols or self._symbols
        if not targets:
            return {}

        mentions: dict[str, SocialMediaMention] = {}
        for symbol in targets:
            mention = self._fetch_single(symbol)
            if mention is not None:
                mentions[symbol] = mention
        return mentions

    def _fetch_single(self, symbol: str) -> SocialMediaMention | None:
        data = self._load_mock(symbol)
        if data is None:
            return None
        return SocialMediaMention(
            source=data.get("source", "mock"),
            symbol=symbol,
            mention_count=int(data.get("mention_count", 0)),
            positive_ratio=float(data.get("positive_ratio", 0.33)),
            negative_ratio=float(data.get("negative_ratio", 0.33)),
            neutral_ratio=float(data.get("neutral_ratio", 0.34)),
            total_volume=float(data.get("total_volume", 0)),
            timestamp=datetime.now(),
        )

    def _load_mock(self, symbol: str) -> dict[str, Any] | None:
        if not self._mock_data_path or not self._mock_data_path.exists():
            return None
        try:
            store: dict[str, Any] = json.loads(self._mock_data_path.read_text())
            return store.get(symbol)
        except Exception:
            logger.exception("Failed to load mock data for %s", symbol)
            return None


class CapitalFlowFetcher:
    """Northbound / Southbound capital flows via public API sources.

    No real source is wired yet — all fetchers return ``[]``. Subclass and
    override to integrate EastMoney or Stock Connect feeds. The empty result
    causes :class:`AlternativeDataService` to mark the source ``degraded``,
    which is the honest state when nothing is configured.
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._client = SentimentHttpClient(timeout_seconds=10.0)

    def fetch_northbound(self, days: int = 20) -> list[CapitalFlowRecord]:
        return []

    def fetch_southbound(self, days: int = 20) -> list[CapitalFlowRecord]:
        return []

    def fetch_all(self, days: int = 20) -> list[CapitalFlowRecord]:
        result = self.fetch_northbound(days)
        result.extend(self.fetch_southbound(days))
        return result


class MacroEventFetcher:
    """Fetch macro-economic events from public calendars.

    No real source is wired yet — both fetchers return ``[]``. Subclass and
    override to integrate ForexFactory, Investing.com, or FRED. The empty
    result causes :class:`AlternativeDataService` to mark the source
    ``degraded``, which is the honest state when nothing is configured.
    """

    def __init__(self) -> None:
        self._client = SentimentHttpClient(timeout_seconds=8.0)

    def fetch_upcoming(self, days: int = 14) -> list[MacroEvent]:
        return []

    def fetch_recent(self, days: int = 7) -> list[MacroEvent]:
        return []


# ---------------------------------------------------------------------------
# Facade
# ---------------------------------------------------------------------------


class AlternativeDataService:
    """Aggregate all alternative data sources into a single snapshot."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        mock_data_path: str | Path | None = None,
        cache_dir: str | Path | None = None,
    ) -> None:
        self._social = SocialMediaFetcher(symbols, mock_data_path)
        self._flows = CapitalFlowFetcher(cache_dir)
        self._macro = MacroEventFetcher()

    def snapshot(
        self,
        symbols: list[str] | None = None,
        flow_days: int = 20,
        macro_days: int = 14,
    ) -> AlternativeDataSnapshot:
        sources_healthy: list[str] = []
        sources_degraded: list[str] = []

        social = self._social.fetch(symbols)
        if social:
            sources_healthy.append("social_media")
        else:
            sources_degraded.append("social_media")

        flows = self._flows.fetch_all(flow_days)
        if flows:
            sources_healthy.append("capital_flows")
        else:
            sources_degraded.append("capital_flows")

        upcoming = self._macro.fetch_upcoming(macro_days)
        if upcoming:
            sources_healthy.append("macro_events")
        else:
            sources_degraded.append("macro_events")

        return AlternativeDataSnapshot(
            social_media=social,
            capital_flows=flows,
            macro_events=upcoming,
            sources_healthy=sources_healthy,
            sources_degraded=sources_degraded,
        )

    def close(self) -> None:
        self._social._client.close()
        self._flows._client.close()
        self._macro._client.close()

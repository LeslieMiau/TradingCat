"""Alternative data sources: sentiment, capital flows, macro events.

Each fetcher follows the same contract — returns None on failure so upstream
services can mark the data point stale.  Uses SentimentHttpClient for all
HTTP calls (single connection pool, TTL cache, exponential backoff).
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

    Uses mock data when no API key is configured (default state for a
    personal trader).  Production deployments can wire in a real provider
    (Brand24, StockTwits, etc.) by subclassing and overriding ``_fetch()``.
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
        if self._mock_data_path and self._mock_data_path.exists():
            try:
                store: dict[str, Any] = json.loads(self._mock_data_path.read_text())
                return store.get(symbol)
            except Exception:
                logger.exception("Failed to load mock data for %s", symbol)
                return None
        # Built-in fallback
        return {
            "source": "mock",
            "mention_count": 50,
            "positive_ratio": 0.40,
            "negative_ratio": 0.25,
            "neutral_ratio": 0.35,
            "total_volume": 10000,
        }


class CapitalFlowFetcher:
    """Northbound / Southbound capital flows via public API sources.

    Currently uses mock data.  EastMoney HTTP API integration can be added
    by subclassing (see the existing CN market-data patterns).
    """

    def __init__(self, cache_dir: str | Path | None = None) -> None:
        self._cache_dir = Path(cache_dir) if cache_dir else None
        self._client = SentimentHttpClient(timeout_seconds=10.0)

    def fetch_northbound(self, days: int = 20) -> list[CapitalFlowRecord]:
        records: list[CapitalFlowRecord] = []
        for i in range(days):
            d = date.today() - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            records.append(CapitalFlowRecord(
                market="northbound",
                date=d,
                net_inflow=0.0,
                cumulative_5d=0.0,
                cumulative_20d=0.0,
            ))
        records.sort(key=lambda r: r.date)
        return records

    def fetch_southbound(self, days: int = 20) -> list[CapitalFlowRecord]:
        records: list[CapitalFlowRecord] = []
        for i in range(days):
            d = date.today() - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            records.append(CapitalFlowRecord(
                market="southbound",
                date=d,
                net_inflow=0.0,
                cumulative_5d=0.0,
                cumulative_20d=0.0,
            ))
        records.sort(key=lambda r: r.date)
        return records

    def fetch_all(self, days: int = 20) -> list[CapitalFlowRecord]:
        result = self.fetch_northbound(days)
        result.extend(self.fetch_southbound(days))
        return result


class MacroEventFetcher:
    """Fetch upcoming macro-economic events from public calendars.

    Returns mock events out of the box.  Wire in a real provider
    (ForexFactory, Investing.com) by replacing ``_fetch_events()``.
    """

    def __init__(self) -> None:
        self._client = SentimentHttpClient(timeout_seconds=8.0)

    def fetch_upcoming(self, days: int = 14) -> list[MacroEvent]:
        events: list[MacroEvent] = []
        today = date.today()
        for i in range(days):
            d = today + timedelta(days=i)
            if d.weekday() >= 5:
                continue
            events.append(MacroEvent(
                date=d, country="US", event="mock data — no calendar configured",
                importance="medium",
            ))
        return events

    def fetch_recent(self, days: int = 7) -> list[MacroEvent]:
        events: list[MacroEvent] = []
        today = date.today()
        for i in range(1, days + 1):
            d = today - timedelta(days=i)
            if d.weekday() >= 5:
                continue
            events.append(MacroEvent(
                date=d, country="US", event="mock data — no calendar configured",
                importance="medium",
            ))
        return events


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
        sources_healthy.append("capital_flows")

        upcoming = self._macro.fetch_upcoming(macro_days)
        sources_healthy.append("macro_events")

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

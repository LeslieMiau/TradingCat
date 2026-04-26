"""US economic calendar via the FRED API.

FRED (https://fred.stlouisfed.org/) provides free access to US economic
release dates. This module maps important releases (GDP, CPI, employment,
etc.) to :class:`MacroEvent` objects for the alternative-data pipeline.

Free tier: 120 requests/minute, no API key cost.
"""
from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_FRED_BASE = "https://api.stlouisfed.org/fred"

# Major US economic releases mapped to FRED release IDs and importance.
# Source: https://fred.stlouisfed.org/releases
_RELEASES: dict[str, dict[str, Any]] = {
    "Gross Domestic Product": {"id": 14, "importance": "high"},
    "Consumer Price Index": {"id": 11, "importance": "high"},
    "Employment Situation": {"id": 13, "importance": "high"},
    "Personal Income and Outlays": {"id": 26, "importance": "high"},
    "Producer Price Index": {"id": 18, "importance": "high"},
    "Retail Sales": {"id": 17, "importance": "high"},
    "ISM Manufacturing": {"id": 51, "importance": "high"},
    "ISM Non-Manufacturing": {"id": 52, "importance": "high"},
    "FOMC Minutes": {"id": 68, "importance": "high"},
    "Consumer Sentiment": {"id": 21, "importance": "medium"},
    "Durable Goods Orders": {"id": 22, "importance": "medium"},
    "Existing Home Sales": {"id": 20, "importance": "medium"},
    "Housing Starts": {"id": 19, "importance": "medium"},
    "Industrial Production": {"id": 15, "importance": "medium"},
    "JOLTS": {"id": 58, "importance": "medium"},
    "New Home Sales": {"id": 53, "importance": "medium"},
    "Trade Balance": {"id": 27, "importance": "medium"},
    "Employment Cost Index": {"id": 55, "importance": "medium"},
    "Construction Spending": {"id": 49, "importance": "low"},
    "Factory Orders": {"id": 50, "importance": "low"},
}


def _fred_date(d: date) -> str:
    return d.isoformat()


class FredEconomicCalendar:
    """US economic calendar backed by the FRED API.

    Fetches release dates for a curated list of major economic indicators.
    Returns :class:`MacroEvent` objects (from ``alternative.py``) that
    :class:`AlternativeDataService` folds into its snapshot.
    """

    def __init__(
        self,
        api_key: str,
        http: SentimentHttpClient | None = None,
        *,
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: int = 3600,
    ) -> None:
        self._api_key = api_key.strip()
        self._http = http or SentimentHttpClient(
            timeout_seconds=timeout_seconds,
            retries=1,
            default_ttl_seconds=cache_ttl_seconds,
            negative_ttl_seconds=120,
        )

    # ------------------------------------------------------------------
    # Public API (matches MacroEventFetcher contract)
    # ------------------------------------------------------------------

    def fetch_upcoming(self, days: int = 14) -> list[Any]:
        """Return events scheduled in the next *days*."""
        if not self._api_key:
            return []
        today = date.today()
        return self._fetch_range(today, today + timedelta(days=max(1, days)))

    def fetch_recent(self, days: int = 7) -> list[Any]:
        """Return events released in the past *days*."""
        if not self._api_key:
            return []
        today = date.today()
        return self._fetch_range(today - timedelta(days=max(1, days)), today)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _fetch_range(self, start: date, end: date) -> list[Any]:
        """Fetch MacroEvent for all tracked releases in [start, end]."""
        from tradingcat.adapters.alternative import MacroEvent

        events: list[MacroEvent] = []
        for name, info in _RELEASES.items():
            release_events = self._fetch_release_dates(
                release_id=info["id"],
                name=name,
                importance=info["importance"],
                start=start,
                end=end,
            )
            events.extend(release_events)
        events.sort(key=lambda e: e.date)
        return events

    def _fetch_release_dates(
        self,
        release_id: int,
        name: str,
        importance: str,
        start: date,
        end: date,
    ) -> list[Any]:
        from tradingcat.adapters.alternative import MacroEvent

        params: dict[str, Any] = {
            "release_id": str(release_id),
            "api_key": self._api_key,
            "file_type": "json",
            "include_release_dates_with_no_data": "true",
            "sort_order": "asc",
            "observation_start": _fred_date(start),
            "observation_end": _fred_date(end),
        }
        url = f"{_FRED_BASE}/release/dates"
        payload = self._http.get_json(url, params=params)
        if payload is None:
            return []

        rows = payload.get("release_dates")
        if not isinstance(rows, list):
            return []

        events: list[MacroEvent] = []
        for row in rows:
            raw_date = row.get("date")
            if not raw_date:
                continue
            try:
                event_date = date.fromisoformat(raw_date)
            except (ValueError, TypeError):
                continue
            # The release date might be from another real-time period;
            # trust FRED's date over our window
            if not (start <= event_date <= end):
                continue
            events.append(
                MacroEvent(
                    date=event_date,
                    country="US",
                    event=name,
                    importance=importance,
                )
            )
        return events

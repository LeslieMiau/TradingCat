from __future__ import annotations

import hashlib
import json
import logging
import urllib.request
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pydantic import BaseModel

from tradingcat.config import AppConfig

logger = logging.getLogger(__name__)

# ── Public calendar API (no key required) ────────────────────────
# We pull from the Nager.Date public holiday API for major-market holidays
# and maintain a curated list of recurring macro events with known schedules.
# For richer feeds, set TRADINGCAT_MACRO_CALENDAR_URL to any JSON endpoint
# that returns [{time, country, event, impact, forecast, previous}, ...].
_DEFAULT_CALENDAR_URL = "https://nager.date/api/v3/NextPublicHolidays/US"
_CACHE_TTL_SECONDS = 3600  # re-fetch at most once per hour


class MacroEvent(BaseModel):
    id: str
    time: str
    country: str
    event: str
    impact: str  # High, Medium, Low
    forecast: str
    previous: str


# ── Known recurring macro events (date-relative, always available) ─
_RECURRING_EVENTS: list[dict] = [
    {"weekday": 4, "hour": 8, "minute": 30, "country": "US",
     "event": "Initial Jobless Claims", "impact": "Medium"},
    {"day": 1, "hour": 10, "minute": 0, "country": "CN",
     "event": "Caixin Manufacturing PMI", "impact": "High"},
    {"day": 3, "hour": 10, "minute": 0, "country": "US",
     "event": "ISM Non-Manufacturing PMI", "impact": "Medium"},
]


def _event_id(country: str, event: str, time_str: str) -> str:
    return hashlib.sha1(f"{country}:{event}:{time_str}".encode()).hexdigest()[:12]


def _build_recurring_events(now: datetime, days: int) -> list[MacroEvent]:
    """Generate upcoming instances of known recurring macro events."""
    events: list[MacroEvent] = []
    for offset in range(days + 1):
        target = now + timedelta(days=offset)
        for spec in _RECURRING_EVENTS:
            match = False
            if "weekday" in spec and target.weekday() == spec["weekday"]:
                match = True
            elif "day" in spec and target.day == spec["day"]:
                match = True
            if not match:
                continue
            t = target.replace(
                hour=spec.get("hour", 10), minute=spec.get("minute", 0),
                second=0, microsecond=0,
            )
            ts = t.strftime("%Y-%m-%dT%H:%M:%SZ")
            events.append(MacroEvent(
                id=_event_id(spec["country"], spec["event"], ts),
                time=ts, country=spec["country"], event=spec["event"],
                impact=spec["impact"], forecast="—", previous="—",
            ))
    return events


class MacroCalendarService:
    """Macro calendar with live fetch + local cache + recurring-event fallback."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config
        self._cache: list[MacroEvent] | None = None
        self._cache_time: float = 0.0
        data_dir = Path(config.data_dir) if config else Path("data")
        self._cache_file = data_dir / "macro_calendar_cache.json"
        self._calendar_url: str = (
            _DEFAULT_CALENDAR_URL
            if config is None
            else getattr(config, "macro_calendar_url", _DEFAULT_CALENDAR_URL) or _DEFAULT_CALENDAR_URL
        )

    # ── Public API ────────────────────────────────────────────────
    def fetch_upcoming_events(self, days: int = 7) -> list[MacroEvent]:
        now = datetime.now(timezone.utc)

        # 1. Try live fetch (with TTL-based caching)
        live_events = self._fetch_live(now, days)

        # 2. Always include recurring-event baseline
        recurring = _build_recurring_events(now, days)

        # 3. Merge: live events take priority (by event name+country dedup)
        seen: set[str] = set()
        merged: list[MacroEvent] = []
        for evt in live_events:
            key = f"{evt.country}:{evt.event}"
            if key not in seen:
                seen.add(key)
                merged.append(evt)
        for evt in recurring:
            key = f"{evt.country}:{evt.event}"
            if key not in seen:
                seen.add(key)
                merged.append(evt)

        return sorted(merged, key=lambda x: x.time)

    # ── Live fetch with cache ─────────────────────────────────────
    def _fetch_live(self, now: datetime, days: int) -> list[MacroEvent]:
        now_ts = now.timestamp()
        if self._cache is not None and (now_ts - self._cache_time) < _CACHE_TTL_SECONDS:
            return self._cache

        events = self._try_remote_fetch(now, days)
        if events is None:
            events = self._load_disk_cache()
        if events is None:
            events = []

        self._cache = events
        self._cache_time = now_ts
        self._save_disk_cache(events)
        return events

    def _try_remote_fetch(self, now: datetime, days: int) -> list[MacroEvent] | None:
        """Fetch from remote calendar URL. Returns None on failure."""
        try:
            req = urllib.request.Request(
                self._calendar_url,
                headers={"User-Agent": "TradingCat/1.0", "Accept": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw = json.loads(resp.read().decode("utf-8"))
        except (urllib.error.URLError, OSError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("macro calendar fetch failed: %s", exc)
            return None

        events: list[MacroEvent] = []
        if isinstance(raw, list):
            for item in raw:
                evt = self._parse_remote_item(item)
                if evt is not None:
                    events.append(evt)
        return events

    @staticmethod
    def _parse_remote_item(item: dict) -> MacroEvent | None:
        """Parse a single calendar item from the remote API.

        Supports two formats:
        - Nager.Date public holidays: {date, countryCode, name, ...}
        - Generic macro calendar: {time, country, event, impact, forecast, previous}
        """
        try:
            # Generic format (e.g. custom macro calendar endpoint)
            if "event" in item and "time" in item:
                ts = item["time"]
                country = item.get("country", "US")
                event_name = item["event"]
                return MacroEvent(
                    id=_event_id(country, event_name, ts),
                    time=ts,
                    country=country,
                    event=event_name,
                    impact=item.get("impact", "Medium"),
                    forecast=item.get("forecast", "—"),
                    previous=item.get("previous", "—"),
                )

            # Nager.Date format
            if "date" in item and "name" in item:
                date_str = item["date"]
                country = item.get("countryCode", "US")
                event_name = f"Holiday: {item['name']}"
                ts = f"{date_str}T00:00:00Z"
                return MacroEvent(
                    id=_event_id(country, event_name, ts),
                    time=ts,
                    country=country,
                    event=event_name,
                    impact="Low",
                    forecast="—",
                    previous="—",
                )
        except (KeyError, TypeError, ValueError):
            pass
        return None

    # ── Disk cache for offline resilience ─────────────────────────
    def _load_disk_cache(self) -> list[MacroEvent] | None:
        if not self._cache_file.exists():
            return None
        try:
            raw = json.loads(self._cache_file.read_text(encoding="utf-8"))
            return [MacroEvent(**item) for item in raw]
        except (json.JSONDecodeError, TypeError, KeyError):
            return None

    def _save_disk_cache(self, events: list[MacroEvent]) -> None:
        try:
            self._cache_file.parent.mkdir(parents=True, exist_ok=True)
            self._cache_file.write_text(
                json.dumps([e.model_dump() for e in events], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("failed to write macro calendar cache: %s", exc)

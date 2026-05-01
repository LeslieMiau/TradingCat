from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from tradingcat.domain.models import Market, MarketSession


class StaticHolidayCalendar:
    """Auditable built-in exchange calendar snapshot for 2026.

    Sources are kept in the returned MarketSession so live-readiness code can
    distinguish explicit calendar knowledge from a simple weekday fallback.
    """

    _SOURCE = {
        Market.CN: "SSE/SZSE 2026 public holiday static snapshot",
        Market.HK: "HKEX 2026 public holiday static snapshot",
        Market.US: "NYSE 2026 holiday and early-close static snapshot",
    }
    _HOLIDAYS_2026: dict[Market, dict[date, str]] = {
        Market.CN: {
            date(2026, 1, 1): "New Year's Day",
            date(2026, 1, 28): "Spring Festival Eve",
            date(2026, 1, 29): "Spring Festival",
            date(2026, 1, 30): "Spring Festival",
            date(2026, 2, 2): "Spring Festival",
            date(2026, 2, 3): "Spring Festival",
            date(2026, 4, 6): "Qingming observed",
            date(2026, 5, 1): "Labour Day",
            date(2026, 5, 4): "Labour Day observed",
            date(2026, 5, 5): "Labour Day observed",
            date(2026, 6, 19): "Dragon Boat Festival",
            date(2026, 9, 25): "Mid-Autumn Festival",
            date(2026, 10, 1): "National Day",
            date(2026, 10, 2): "National Day",
            date(2026, 10, 5): "National Day",
            date(2026, 10, 6): "National Day",
            date(2026, 10, 7): "National Day",
            date(2026, 10, 8): "National Day",
        },
        Market.HK: {
            date(2026, 1, 1): "New Year's Day",
            date(2026, 2, 17): "Lunar New Year",
            date(2026, 2, 18): "Lunar New Year",
            date(2026, 2, 19): "Lunar New Year",
            date(2026, 4, 3): "Good Friday",
            date(2026, 4, 6): "Easter Monday",
            date(2026, 4, 7): "Ching Ming observed",
            date(2026, 5, 1): "Labour Day",
            date(2026, 5, 25): "Buddha's Birthday",
            date(2026, 6, 19): "Tuen Ng Festival",
            date(2026, 7, 1): "Hong Kong SAR Establishment Day",
            date(2026, 9, 26): "Mid-Autumn Festival day after",
            date(2026, 10, 1): "National Day",
            date(2026, 10, 19): "Chung Yeung Festival",
            date(2026, 12, 25): "Christmas Day",
            date(2026, 12, 28): "Boxing Day observed",
        },
        Market.US: {
            date(2026, 1, 1): "New Year's Day",
            date(2026, 1, 19): "Martin Luther King Jr. Day",
            date(2026, 2, 16): "Washington's Birthday",
            date(2026, 4, 3): "Good Friday",
            date(2026, 5, 25): "Memorial Day",
            date(2026, 6, 19): "Juneteenth",
            date(2026, 7, 3): "Independence Day observed",
            date(2026, 9, 7): "Labor Day",
            date(2026, 11, 26): "Thanksgiving Day",
            date(2026, 12, 25): "Christmas Day",
        },
    }
    _HALF_DAY_CLOSES_2026: dict[Market, dict[date, time]] = {
        Market.US: {
            date(2026, 11, 27): time(13, 0),
            date(2026, 12, 24): time(13, 0),
        },
        Market.HK: {
            date(2026, 12, 24): time(12, 0),
            date(2026, 12, 31): time(12, 0),
        },
    }

    @classmethod
    def source(cls, market: Market) -> str:
        return cls._SOURCE[market]

    @classmethod
    def holiday_name(cls, market: Market, d: date) -> str | None:
        return cls._HOLIDAYS_2026.get(market, {}).get(d)

    @classmethod
    def half_day_close(cls, market: Market, d: date) -> time | None:
        return cls._HALF_DAY_CLOSES_2026.get(market, {}).get(d)

    @classmethod
    def is_holiday(cls, market: Market, d: date) -> bool:
        return cls.holiday_name(market, d) is not None

    @classmethod
    def has_explicit_year(cls, d: date) -> bool:
        return d.year == 2026


class MarketCalendarService:
    _market_config = {
        Market.US: {"timezone": "America/New_York", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.HK: {"timezone": "Asia/Hong_Kong", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.CN: {"timezone": "Asia/Shanghai", "open_time": time(9, 30), "close_time": time(15, 0)},
    }

    @staticmethod
    def _is_trading_day(market: Market, local_date: date) -> bool:
        if not StaticHolidayCalendar.has_explicit_year(local_date):
            return False
        if local_date.weekday() >= 5:
            return False
        if StaticHolidayCalendar.is_holiday(market, local_date):
            return False
        return True

    def get_session(self, market: Market, now: datetime | None = None) -> MarketSession:
        config = self._market_config[market]
        tz = ZoneInfo(config["timezone"])
        current = now.astimezone(tz) if now else datetime.now(tz)
        local_now = current.timetz().replace(tzinfo=None)
        calendar_available = StaticHolidayCalendar.has_explicit_year(current.date())
        is_trading_day = self._is_trading_day(market, current.date()) if calendar_available else False
        holiday_name = StaticHolidayCalendar.holiday_name(market, current.date())
        close_time = StaticHolidayCalendar.half_day_close(market, current.date()) or config["close_time"]
        breaks = self._breaks_for_market(market)
        in_break = self._in_break(local_now, breaks)
        if not calendar_available:
            phase = "closed"
        elif not is_trading_day or local_now >= close_time:
            phase = "closed"
        elif local_now < config["open_time"]:
            phase = "pre_open"
        elif in_break:
            phase = "break"
        else:
            phase = "open"
        return MarketSession(
            market=market,
            timezone=config["timezone"],
            local_date=current.date(),
            open_time=config["open_time"],
            close_time=close_time,
            is_trading_day=is_trading_day,
            phase=phase,
            session_type=(
                "calendar_unavailable"
                if not calendar_available
                else "holiday"
                if holiday_name
                else ("half_day" if close_time != config["close_time"] else "regular")
            ),
            calendar_source=StaticHolidayCalendar.source(market),
            calendar_note=holiday_name or (None if calendar_available else "No explicit exchange calendar snapshot is loaded for this year."),
            breaks=breaks,
        )

    def next_run_utc(self, market: Market, local_time: time, after: datetime | None = None) -> datetime:
        config = self._market_config[market]
        tz = ZoneInfo(config["timezone"])
        anchor = after.astimezone(tz) if after else datetime.now(tz)
        local_candidate = datetime.combine(anchor.date(), local_time, tzinfo=tz)
        if local_candidate <= anchor:
            local_candidate = local_candidate + timedelta(days=1)
        attempts = 0
        while not self._is_trading_day(market, local_candidate.date()):
            local_candidate = local_candidate + timedelta(days=1)
            attempts += 1
            if attempts > 370:
                raise ValueError(f"No explicit trading calendar is available after {anchor.date().isoformat()}")
        return local_candidate.astimezone(UTC)

    @staticmethod
    def _breaks_for_market(market: Market) -> list[dict[str, str]]:
        return [{"start": "11:30", "end": "13:00"}] if market in {Market.CN, Market.HK} else []

    @staticmethod
    def _in_break(local_now: time, breaks: list[dict[str, str]]) -> bool:
        for row in breaks:
            try:
                start = time.fromisoformat(str(row["start"]))
                end = time.fromisoformat(str(row["end"]))
            except (KeyError, ValueError):
                continue
            if start <= local_now < end:
                return True
        return False

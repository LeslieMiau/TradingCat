from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, time
from zoneinfo import ZoneInfo

from tradingcat.domain.models import Market, MarketSession


class ChinaHolidayCalendar:
    """CN market holiday calendar. Source: 中国政府网公布的节假日安排 (approximate for 2026)."""

    _HOLIDAYS_2026: frozenset[date] = frozenset({
        date(2026, 1, 1),   # 元旦
        date(2026, 1, 28),  # 除夕
        date(2026, 1, 29),  # 初一
        date(2026, 1, 30),  # 初二
        date(2026, 2, 2),   # 初五
        date(2026, 2, 3),   # 初六
        date(2026, 4, 6),   # 清明 (调休)
        date(2026, 5, 1),   # 劳动节
        date(2026, 5, 4),   # 劳动节调休
        date(2026, 5, 5),   # 劳动节调休
        date(2026, 6, 19),  # 端午
        date(2026, 9, 25),  # 中秋
        date(2026, 10, 1),  # 国庆
        date(2026, 10, 2),  # 国庆
        date(2026, 10, 5),  # 国庆
        date(2026, 10, 6),  # 国庆
        date(2026, 10, 7),  # 国庆
        date(2026, 10, 8),  # 国庆
    })

    @classmethod
    def is_holiday(cls, d: date) -> bool:
        return d in cls._HOLIDAYS_2026


class MarketCalendarService:
    _market_config = {
        Market.US: {"timezone": "America/New_York", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.HK: {"timezone": "Asia/Hong_Kong", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.CN: {"timezone": "Asia/Shanghai", "open_time": time(9, 30), "close_time": time(15, 0)},
    }

    @staticmethod
    def _is_trading_day(market: Market, local_date: date) -> bool:
        if local_date.weekday() >= 5:
            return False
        if market == Market.CN and ChinaHolidayCalendar.is_holiday(local_date):
            return False
        return True

    def get_session(self, market: Market, now: datetime | None = None) -> MarketSession:
        config = self._market_config[market]
        tz = ZoneInfo(config["timezone"])
        current = now.astimezone(tz) if now else datetime.now(tz)
        local_now = current.timetz().replace(tzinfo=None)
        is_trading_day = self._is_trading_day(market, current.date())
        if not is_trading_day or local_now >= config["close_time"]:
            phase = "closed"
        elif local_now < config["open_time"]:
            phase = "pre_open"
        else:
            phase = "open"
        return MarketSession(
            market=market,
            timezone=config["timezone"],
            local_date=current.date(),
            open_time=config["open_time"],
            close_time=config["close_time"],
            is_trading_day=is_trading_day,
            phase=phase,
        )

    def next_run_utc(self, market: Market, local_time: time, after: datetime | None = None) -> datetime:
        config = self._market_config[market]
        tz = ZoneInfo(config["timezone"])
        anchor = after.astimezone(tz) if after else datetime.now(tz)
        local_candidate = datetime.combine(anchor.date(), local_time, tzinfo=tz)
        if local_candidate <= anchor:
            local_candidate = local_candidate + timedelta(days=1)
        while not self._is_trading_day(market, local_candidate.date()):
            local_candidate = local_candidate + timedelta(days=1)
        return local_candidate.astimezone(UTC)

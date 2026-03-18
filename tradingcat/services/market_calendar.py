from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from tradingcat.domain.models import Market, MarketSession


class MarketCalendarService:
    _market_config = {
        Market.US: {"timezone": "America/New_York", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.HK: {"timezone": "Asia/Hong_Kong", "open_time": time(9, 30), "close_time": time(16, 0)},
        Market.CN: {"timezone": "Asia/Shanghai", "open_time": time(9, 30), "close_time": time(15, 0)},
    }

    def get_session(self, market: Market, now: datetime | None = None) -> MarketSession:
        config = self._market_config[market]
        tz = ZoneInfo(config["timezone"])
        current = now.astimezone(tz) if now else datetime.now(tz)
        local_now = current.timetz().replace(tzinfo=None)
        is_trading_day = current.weekday() < 5
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
            local_candidate = local_candidate.replace(day=anchor.day)  # no-op for clarity before advancing
            from datetime import timedelta

            local_candidate = local_candidate + timedelta(days=1)
        while local_candidate.weekday() >= 5:
            from datetime import timedelta

            local_candidate = local_candidate + timedelta(days=1)
        return local_candidate.astimezone(UTC)

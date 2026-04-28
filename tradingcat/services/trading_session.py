from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from enum import Enum
from typing import TYPE_CHECKING

from tradingcat.domain.models import Market, MarketSession

if TYPE_CHECKING:
    from tradingcat.services.market_calendar import MarketCalendarService


class TradingPhase(str, Enum):
    SLEEP = "sleep"
    PRE_MARKET = "pre_market"
    OPENING = "opening"
    INTRADAY = "intraday"
    CLOSING = "closing"
    POST_MARKET = "post_market"


@dataclass(frozen=True)
class TradingSession:
    phase: TradingPhase
    market: Market
    local_date: date
    underlying_session: MarketSession


class TradingSessionService:
    """Builds on MarketCalendarService to provide finer-grained trading phases.

    Phase derivation rules (applied on top of MarketCalendarService.get_session()):

        base_phase=pre_open  & min_to_open >  window  → SLEEP
        base_phase=pre_open  & min_to_open <= window  → PRE_MARKET
        base_phase=open      & min_from_open <  window → OPENING
        base_phase=open      & min_to_close  <= window → CLOSING
        base_phase=open      & otherwise               → INTRADAY
        base_phase=closed    & is_trading_day          → POST_MARKET
        base_phase=closed    & not is_trading_day      → SLEEP
    """

    def __init__(
        self,
        calendar: MarketCalendarService,
        *,
        opening_window_minutes: int = 30,
        closing_window_minutes: int = 30,
    ) -> None:
        self._calendar = calendar
        self._opening_window = opening_window_minutes
        self._closing_window = closing_window_minutes

    def get_phase(self, market: Market, now: datetime | None = None) -> TradingSession:
        base = self._calendar.get_session(market, now)
        resolved_now = (now or datetime.now(UTC)).astimezone(
            self._tz(base.timezone)
        )
        local_time = resolved_now.timetz().replace(tzinfo=None)

        if base.phase == "pre_open":
            min_to_open = minutes_between(local_time, base.open_time)
            phase = TradingPhase.PRE_MARKET if min_to_open <= self._opening_window else TradingPhase.SLEEP
        elif base.phase == "open":
            min_from_open = minutes_between(base.open_time, local_time)
            min_to_close = minutes_between(local_time, base.close_time)
            if min_from_open < self._opening_window:
                phase = TradingPhase.OPENING
            elif min_to_close <= self._closing_window:
                phase = TradingPhase.CLOSING
            else:
                phase = TradingPhase.INTRADAY
        else:
            phase = TradingPhase.POST_MARKET if base.is_trading_day else TradingPhase.SLEEP

        return TradingSession(phase=phase, market=market, local_date=base.local_date, underlying_session=base)

    @staticmethod
    def _tz(tz_name: str):
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)


def minutes_between(a: time, b: time) -> int:
    """Positive minutes from time *a* to time *b* (wrapping at midnight)."""
    a_min = a.hour * 60 + a.minute
    b_min = b.hour * 60 + b.minute
    if b_min >= a_min:
        return b_min - a_min
    return (1440 - a_min) + b_min

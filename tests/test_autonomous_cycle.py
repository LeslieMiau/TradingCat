"""Tests for autonomous daily-cycle services."""

from __future__ import annotations

from datetime import date, datetime, time
from zoneinfo import ZoneInfo

import pytest

from tradingcat.domain.models import Market, MarketSession
from tradingcat.services.trading_session import TradingPhase, TradingSessionService


# ---------------------------------------------------------------------------
# TradingSessionService
# ---------------------------------------------------------------------------


class _FakeCalendar:
    """Returns a MarketSession for any given (market, now) pair provided via
    a side-effect dict keyed by (market, iso_timestamp)."""

    def __init__(self, sessions: dict[tuple, MarketSession]) -> None:
        self._sessions = sessions

    def get_session(self, market: Market, now: datetime | None = None) -> MarketSession:
        key = (market, now.isoformat() if now else "default")
        if key not in self._sessions:
            msg = f"no fake session for {key}"
            raise KeyError(msg)
        return self._sessions[key]


def _session(phase: str, is_trading_day: bool = True, local: str = "Asia/Shanghai") -> MarketSession:
    return MarketSession(
        market=Market.CN,
        timezone=local,
        local_date=date(2026, 4, 27),
        open_time=time(9, 30),
        close_time=time(15, 0),
        is_trading_day=is_trading_day,
        phase=phase,
    )


def _cst(h: int, m: int) -> datetime:
    return datetime(2026, 4, 27, h, m, tzinfo=ZoneInfo("Asia/Shanghai"))


class TestTradingSessionService:
    @pytest.fixture
    def service(self):
        cal = _FakeCalendar({})
        return TradingSessionService(cal, opening_window_minutes=30, closing_window_minutes=30)

    @pytest.mark.parametrize(
        ("base_phase", "is_trading", "hour_min", "expected"),
        [
            ("pre_open", True, (0, 30), TradingPhase.SLEEP),
            ("pre_open", True, (8, 29), TradingPhase.SLEEP),
            ("pre_open", True, (9, 0), TradingPhase.PRE_MARKET),
            ("pre_open", True, (9, 29), TradingPhase.PRE_MARKET),
            ("open", True, (9, 30), TradingPhase.OPENING),
            ("open", True, (9, 45), TradingPhase.OPENING),
            ("open", True, (9, 59), TradingPhase.OPENING),
            ("open", True, (10, 0), TradingPhase.INTRADAY),
            ("open", True, (13, 0), TradingPhase.INTRADAY),
            ("open", True, (14, 29), TradingPhase.INTRADAY),
            ("open", True, (14, 30), TradingPhase.CLOSING),
            ("open", True, (14, 45), TradingPhase.CLOSING),
            ("open", True, (14, 59), TradingPhase.CLOSING),
            ("closed", True, (15, 1), TradingPhase.POST_MARKET),
            ("closed", True, (20, 0), TradingPhase.POST_MARKET),
            ("closed", False, (10, 0), TradingPhase.SLEEP),
            ("closed", False, (23, 59), TradingPhase.SLEEP),
        ],
    )
    def test_phase_derivation(self, service, base_phase, is_trading, hour_min, expected):
        h, m = hour_min
        now = _cst(h, m)
        service._calendar.get_session = lambda mkt, n=None: _session(base_phase, is_trading_day=is_trading)

        result = service.get_phase(Market.CN, now=now)
        assert result.phase == expected, f"base={base_phase} is_trading={is_trading} now={now} -> {expected}"

    def test_custom_windows(self):
        cal = _FakeCalendar({})
        svc = TradingSessionService(cal, opening_window_minutes=15, closing_window_minutes=45)
        svc._calendar.get_session = lambda m, n=None: _session("open")

        assert svc.get_phase(Market.CN, now=_cst(9, 40)).phase == TradingPhase.OPENING
        assert svc.get_phase(Market.CN, now=_cst(9, 46)).phase == TradingPhase.INTRADAY
        assert svc.get_phase(Market.CN, now=_cst(14, 20)).phase == TradingPhase.CLOSING

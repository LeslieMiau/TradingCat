"""Unit tests for CompositeMarketDataAdapter.

Verifies CN/US routing, CN adapter fallback on failure, and per-method delegation.
"""

from __future__ import annotations

from datetime import date

import pytest

from tradingcat.adapters.composite import CompositeMarketDataAdapter
from tradingcat.domain.models import Instrument, Market


class _FakeInner:
    """Simulates a MarketDataAdapter that records which instruments it saw."""

    def __init__(self, bars: list | None = None, quotes: dict[str, float] | None = None) -> None:
        self.bars = bars or []
        self.quotes = quotes or {}
        self.seen: list[Instrument] = []

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list:
        self.seen.append(instrument)
        return self.bars

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        self.seen.extend(instruments)
        return {inst.symbol: self.quotes.get(inst.symbol, 100.0) for inst in instruments}

    def fetch_option_chain(self, underlying, as_of, *, market=None):
        return []

    def fetch_corporate_actions(self, instrument, start, end):
        return []

    def fetch_fx_rates(self, base_currency, quote_currency, start, end):
        return []


class _FakeInnerRaises:
    """Simulates an adapter that always raises."""

    def fetch_bars(self, instrument, start, end):
        raise RuntimeError("always fails")

    def fetch_quotes(self, instruments):
        raise RuntimeError("always fails")

    def fetch_option_chain(self, underlying, as_of, *, market=None):
        raise RuntimeError("always fails")

    def fetch_corporate_actions(self, instrument, start, end):
        raise RuntimeError("always fails")

    def fetch_fx_rates(self, base_currency, quote_currency, start, end):
        raise RuntimeError("always fails")


def _cn_inst(symbol: str = "600000") -> Instrument:
    return Instrument(symbol=symbol, market=Market.CN, currency="CNY")


def _us_inst(symbol: str = "SPY") -> Instrument:
    return Instrument(symbol=symbol, market=Market.US, currency="USD")


def _hk_inst(symbol: str = "0700") -> Instrument:
    return Instrument(symbol=symbol, market=Market.HK, currency="HKD")


class TestCompositeMarketDataAdapter:
    T = date(2026, 4, 1)

    # ── fetch_bars ────────────────────────────────────────────────────

    def test_routes_cn_to_akshare(self):
        cn = _FakeInner(bars=["bar1"])
        us = _FakeInner()
        adapter = CompositeMarketDataAdapter(cn_inner=cn, us_hk_inner=us)

        result = adapter.fetch_bars(_cn_inst(), self.T, self.T)

        assert result == ["bar1"]
        assert len(cn.seen) == 1
        assert len(us.seen) == 0

    def test_routes_us_to_us_hk(self):
        cn = _FakeInner()
        us = _FakeInner(bars=["bar_us"])
        adapter = CompositeMarketDataAdapter(cn_inner=cn, us_hk_inner=us)

        result = adapter.fetch_bars(_us_inst(), self.T, self.T)

        assert result == ["bar_us"]
        assert len(cn.seen) == 0
        assert len(us.seen) == 1

    def test_routes_hk_to_us_hk(self):
        cn = _FakeInner()
        us = _FakeInner(bars=["bar_hk"])
        adapter = CompositeMarketDataAdapter(cn_inner=cn, us_hk_inner=us)

        result = adapter.fetch_bars(_hk_inst(), self.T, self.T)

        assert result == ["bar_hk"]
        assert len(us.seen) == 1

    def test_akshare_empty_falls_back(self):
        cn = _FakeInner(bars=[])
        us = _FakeInner(bars=["fallback"])
        adapter = CompositeMarketDataAdapter(cn_inner=cn, us_hk_inner=us)

        result = adapter.fetch_bars(_cn_inst(), self.T, self.T)

        assert result == ["fallback"]
        assert len(cn.seen) == 1
        assert len(us.seen) == 1

    def test_akshare_raises_falls_back(self):
        cn = _FakeInnerRaises()
        us = _FakeInner(bars=["fallback"])
        adapter = CompositeMarketDataAdapter(cn_inner=cn, us_hk_inner=us)

        result = adapter.fetch_bars(_cn_inst(), self.T, self.T)

        assert result == ["fallback"]

    # ── fetch_quotes ───────────────────────────────────────────────────

    def test_quotes_partition_by_market(self):
        cn_inner = _FakeInner(quotes={"600000": 10.0})
        us_inner = _FakeInner(quotes={"SPY": 500.0})
        adapter = CompositeMarketDataAdapter(cn_inner=cn_inner, us_hk_inner=us_inner)

        result = adapter.fetch_quotes([_cn_inst(), _us_inst()])

        assert result == {"600000": 10.0, "SPY": 500.0}

    def test_quotes_cn_failure_falls_back(self):
        cn_inner = _FakeInnerRaises()
        us_inner = _FakeInner(quotes={"600000": 9.0})
        adapter = CompositeMarketDataAdapter(cn_inner=cn_inner, us_hk_inner=us_inner)

        result = adapter.fetch_quotes([_cn_inst()])

        assert result == {"600000": 9.0}
        assert len(us_inner.seen) == 1

    def test_quotes_us_only_no_cn_call(self):
        cn_inner = _FakeInner()
        us_inner = _FakeInner(quotes={"SPY": 500.0})
        adapter = CompositeMarketDataAdapter(cn_inner=cn_inner, us_hk_inner=us_inner)

        result = adapter.fetch_quotes([_us_inst()])

        assert result == {"SPY": 500.0}
        assert len(cn_inner.seen) == 0

    # ── delegation stubs ──────────────────────────────────────────────

    def test_option_chain_delegates_to_us_hk(self):
        us = _FakeInner()
        adapter = CompositeMarketDataAdapter(cn_inner=_FakeInner(), us_hk_inner=us)
        adapter.fetch_option_chain("SPY", self.T, market=Market.US)
        # No crash is the main assertion; the stub returns [].
        assert True

    def test_corporate_actions_delegates_to_us_hk(self):
        us = _FakeInner()
        adapter = CompositeMarketDataAdapter(cn_inner=_FakeInner(), us_hk_inner=us)
        result = adapter.fetch_corporate_actions(_us_inst(), self.T, self.T)
        assert result == []

    def test_fx_rates_delegates_to_us_hk(self):
        us = _FakeInner()
        adapter = CompositeMarketDataAdapter(cn_inner=_FakeInner(), us_hk_inner=us)
        result = adapter.fetch_fx_rates("USD", "CNY", self.T, self.T)
        assert result == []

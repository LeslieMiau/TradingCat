"""Unit tests for the YFinance market-data adapter.

These tests stub out ``yfinance`` so the suite never touches the network.
Focused on quote-fetch failure modes — NaN/None prices and exceptions must
omit the symbol rather than silently returning ``0.0``.
"""

from __future__ import annotations

import math

import pytest

from tradingcat.adapters import yfinance_adapter
from tradingcat.adapters.yfinance_adapter import YFinanceMarketDataAdapter
from tradingcat.domain.models import AssetClass, Instrument, Market


def _us_instrument(symbol: str = "SPY") -> Instrument:
    return Instrument(symbol=symbol, market=Market.US, asset_class=AssetClass.STOCK)


class _FakeFastInfo:
    def __init__(self, price):
        self._price = price

    def __getitem__(self, key):
        if key == "lastPrice":
            return self._price
        raise KeyError(key)


class _FakeTicker:
    def __init__(self, price=None, *, raise_on_access: bool = False):
        self._price = price
        self._raise = raise_on_access

    @property
    def fast_info(self):
        if self._raise:
            raise RuntimeError("yfinance unavailable")
        return _FakeFastInfo(self._price)


class _FakeYf:
    def __init__(self, prices: dict[str, float | None] | None = None, raise_for: set[str] | None = None):
        self._prices = prices or {}
        self._raise_for = raise_for or set()

    def Ticker(self, ticker: str) -> _FakeTicker:  # noqa: N802 — match yfinance API
        if ticker in self._raise_for:
            return _FakeTicker(raise_on_access=True)
        return _FakeTicker(self._prices.get(ticker))


def test_fetch_quotes_returns_valid_price(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_adapter, "yf", _FakeYf({"SPY": 432.10}))
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes([_us_instrument("SPY")])

    assert quotes == {"SPY": 432.10}


def test_fetch_quotes_omits_symbol_on_nan(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_adapter, "yf", _FakeYf({"SPY": math.nan}))
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes([_us_instrument("SPY")])

    assert "SPY" not in quotes
    assert quotes == {}


def test_fetch_quotes_omits_symbol_on_none(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_adapter, "yf", _FakeYf({"SPY": None}))
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes([_us_instrument("SPY")])

    assert quotes == {}


def test_fetch_quotes_omits_symbol_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_adapter, "yf", _FakeYf(raise_for={"SPY"}))
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes([_us_instrument("SPY")])

    assert quotes == {}


def test_fetch_quotes_keeps_valid_symbols_when_some_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        yfinance_adapter,
        "yf",
        _FakeYf(prices={"SPY": 432.10, "AAPL": math.nan, "TSLA": None}, raise_for={"NVDA"}),
    )
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes(
        [
            _us_instrument("SPY"),
            _us_instrument("AAPL"),
            _us_instrument("TSLA"),
            _us_instrument("NVDA"),
        ]
    )

    # Only SPY has a valid price; the rest are silently dropped (callers
    # detect this via ``symbol not in quotes`` and route to fallbacks).
    assert quotes == {"SPY": 432.10}


def test_fetch_quotes_drops_non_numeric_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(yfinance_adapter, "yf", _FakeYf({"SPY": "not-a-price"}))  # type: ignore[dict-item]
    adapter = YFinanceMarketDataAdapter()

    quotes = adapter.fetch_quotes([_us_instrument("SPY")])

    assert quotes == {}

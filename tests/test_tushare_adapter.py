"""Unit tests for the Tushare A-share market-data adapter (Round 04).

These tests inject fake Tushare objects so the suite does not need the optional
dependency, a real token, or network access.
"""

from __future__ import annotations

from datetime import date

import pytest

from tradingcat.adapters.cn.tushare import TushareMarketDataAdapter, TushareUnavailable
from tradingcat.config import TushareConfig
from tradingcat.domain.models import AssetClass, Instrument, Market


class _FakeDataFrame:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def to_dict(self, orient: str = "records") -> list[dict]:
        if orient != "records":
            raise TypeError("only orient='records' is supported by this fake")
        return list(self._rows)


class _FakeProClient:
    def __init__(
        self,
        *,
        daily_basic_rows: list[dict] | None = None,
        fina_indicator_rows: list[dict] | None = None,
        explode: bool = False,
    ) -> None:
        self.daily_basic_rows = daily_basic_rows or []
        self.fina_indicator_rows = fina_indicator_rows or []
        self.explode = explode
        self.calls: list[tuple[str, dict]] = []

    def daily_basic(self, **kwargs):
        self.calls.append(("daily_basic", kwargs))
        if self.explode:
            raise RuntimeError("daily_basic down")
        return _FakeDataFrame(self.daily_basic_rows)

    def fina_indicator(self, **kwargs):
        self.calls.append(("fina_indicator", kwargs))
        if self.explode:
            raise RuntimeError("fina_indicator down")
        return _FakeDataFrame(self.fina_indicator_rows)


class _FakeTushare:
    def __init__(
        self,
        *,
        pro_bar_rows: list[dict] | None = None,
        pro_client: _FakeProClient | None = None,
        explode_pro_bar: bool = False,
    ) -> None:
        self.pro_bar_rows = pro_bar_rows or []
        self.pro_client = pro_client or _FakeProClient()
        self.explode_pro_bar = explode_pro_bar
        self.calls: list[tuple[str, dict]] = []

    def pro_api(self, token):
        self.calls.append(("pro_api", {"token": token}))
        return self.pro_client

    def pro_bar(self, **kwargs):
        self.calls.append(("pro_bar", kwargs))
        if self.explode_pro_bar:
            raise RuntimeError("pro_bar down")
        return _FakeDataFrame(self.pro_bar_rows)


def _stock_instrument(symbol: str = "600000") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.STOCK,
        currency="CNY",
    )


def _etf_instrument(symbol: str = "159915") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.ETF,
        currency="CNY",
    )


def test_init_requires_token_without_injected_client():
    with pytest.raises(TushareUnavailable):
        TushareMarketDataAdapter(token="", tushare_module=_FakeTushare())


def test_fetch_bars_uses_pro_bar_and_sorts_trade_dates():
    fake = _FakeTushare(
        pro_bar_rows=[
            {"trade_date": "20240103", "open": 10.5, "high": 10.6, "low": 10.1, "close": 10.2, "vol": 987.0},
            {"trade_date": "20240102", "open": 10.0, "high": 10.7, "low": 9.9, "close": 10.5, "vol": 1234.0},
        ]
    )
    adapter = TushareMarketDataAdapter(token="test-token", adj="qfq", tushare_module=fake)

    bars = adapter.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5))

    assert [bar.close for bar in bars] == [10.5, 10.2]
    assert [call[0] for call in fake.calls] == ["pro_api", "pro_bar"]
    assert fake.calls[1][1] == {
        "ts_code": "600000.SH",
        "start_date": "20240101",
        "end_date": "20240105",
        "freq": "D",
        "asset": "E",
        "adj": "qfq",
        "pro_api": fake.pro_client,
    }


def test_fetch_bars_maps_sz_etf_and_raw_adjustment():
    fake = _FakeTushare(
        pro_bar_rows=[
            {"trade_date": "20240102", "open": 2.1, "high": 2.2, "low": 2.0, "close": 2.12, "vol": 5000.0}
        ]
    )
    adapter = TushareMarketDataAdapter(token="test-token", adj="", tushare_module=fake)

    bars = adapter.fetch_bars(_etf_instrument("159915"), date(2024, 1, 1), date(2024, 1, 31))

    assert len(bars) == 1
    assert fake.calls[1][1]["ts_code"] == "159915.SZ"
    assert fake.calls[1][1]["adj"] is None


def test_fetch_bars_returns_empty_on_empty_error_or_malformed_rows():
    empty = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare())
    assert empty.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []

    exploding = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare(explode_pro_bar=True))
    assert exploding.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []

    malformed = TushareMarketDataAdapter(
        token="test-token",
        tushare_module=_FakeTushare(pro_bar_rows=[{"trade_date": "20240102", "open": 1.0}]),
    )
    assert malformed.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []


def test_research_helpers_return_plain_rows_and_swallow_errors():
    pro = _FakeProClient(
        daily_basic_rows=[{"ts_code": "600000.SH", "trade_date": "20240102", "pe": 10.0}],
        fina_indicator_rows=[{"ts_code": "600000.SH", "end_date": "20231231", "roe": 0.12}],
    )
    adapter = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare(pro_client=pro))

    assert adapter.fetch_daily_basic(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == [
        {"ts_code": "600000.SH", "trade_date": "20240102", "pe": 10.0}
    ]
    assert adapter.fetch_fina_indicator(_stock_instrument("600000"), date(2023, 1, 1), date(2023, 12, 31)) == [
        {"ts_code": "600000.SH", "end_date": "20231231", "roe": 0.12}
    ]
    assert pro.calls == [
        ("daily_basic", {"ts_code": "600000.SH", "start_date": "20240101", "end_date": "20240105"}),
        ("fina_indicator", {"ts_code": "600000.SH", "start_date": "20230101", "end_date": "20231231"}),
    ]

    failing = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare(pro_client=_FakeProClient(explode=True)))
    assert failing.fetch_daily_basic(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []
    assert failing.fetch_fina_indicator(_stock_instrument("600000"), date(2023, 1, 1), date(2023, 12, 31)) == []


def test_normalise_rejects_non_cn_market_index_label_and_bad_symbol():
    adapter = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare())

    with pytest.raises(TushareUnavailable):
        adapter.fetch_bars(Instrument(symbol="AAPL", market=Market.US, currency="USD"), date(2024, 1, 1), date(2024, 1, 2))
    with pytest.raises(TushareUnavailable):
        adapter.fetch_bars(Instrument(symbol="SH000001", market=Market.CN, currency="CNY"), date(2024, 1, 1), date(2024, 1, 2))
    with pytest.raises(TushareUnavailable):
        adapter.fetch_bars(Instrument(symbol="abc", market=Market.CN, currency="CNY"), date(2024, 1, 1), date(2024, 1, 2))


def test_stub_endpoints_return_empty():
    adapter = TushareMarketDataAdapter(token="test-token", tushare_module=_FakeTushare())
    assert adapter.fetch_quotes([_stock_instrument("600000")]) == {}
    assert adapter.fetch_option_chain("600000", date(2024, 1, 1)) == []
    assert adapter.fetch_corporate_actions(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 12, 31)) == []
    assert adapter.fetch_fx_rates("CNY", "USD", date(2024, 1, 1), date(2024, 1, 31)) == []


def test_config_defaults_disabled_without_token():
    cfg = TushareConfig()
    assert cfg.enabled is False
    assert cfg.token is None
    assert cfg.adj == "qfq"


def test_config_from_env_parses_flags():
    cfg = TushareConfig.from_env(
        {
            "TRADINGCAT_TUSHARE_ENABLED": "true",
            "TRADINGCAT_TUSHARE_TOKEN": "secret-token",
            "TRADINGCAT_TUSHARE_ADJ": "hfq",
        }
    )
    assert cfg.enabled is True
    assert cfg.token == "secret-token"
    assert cfg.adj == "hfq"


def test_config_from_env_rejects_invalid_adj():
    with pytest.raises(ValueError):
        TushareConfig.from_env({"TRADINGCAT_TUSHARE_ADJ": "bad"})

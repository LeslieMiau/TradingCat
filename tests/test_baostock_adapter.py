"""Unit tests for the BaoStock A-share market-data adapter (Round 03).

These tests inject a fake ``baostock`` module so the suite does not need the
optional dependency and never opens a real BaoStock network session.
"""

from __future__ import annotations

from datetime import date

import pytest

from tradingcat.adapters.cn.baostock import (
    BaostockMarketDataAdapter,
    BaostockUnavailable,
)
from tradingcat.config import BaostockConfig
from tradingcat.domain.models import AssetClass, Instrument, Market


class _FakeResult:
    def __init__(
        self,
        *,
        fields: list[str] | None = None,
        rows: list[list[str]] | None = None,
        error_code: str = "0",
        error_msg: str = "",
    ) -> None:
        self.fields = fields or [
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "amount",
            "tradestatus",
        ]
        self.rows = rows or []
        self.error_code = error_code
        self.error_msg = error_msg
        self._index = -1

    def next(self):
        self._index += 1
        return self._index < len(self.rows)

    def get_row_data(self):
        return self.rows[self._index]


class _FakeLogin:
    def __init__(self, error_code: str = "0", error_msg: str = "") -> None:
        self.error_code = error_code
        self.error_msg = error_msg


class _FakeBaostock:
    def __init__(
        self,
        *,
        rows: list[list[str]] | None = None,
        login_error_code: str = "0",
        query_error_code: str = "0",
    ) -> None:
        self.rows = rows or []
        self.login_error_code = login_error_code
        self.query_error_code = query_error_code
        self.calls: list[tuple[str, tuple, dict]] = []

    def login(self):
        self.calls.append(("login", (), {}))
        return _FakeLogin(error_code=self.login_error_code, error_msg="login failed")

    def logout(self):
        self.calls.append(("logout", (), {}))
        return None

    def query_history_k_data_plus(self, *args, **kwargs):
        self.calls.append(("query_history_k_data_plus", args, kwargs))
        return _FakeResult(
            rows=self.rows,
            error_code=self.query_error_code,
            error_msg="query failed",
        )


def _stock_instrument(symbol: str = "600000") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.STOCK,
        currency="CNY",
    )


def _etf_instrument(symbol: str = "510300") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.ETF,
        currency="CNY",
    )


def test_fetch_bars_logs_in_queries_and_logs_out():
    fake = _FakeBaostock(
        rows=[
            ["2024-01-02", "sh.600000", "10.0", "10.7", "9.9", "10.5", "1234567", "10000000", "1"],
            ["2024-01-03", "sh.600000", "10.5", "10.6", "10.1", "10.2", "987654", "9000000", "1"],
        ]
    )
    adapter = BaostockMarketDataAdapter(baostock_module=fake, adjustflag="2")

    bars = adapter.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5))

    assert [bar.close for bar in bars] == [10.5, 10.2]
    assert bars[0].open == 10.0
    assert bars[0].volume == 1_234_567
    assert [call[0] for call in fake.calls] == ["login", "query_history_k_data_plus", "logout"]
    query_call = fake.calls[1]
    assert query_call[1] == ("sh.600000", "date,code,open,high,low,close,volume,amount,tradestatus")
    assert query_call[2] == {
        "start_date": "2024-01-01",
        "end_date": "2024-01-05",
        "frequency": "d",
        "adjustflag": "2",
    }


def test_fetch_bars_maps_cn_etf_to_sh_or_sz_prefix():
    fake = _FakeBaostock(rows=[["2024-01-02", "sh.510300", "4.1", "4.2", "4.0", "4.12", "5000", "1000", "1"]])
    adapter = BaostockMarketDataAdapter(baostock_module=fake)

    bars = adapter.fetch_bars(_etf_instrument("510300"), date(2024, 1, 1), date(2024, 1, 31))

    assert len(bars) == 1
    assert fake.calls[1][1][0] == "sh.510300"

    fake_sz = _FakeBaostock(rows=[["2024-01-02", "sz.159915", "2.1", "2.2", "2.0", "2.12", "5000", "1000", "1"]])
    adapter_sz = BaostockMarketDataAdapter(baostock_module=fake_sz)
    adapter_sz.fetch_bars(_etf_instrument("159915"), date(2024, 1, 1), date(2024, 1, 31))

    assert fake_sz.calls[1][1][0] == "sz.159915"


def test_fetch_bars_skips_suspended_and_malformed_rows():
    fake = _FakeBaostock(
        rows=[
            ["2024-01-02", "sh.600000", "10.0", "10.7", "9.9", "10.5", "1234567", "10000000", "0"],
            ["2024-01-03", "sh.600000", "10.5", "10.6", "10.1", "", "987654", "9000000", "1"],
            ["2024-01-04", "sh.600000", "10.5", "10.6", "10.1", "10.2", "987654", "9000000", "1"],
        ]
    )
    adapter = BaostockMarketDataAdapter(baostock_module=fake)

    bars = adapter.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5))

    assert len(bars) == 1
    assert bars[0].close == 10.2


def test_fetch_bars_returns_empty_when_login_or_query_fails():
    login_fails = _FakeBaostock(login_error_code="1")
    adapter = BaostockMarketDataAdapter(baostock_module=login_fails)

    assert adapter.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []
    assert [call[0] for call in login_fails.calls] == ["login"]

    query_fails = _FakeBaostock(query_error_code="1")
    adapter = BaostockMarketDataAdapter(baostock_module=query_fails)

    assert adapter.fetch_bars(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)) == []
    assert [call[0] for call in query_fails.calls] == ["login", "query_history_k_data_plus", "logout"]


def test_normalise_rejects_non_cn_market_index_label_and_bad_symbol():
    adapter = BaostockMarketDataAdapter(baostock_module=_FakeBaostock())

    with pytest.raises(BaostockUnavailable):
        adapter.fetch_bars(Instrument(symbol="AAPL", market=Market.US, currency="USD"), date(2024, 1, 1), date(2024, 1, 2))
    with pytest.raises(BaostockUnavailable):
        adapter.fetch_bars(Instrument(symbol="SH000001", market=Market.CN, currency="CNY"), date(2024, 1, 1), date(2024, 1, 2))
    with pytest.raises(BaostockUnavailable):
        adapter.fetch_bars(Instrument(symbol="abc", market=Market.CN, currency="CNY"), date(2024, 1, 1), date(2024, 1, 2))


def test_stub_endpoints_return_empty():
    adapter = BaostockMarketDataAdapter(baostock_module=_FakeBaostock())
    assert adapter.fetch_quotes([_stock_instrument("600000")]) == {}
    assert adapter.fetch_option_chain("600000", date(2024, 1, 1)) == []
    assert adapter.fetch_corporate_actions(_stock_instrument("600000"), date(2024, 1, 1), date(2024, 12, 31)) == []
    assert adapter.fetch_fx_rates("CNY", "USD", date(2024, 1, 1), date(2024, 1, 31)) == []


def test_config_defaults_disabled_with_adjustflag_two():
    cfg = BaostockConfig()
    assert cfg.enabled is False
    assert cfg.adjustflag == "2"


def test_config_from_env_parses_flags():
    cfg = BaostockConfig.from_env(
        {
            "TRADINGCAT_BAOSTOCK_ENABLED": "true",
            "TRADINGCAT_BAOSTOCK_ADJUSTFLAG": "3",
        }
    )
    assert cfg.enabled is True
    assert cfg.adjustflag == "3"


def test_config_from_env_rejects_invalid_adjustflag():
    with pytest.raises(ValueError):
        BaostockConfig.from_env({"TRADINGCAT_BAOSTOCK_ADJUSTFLAG": "0"})

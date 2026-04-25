"""Unit tests for the AKShare A-share market-data adapter (Round 01).

These tests inject a fake ``akshare`` module so the suite can run without the
optional dependency installed and without hitting the network.
"""

from __future__ import annotations

from datetime import date

import pytest

from tradingcat.adapters.cn.akshare import (
    AkshareMarketDataAdapter,
    AkshareUnavailable,
)
from tradingcat.config import AkshareConfig
from tradingcat.domain.models import AssetClass, Instrument, Market


class _FakeDataFrame:
    """Minimal pandas-like stand-in supporting ``to_dict(orient='records')``.

    The real AKShare DataFrame has more, but the adapter only needs this entry
    point (and falls back to ``iterrows``).
    """

    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    @property
    def empty(self) -> bool:
        return not self._rows

    def to_dict(self, orient: str = "records") -> list[dict]:
        if orient != "records":
            raise TypeError("only orient='records' is supported by this fake")
        return list(self._rows)


class _FakeAkshare:
    """Fake module exposing the three AKShare endpoints the adapter calls."""

    def __init__(
        self,
        *,
        stock_hist_rows: list[dict] | None = None,
        etf_hist_rows: list[dict] | None = None,
        spot_rows: list[dict] | None = None,
    ) -> None:
        self.stock_hist_rows = stock_hist_rows or []
        self.etf_hist_rows = etf_hist_rows or []
        self.spot_rows = spot_rows or []
        self.calls: list[tuple[str, dict]] = []

    def stock_zh_a_hist(self, **kwargs):
        self.calls.append(("stock_zh_a_hist", kwargs))
        return _FakeDataFrame(self.stock_hist_rows)

    def fund_etf_hist_em(self, **kwargs):
        self.calls.append(("fund_etf_hist_em", kwargs))
        return _FakeDataFrame(self.etf_hist_rows)

    def stock_zh_a_spot_em(self):
        self.calls.append(("stock_zh_a_spot_em", {}))
        return _FakeDataFrame(self.spot_rows)


def _stock_instrument(symbol: str = "600000", name: str = "Pudong") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.STOCK,
        currency="CNY",
        name=name,
    )


def _etf_instrument(symbol: str = "510300", name: str = "CSI 300 ETF") -> Instrument:
    return Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.ETF,
        currency="CNY",
        name=name,
    )


def test_fetch_bars_routes_stock_to_stock_zh_a_hist():
    fake = _FakeAkshare(
        stock_hist_rows=[
            {
                "日期": "2024-01-02",
                "开盘": 10.0,
                "收盘": 10.5,
                "最高": 10.7,
                "最低": 9.9,
                "成交量": 1_234_567,
            },
            {
                "日期": "2024-01-03",
                "开盘": 10.5,
                "收盘": 10.2,
                "最高": 10.6,
                "最低": 10.1,
                "成交量": 987_654,
            },
        ]
    )
    adapter = AkshareMarketDataAdapter(akshare_module=fake, adjust="qfq")
    bars = adapter.fetch_bars(
        _stock_instrument("600000"),
        date(2024, 1, 1),
        date(2024, 1, 5),
    )
    assert [b.close for b in bars] == [10.5, 10.2]
    assert bars[0].open == 10.0
    assert bars[0].volume == 1_234_567
    assert fake.calls == [
        (
            "stock_zh_a_hist",
            {
                "symbol": "600000",
                "period": "daily",
                "start_date": "20240101",
                "end_date": "20240105",
                "adjust": "qfq",
            },
        )
    ]


def test_fetch_bars_routes_etf_to_fund_etf_hist_em():
    fake = _FakeAkshare(
        etf_hist_rows=[
            {
                "日期": "2024-01-02",
                "开盘": 4.10,
                "收盘": 4.12,
                "最高": 4.15,
                "最低": 4.08,
                "成交量": 50_000_000,
            }
        ]
    )
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    bars = adapter.fetch_bars(
        _etf_instrument("510300"),
        date(2024, 1, 1),
        date(2024, 1, 31),
    )
    assert len(bars) == 1
    assert bars[0].close == 4.12
    assert fake.calls[0][0] == "fund_etf_hist_em"


def test_fetch_bars_returns_empty_on_unparseable_rows():
    # Row missing the close column should be skipped, not crash.
    fake = _FakeAkshare(
        stock_hist_rows=[
            {"日期": "2024-01-02", "开盘": 10.0, "最高": 10.7, "最低": 9.9},
        ]
    )
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    assert adapter.fetch_bars(
        _stock_instrument("600000"),
        date(2024, 1, 1),
        date(2024, 1, 5),
    ) == []


def test_fetch_bars_swallows_endpoint_exception():
    class _Exploding:
        def stock_zh_a_hist(self, **kwargs):
            raise RuntimeError("boom")

        def fund_etf_hist_em(self, **kwargs):  # pragma: no cover — not used here
            raise RuntimeError("boom")

        def stock_zh_a_spot_em(self):  # pragma: no cover — not used here
            raise RuntimeError("boom")

    adapter = AkshareMarketDataAdapter(akshare_module=_Exploding())
    bars = adapter.fetch_bars(
        _stock_instrument("600000"), date(2024, 1, 1), date(2024, 1, 5)
    )
    assert bars == []


def test_fetch_quotes_uses_spot_snapshot_and_caches():
    fake = _FakeAkshare(
        spot_rows=[
            {"代码": "600000", "最新价": 10.21},
            {"代码": "300308", "最新价": 168.50},
            {"代码": "510300", "最新价": 4.12},
        ]
    )
    adapter = AkshareMarketDataAdapter(akshare_module=fake, spot_cache_ttl_seconds=60.0)
    quotes_first = adapter.fetch_quotes(
        [_stock_instrument("600000"), _etf_instrument("510300")]
    )
    quotes_second = adapter.fetch_quotes([_stock_instrument("300308")])

    assert quotes_first == {"600000": 10.21, "510300": 4.12}
    assert quotes_second == {"300308": 168.50}
    # The snapshot endpoint must only be hit once thanks to caching.
    spot_calls = [name for name, _ in fake.calls if name == "stock_zh_a_spot_em"]
    assert len(spot_calls) == 1


def test_fetch_quotes_skips_non_cn_instruments_quietly():
    fake = _FakeAkshare(spot_rows=[{"代码": "600000", "最新价": 10.0}])
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    us_instr = Instrument(symbol="AAPL", market=Market.US, currency="USD")
    cn_instr = _stock_instrument("600000")
    quotes = adapter.fetch_quotes([us_instr, cn_instr])
    assert quotes == {"600000": 10.0}


def test_fetch_quotes_returns_empty_when_snapshot_fails():
    class _SpotExplodes:
        def stock_zh_a_hist(self, **kwargs):  # pragma: no cover — unused
            return _FakeDataFrame([])

        def fund_etf_hist_em(self, **kwargs):  # pragma: no cover — unused
            return _FakeDataFrame([])

        def stock_zh_a_spot_em(self):
            raise ConnectionError("network down")

    adapter = AkshareMarketDataAdapter(akshare_module=_SpotExplodes())
    assert adapter.fetch_quotes([_stock_instrument("600000")]) == {}


def test_normalise_rejects_non_cn_market():
    fake = _FakeAkshare()
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    bad = Instrument(symbol="AAPL", market=Market.US, currency="USD")
    with pytest.raises(AkshareUnavailable):
        adapter.fetch_bars(bad, date(2024, 1, 1), date(2024, 1, 2))


def test_normalise_rejects_index_label():
    fake = _FakeAkshare()
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    bad = Instrument(symbol="SH000001", market=Market.CN, currency="CNY")
    with pytest.raises(AkshareUnavailable):
        adapter.fetch_bars(bad, date(2024, 1, 1), date(2024, 1, 2))


def test_normalise_rejects_non_six_digit_symbol():
    fake = _FakeAkshare()
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    bad = Instrument(symbol="abc", market=Market.CN, currency="CNY")
    with pytest.raises(AkshareUnavailable):
        adapter.fetch_bars(bad, date(2024, 1, 1), date(2024, 1, 2))


def test_stub_endpoints_return_empty():
    fake = _FakeAkshare()
    adapter = AkshareMarketDataAdapter(akshare_module=fake)
    assert adapter.fetch_option_chain("600000", date(2024, 1, 1)) == []
    assert (
        adapter.fetch_corporate_actions(
            _stock_instrument("600000"), date(2024, 1, 1), date(2024, 12, 31)
        )
        == []
    )
    assert adapter.fetch_fx_rates("CNY", "USD", date(2024, 1, 1), date(2024, 1, 31)) == []


def test_config_defaults_disabled_with_qfq_adjust():
    cfg = AkshareConfig()
    assert cfg.enabled is False
    assert cfg.adjust == "qfq"
    assert cfg.spot_cache_ttl_seconds == 30.0


def test_config_from_env_parses_flags(monkeypatch):
    env = {
        "TRADINGCAT_AKSHARE_ENABLED": "true",
        "TRADINGCAT_AKSHARE_ADJUST": "hfq",
        "TRADINGCAT_AKSHARE_SPOT_CACHE_TTL_SECONDS": "120",
    }
    cfg = AkshareConfig.from_env(env)
    assert cfg.enabled is True
    assert cfg.adjust == "hfq"
    assert cfg.spot_cache_ttl_seconds == 120.0


def test_config_from_env_rejects_invalid_adjust():
    with pytest.raises(ValueError):
        AkshareConfig.from_env({"TRADINGCAT_AKSHARE_ADJUST": "invalid"})

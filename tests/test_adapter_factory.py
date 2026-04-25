from datetime import UTC, date, datetime

import pytest

from tradingcat.adapters.cn.akshare import AkshareUnavailable
from tradingcat.adapters.composite import CompositeMarketDataAdapter
from tradingcat.adapters.futu import FutuAdapterUnavailable, _asset_class_from_symbol, _map_order_status, _parse_date
from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.broker import SimulatedBrokerAdapter
from tradingcat.config import AkshareConfig, AppConfig, FutuConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market


class _ReachableSocket:
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _patch_futu_endpoint_reachable(monkeypatch):
    monkeypatch.setattr(
        "tradingcat.adapters.factory.socket.create_connection",
        lambda *_args, **_kwargs: _ReachableSocket(),
    )


def test_factory_falls_back_when_futu_disabled():
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=False)))

    assert isinstance(factory.create_market_data_adapter(), StaticMarketDataAdapter)
    assert isinstance(factory.create_live_broker_adapter(), SimulatedBrokerAdapter)
    assert factory.broker_backend_name() == "simulated"


def test_factory_ignores_akshare_when_disabled(monkeypatch):
    monkeypatch.setattr("tradingcat.adapters.factory.AKSHARE_AVAILABLE", True)
    monkeypatch.setattr(
        "tradingcat.adapters.factory.AkshareMarketDataAdapter",
        lambda *_args, **_kwargs: pytest.fail("AKShare should not initialize when disabled"),
    )
    factory = AdapterFactory(
        AppConfig(
            futu=FutuConfig(enabled=False),
            akshare=AkshareConfig(enabled=False),
        )
    )

    adapter = factory.create_market_data_adapter()

    assert isinstance(adapter, StaticMarketDataAdapter)
    assert not isinstance(adapter, CompositeMarketDataAdapter)


def test_factory_falls_back_when_sdk_missing(monkeypatch):
    _patch_futu_endpoint_reachable(monkeypatch)
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=True)))

    def unavailable(*_args, **_kwargs):
        raise FutuAdapterUnavailable("futu sdk unavailable")

    monkeypatch.setattr("tradingcat.adapters.factory.FutuMarketDataAdapter", unavailable)
    monkeypatch.setattr("tradingcat.adapters.factory.FutuBrokerAdapter", unavailable)

    assert isinstance(factory.create_market_data_adapter(), StaticMarketDataAdapter)
    assert isinstance(factory.create_live_broker_adapter(), SimulatedBrokerAdapter)
    diagnostics = factory.broker_diagnostics()
    assert diagnostics["backend"] == "simulated"
    assert "detail" in diagnostics


def test_factory_falls_back_when_futu_init_times_out(monkeypatch):
    _patch_futu_endpoint_reachable(monkeypatch)
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=True)))

    def slow_market_adapter(_config):
        import time
        time.sleep(3.5)
        return object()

    monkeypatch.setattr("tradingcat.adapters.factory.FutuMarketDataAdapter", slow_market_adapter)

    adapter = factory.create_market_data_adapter()
    assert isinstance(adapter, StaticMarketDataAdapter)


def test_factory_wraps_market_data_with_akshare_composite(monkeypatch):
    monkeypatch.setattr("tradingcat.adapters.factory.AKSHARE_AVAILABLE", True)

    class _FakeAkshareAdapter:
        def __init__(self, *, adjust, spot_cache_ttl_seconds):
            self.adjust = adjust
            self.spot_cache_ttl_seconds = spot_cache_ttl_seconds

        def fetch_bars(self, instrument, start, end):
            return [
                Bar(
                    instrument=instrument,
                    timestamp=datetime(2024, 1, 2, tzinfo=UTC),
                    open=10.0,
                    high=11.0,
                    low=9.0,
                    close=10.5,
                    volume=1000,
                )
            ]

        def fetch_quotes(self, instruments):
            return {instrument.symbol: 12.3 for instrument in instruments}

    monkeypatch.setattr("tradingcat.adapters.factory.AkshareMarketDataAdapter", _FakeAkshareAdapter)
    factory = AdapterFactory(
        AppConfig(
            futu=FutuConfig(enabled=False),
            akshare=AkshareConfig(enabled=True, adjust="hfq", spot_cache_ttl_seconds=5.0),
        )
    )

    adapter = factory.create_market_data_adapter()
    cn = Instrument(symbol="600000", market=Market.CN, asset_class=AssetClass.STOCK, currency="CNY")
    us = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")

    assert isinstance(adapter, CompositeMarketDataAdapter)
    assert adapter.fetch_bars(cn, date(2024, 1, 1), date(2024, 1, 3))[0].close == 10.5
    assert adapter.fetch_quotes([cn, us]) == {"600000": 12.3, "SPY": 100.0}


def test_akshare_composite_falls_back_to_inner_on_empty_or_unavailable(monkeypatch):
    monkeypatch.setattr("tradingcat.adapters.factory.AKSHARE_AVAILABLE", True)

    class _EmptyAkshareAdapter:
        def __init__(self, **_kwargs):
            return None

        def fetch_bars(self, instrument, start, end):
            return []

        def fetch_quotes(self, instruments):
            return {}

    monkeypatch.setattr("tradingcat.adapters.factory.AkshareMarketDataAdapter", _EmptyAkshareAdapter)
    factory = AdapterFactory(
        AppConfig(
            futu=FutuConfig(enabled=False),
            akshare=AkshareConfig(enabled=True),
        )
    )
    adapter = factory.create_market_data_adapter()
    cn = Instrument(symbol="600000", market=Market.CN, asset_class=AssetClass.STOCK, currency="CNY")

    assert adapter.fetch_bars(cn, date(2024, 1, 1), date(2024, 1, 2))
    assert adapter.fetch_quotes([cn]) == {"600000": 100.0}

    class _UnavailableAkshareAdapter(_EmptyAkshareAdapter):
        def fetch_bars(self, instrument, start, end):
            raise AkshareUnavailable("not available")

        def fetch_quotes(self, instruments):
            raise AkshareUnavailable("not available")

    monkeypatch.setattr("tradingcat.adapters.factory.AkshareMarketDataAdapter", _UnavailableAkshareAdapter)
    adapter = factory.create_market_data_adapter()

    assert adapter.fetch_bars(cn, date(2024, 1, 1), date(2024, 1, 2))
    assert adapter.fetch_quotes([cn]) == {"600000": 100.0}


def test_factory_validation_reports_skipped_or_failures(monkeypatch):
    _patch_futu_endpoint_reachable(monkeypatch)
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=True)))

    def unavailable(*_args, **_kwargs):
        raise FutuAdapterUnavailable("futu sdk unavailable")

    monkeypatch.setattr("tradingcat.adapters.factory.FutuMarketDataAdapter", unavailable)
    monkeypatch.setattr("tradingcat.adapters.factory.FutuBrokerAdapter", unavailable)

    validation = factory.validate_futu_connection()

    assert validation["backend"] == "futu"
    assert set(validation["checks"].keys()) == {"quote", "trade"}
    assert validation["checks"]["quote"]["status"] in {"ok", "failed", "skipped"}
    assert validation["checks"]["trade"]["status"] in {"ok", "failed", "skipped"}


def test_factory_skips_futu_checks_when_opend_is_unreachable(monkeypatch):
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=True)))

    def unreachable(*_args, **_kwargs):
        raise ConnectionRefusedError("Connection refused")

    monkeypatch.setattr("tradingcat.adapters.factory.socket.create_connection", unreachable)
    monkeypatch.setattr(
        "tradingcat.adapters.factory.FutuMarketDataAdapter",
        lambda *_args, **_kwargs: pytest.fail("market adapter should not initialize when OpenD is down"),
    )
    monkeypatch.setattr(
        "tradingcat.adapters.factory.FutuBrokerAdapter",
        lambda *_args, **_kwargs: pytest.fail("broker adapter should not initialize when OpenD is down"),
    )

    assert isinstance(factory.create_market_data_adapter(), StaticMarketDataAdapter)
    assert isinstance(factory.create_live_broker_adapter(), SimulatedBrokerAdapter)

    diagnostics = factory.broker_diagnostics()
    validation = factory.validate_futu_connection()

    assert diagnostics["backend"] == "simulated"
    assert "not reachable" in str(diagnostics["detail"])
    assert validation["detail"] == "Futu validation skipped"
    assert validation["checks"]["quote"]["status"] == "skipped"
    assert validation["checks"]["trade"]["status"] == "skipped"


def test_factory_caches_validation_results_briefly(monkeypatch):
    _patch_futu_endpoint_reachable(monkeypatch)
    factory = AdapterFactory(AppConfig(futu=FutuConfig(enabled=True)))
    counts = {"quote": 0, "trade": 0}

    class _QuoteAdapter:
        def __init__(self, _config):
            counts["quote"] += 1

        def close(self):
            return None

        def health_check(self):
            return {"healthy": True, "detail": "Quote context connected"}

    class _TradeAdapter:
        def __init__(self, _config):
            counts["trade"] += 1

        def close(self):
            return None

        def health_check(self):
            return {"healthy": True, "detail": "Trade context connected"}

    monkeypatch.setattr("tradingcat.adapters.factory.FutuMarketDataAdapter", _QuoteAdapter)
    monkeypatch.setattr("tradingcat.adapters.factory.FutuBrokerAdapter", _TradeAdapter)

    broker_first = factory.broker_diagnostics()
    broker_second = factory.broker_diagnostics()
    validation_first = factory.validate_futu_connection()
    validation_second = factory.validate_futu_connection()

    assert broker_first == broker_second
    assert validation_first == validation_second
    assert counts["quote"] == 1
    assert counts["trade"] == 2


def test_futu_parsing_helpers_are_conservative():
    assert _parse_date("2026-03-07 09:30:00") is not None
    assert _asset_class_from_symbol("510300").value == "etf"
    assert _asset_class_from_symbol("0700").value == "stock"
    assert _map_order_status("CANCELLED_ALL") .value == "cancelled"


def test_simulated_broker_probe_shape():
    broker = SimulatedBrokerAdapter()
    payload = broker.probe()
    assert payload["status"] == "ok"
    assert {"cash", "positions", "orders"} <= set(payload.keys())

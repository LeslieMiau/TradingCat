import pytest

from tradingcat.adapters.futu import FutuAdapterUnavailable, _asset_class_from_symbol, _map_order_status, _parse_date
from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.broker import SimulatedBrokerAdapter
from tradingcat.config import AppConfig, FutuConfig


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

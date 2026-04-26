from datetime import date

import pytest

from tradingcat.adapters.futu import FutuBrokerAdapter, FutuMarketDataAdapter, _normalize_code
from tradingcat.config import FutuConfig
from tradingcat.domain.models import AssetClass, Instrument, Market, OrderIntent, OrderSide


class _FakeTable:
    def __init__(self, records):
        self._records = records

    def to_dict(self, orient):
        assert orient == "records"
        return list(self._records)


class _FakeQuoteContext:
    def __init__(self, host, port):
        self.host = host
        self.port = port

    def close(self):
        return None

    def get_global_state(self):
        return 0, {"state": "ready"}

    def request_history_kline(self, code, start, end, max_count):
        return 0, _FakeTable(
            [
                {
                    "time_key": "2026-03-05 09:30:00",
                    "open": 100,
                    "high": 101,
                    "low": 99,
                    "close": 100.5,
                    "volume": 12345,
                }
            ]
        ), None

    def get_market_snapshot(self, codes):
        return 0, _FakeTable([{"code": code, "last_price": 101.25} for code in codes])

    def get_option_chain(self, code, start, end):
        return 0, _FakeTable(
            [
                {
                    "code": "US.SPY240405C00500000",
                    "strike_price": 500,
                    "expiry_date": "2026-04-05",
                    "option_type": "CALL",
                }
            ]
        )

    def get_rehab(self, code):
        return 0, _FakeTable([{"ex_div_date": "2026-03-06", "action": "DIVIDEND"}])


class _FakeTradeContext:
    def __init__(self, filter_trdmarket, host, port):
        self.market = filter_trdmarket
        self.cancel_attempts = []

    def close(self):
        return None

    def unlock_trade(self, password):
        return 0, "ok"

    def accinfo_query(self, trd_env):
        return 0, _FakeTable([{"cash": 50000}])

    def order_list_query(self, trd_env):
        return 0, _FakeTable([{"order_id": "1001", "order_status": "SUBMITTED", "dealt_qty": 0, "price": 10.5}])

    def position_list_query(self, trd_env):
        code_map = {"US": "US.SPY", "HK": "HK.0700", "CN": "SH.510300"}
        code = code_map.get(self.market, "US.SPY")
        return 0, _FakeTable([{"code": code, "qty": 10, "market_val": 1000}])

    def deal_list_query(self, trd_env):
        return 0, _FakeTable([{"order_id": "1001", "qty": 10, "price": 10.5}])

    def place_order(self, price, qty, code, trd_side, order_type, trd_env):
        return 0, _FakeTable([{"order_id": "1002", "price": price or 10.5}])

    def modify_order(self, modify_order_op, order_id, qty, price, trd_env):
        self.cancel_attempts.append(order_id)
        if self.market == "HK":
            return 1, "order not found"
        return 0, "cancelled"


class _FakeFt:
    RET_OK = 0

    class TrdMarket:
        HK = "HK"
        US = "US"
        CN = "CN"

    class TrdEnv:
        SIMULATE = "SIMULATE"
        REAL = "REAL"

    class OrderType:
        NORMAL = "NORMAL"
        MARKET = "MARKET"

    class TrdSide:
        BUY = "BUY"
        SELL = "SELL"

    class ModifyOrderOp:
        CANCEL = "CANCEL"

    OpenQuoteContext = _FakeQuoteContext
    OpenSecTradeContext = _FakeTradeContext


@pytest.fixture
def fake_futu_sdk(monkeypatch):
    monkeypatch.setattr("tradingcat.adapters.futu._load_futu_sdk", lambda: _FakeFt)


def test_futu_market_adapter_maps_quote_bar_and_option_chain(fake_futu_sdk):
    adapter = FutuMarketDataAdapter(FutuConfig(enabled=True))
    instrument = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")

    health = adapter.health_check()
    quotes = adapter.fetch_quotes([instrument])
    bars = adapter.fetch_bars(instrument, date(2026, 3, 5), date(2026, 3, 5))
    chain = adapter.fetch_option_chain("SPY", date(2026, 3, 5))
    actions = adapter.fetch_corporate_actions(instrument, date(2026, 3, 1), date(2026, 3, 7))

    assert health["healthy"] is True
    assert quotes["SPY"] == 101.25
    assert len(bars) == 1
    assert bars[0].close == 100.5
    assert len(chain) == 1
    assert chain[0].market == Market.US
    assert len(actions) == 1


def test_futu_normalize_code_pads_hk_symbols():
    instrument = Instrument(symbol="0700", market=Market.HK, asset_class=AssetClass.STOCK, currency="HKD")
    assert _normalize_code(instrument) == "HK.00700"


def test_futu_market_adapter_preserves_original_hk_symbol(fake_futu_sdk):
    adapter = FutuMarketDataAdapter(FutuConfig(enabled=True))
    instrument = Instrument(symbol="0700", market=Market.HK, asset_class=AssetClass.STOCK, currency="HKD")

    quotes = adapter.fetch_quotes([instrument])

    assert quotes == {"0700": 101.25}


def test_futu_normalize_code_maps_cn_symbols_to_exchange_prefix():
    sh_instrument = Instrument(symbol="510300", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY")
    sz_instrument = Instrument(symbol="159919", market=Market.CN, asset_class=AssetClass.ETF, currency="CNY")

    assert _normalize_code(sh_instrument) == "SH.510300"
    assert _normalize_code(sz_instrument) == "SZ.159919"


def test_futu_broker_adapter_routes_cancel_and_probes(fake_futu_sdk):
    adapter = FutuBrokerAdapter(FutuConfig(enabled=True))
    intent = OrderIntent(
        signal_id="sig-1",
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        quantity=10,
    )

    health = adapter.health_check()
    placed = adapter.place_order(intent)
    cancelled = adapter.cancel_order("1002")
    orders = adapter.get_orders()
    positions = adapter.get_positions()
    cash = adapter.get_cash()
    fills = adapter.reconcile_fills()
    probe = adapter.probe()

    assert health["healthy"] is True
    assert placed.broker_order_id == "1002"
    assert cancelled.status.value == "cancelled"
    assert len(orders) == 3
    assert len(positions) == 3
    assert cash == 150000
    assert len(fills) == 3
    assert probe["status"] == "ok"
    assert probe["orders"] == 3

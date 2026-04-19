from datetime import date, datetime, timezone

from tradingcat.adapters.broker import ManualExecutionAdapter, SimulatedBrokerAdapter
from tradingcat.config import AppConfig, FutuConfig
from tradingcat.domain.models import (
    AssetClass,
    ExecutionReport,
    Instrument,
    Market,
    OrderIntent,
    OrderSide,
    OrderStatus,
)
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import ApprovalRepository, ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.trade_ledger import (
    CSV_COLUMNS,
    FEE_SCHEDULE_VERSION,
    FEE_SCHEDULES,
    TradeLedgerService,
    render_csv,
)


UTC = timezone.utc


def _service_with_fill(
    *,
    market: Market,
    asset_class: AssetClass = AssetClass.STOCK,
    side: OrderSide = OrderSide.BUY,
    symbol: str = "SPY",
    currency: str = "USD",
    filled_quantity: float = 100.0,
    average_price: float = 100.0,
    ts: datetime | None = None,
) -> TradeLedgerService:
    timestamp = ts or datetime(2026, 4, 15, 14, 30, tzinfo=UTC)
    report = ExecutionReport(
        order_intent_id="intent-1",
        broker_order_id="broker-1",
        fill_id="fill-1",
        status=OrderStatus.FILLED,
        filled_quantity=filled_quantity,
        average_price=average_price,
        timestamp=timestamp,
        market=market,
        slippage=0.0005,
    )
    intent_context = {
        "symbol": symbol,
        "market": market.value,
        "asset_class": asset_class.value,
        "side": side.value,
        "currency": currency,
        "strategy_id": "strat_alpha",
    }
    return TradeLedgerService(
        list_orders=lambda: [report],
        resolve_intent_context=lambda _: intent_context,
        resolve_price_context=lambda _: {},
        resolve_authorization_context=lambda _: {"final_authorization_mode": "risk_approved"},
    )


def test_hk_buy_applies_stamp_duty_both_sides():
    service = _service_with_fill(market=Market.HK, symbol="0700.HK", currency="HKD")
    entries = service.build_entries()
    assert len(entries) == 1
    entry = entries[0]
    expected_stamp = 100.0 * 100.0 * FEE_SCHEDULES[Market.HK].stamp_duty_buy
    assert abs(entry.stamp_duty - expected_stamp) < 1e-6
    assert entry.market == Market.HK
    assert entry.currency == "HKD"
    assert entry.net_amount < 0  # buy reduces cash
    assert entry.fee_schedule_version == FEE_SCHEDULE_VERSION


def test_us_sell_applies_sec_fee_only():
    service = _service_with_fill(
        market=Market.US,
        side=OrderSide.SELL,
        symbol="SPY",
        currency="USD",
        filled_quantity=200.0,
        average_price=500.0,
    )
    entries = service.build_entries()
    entry = entries[0]
    gross = 200.0 * 500.0
    expected_reg = gross * FEE_SCHEDULES[Market.US].regulatory_fee_rate_sell
    assert abs(entry.regulatory_fee - expected_reg) < 1e-6
    assert entry.stamp_duty == 0.0
    # Sell → cash in minus fees
    assert entry.net_amount > 0


def test_us_buy_has_no_regulatory_fee():
    service = _service_with_fill(market=Market.US, side=OrderSide.BUY, currency="USD")
    entries = service.build_entries()
    assert entries[0].regulatory_fee == 0.0


def test_cn_sell_applies_seller_stamp_duty():
    service = _service_with_fill(
        market=Market.CN,
        side=OrderSide.SELL,
        symbol="510300",
        asset_class=AssetClass.ETF,
        currency="CNY",
        filled_quantity=1000.0,
        average_price=4.0,
    )
    entries = service.build_entries()
    entry = entries[0]
    gross = 4000.0
    assert abs(entry.stamp_duty - gross * FEE_SCHEDULES[Market.CN].stamp_duty_sell) < 1e-6
    assert abs(entry.transfer_fee - gross * FEE_SCHEDULES[Market.CN].transfer_fee_rate) < 1e-6


def test_cn_buy_has_no_stamp_duty_but_transfer_fee():
    service = _service_with_fill(
        market=Market.CN,
        side=OrderSide.BUY,
        symbol="510300",
        asset_class=AssetClass.ETF,
        currency="CNY",
        filled_quantity=1000.0,
        average_price=4.0,
    )
    entries = service.build_entries()
    entry = entries[0]
    assert entry.stamp_duty == 0.0
    assert entry.transfer_fee > 0.0


def test_build_entries_respects_date_filter():
    service = _service_with_fill(market=Market.US, ts=datetime(2026, 4, 15, 14, 30, tzinfo=UTC))
    # Entry is on 2026-04-15; filter excludes anything after 2026-04-10.
    assert service.build_entries(end=date(2026, 4, 10)) == []
    # And include it with inclusive end.
    entries = service.build_entries(start=date(2026, 4, 1), end=date(2026, 4, 30))
    assert len(entries) == 1


def test_build_entries_respects_market_filter():
    service = _service_with_fill(market=Market.HK, currency="HKD")
    assert service.build_entries(market=Market.US) == []
    assert len(service.build_entries(market=Market.HK)) == 1


def test_summary_aggregates_by_market():
    service = _service_with_fill(market=Market.HK, currency="HKD")
    entries = service.build_entries()
    summary = service.summary(entries)
    assert summary["row_count"] == 1
    assert "HK" in summary["by_market"]
    assert summary["by_market"]["HK"]["stamp_duty"] > 0
    assert summary["fee_schedule_version"] == FEE_SCHEDULE_VERSION


def test_csv_render_has_schema_columns():
    service = _service_with_fill(market=Market.HK, currency="HKD")
    entries = service.build_entries()
    csv_text = render_csv(entries)
    header_line = csv_text.splitlines()[0]
    assert header_line.split(",") == CSV_COLUMNS
    # Data row present
    assert len(csv_text.splitlines()) == 2


def test_pending_orders_are_excluded():
    report = ExecutionReport(
        order_intent_id="intent-pending",
        broker_order_id="broker-pending",
        status=OrderStatus.SUBMITTED,
        filled_quantity=0.0,
        average_price=None,
        timestamp=datetime(2026, 4, 15, tzinfo=UTC),
        market=Market.US,
    )
    service = TradeLedgerService(
        list_orders=lambda: [report],
        resolve_intent_context=lambda _: {"symbol": "SPY", "market": "US", "side": "buy"},
        resolve_price_context=lambda _: {},
    )
    assert service.build_entries() == []


def test_slippage_converted_to_bps():
    service = _service_with_fill(market=Market.US, currency="USD")
    entries = service.build_entries()
    # Underlying slippage 0.0005 → 5 bps.
    assert entries[0].realized_slippage_bps == 5.0


def test_app_trade_ledger_export_end_to_end(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )
    # Seed one filled order directly through the execution service.
    intent = OrderIntent(
        signal_id="strat_core:sig-1",
        instrument=Instrument(
            symbol="SPY",
            market=Market.US,
            asset_class=AssetClass.ETF,
            currency="USD",
        ),
        side=OrderSide.BUY,
        quantity=10,
    )
    app.execution.submit(intent)
    app.execution.reconcile_live_state()

    payload = app.trade_ledger_export()
    assert "rows" in payload
    assert "summary" in payload
    assert payload["filters"]["market"] is None
    assert isinstance(payload["summary"]["row_count"], int)

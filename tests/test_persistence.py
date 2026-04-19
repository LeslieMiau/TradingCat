from datetime import date, datetime

from tradingcat.config import AppConfig
from tradingcat.main import TradingCatApplication
from tradingcat.domain.models import (
    AssetClass,
    Instrument,
    ManualFill,
    Market,
    OrderSide,
    Signal,
)


def test_approval_and_order_state_reload(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app_one = TradingCatApplication(config=config)
    app_one.reset_state()

    signals = list(app_one.get_signals(as_of=date(2026, 3, 7)))
    signals.append(
        Signal(
            strategy_id="test_persistence_cn",
            generated_at=datetime(2026, 3, 7, 9, 30),
            instrument=Instrument(
                symbol="510300",
                market=Market.CN,
                asset_class=AssetClass.ETF,
                currency="CNY",
            ),
            side=OrderSide.BUY,
            target_weight=0.05,
            reason="persistence regression fixture",
        )
    )
    snapshot = app_one.portfolio.snapshot()
    intents = app_one.risk.check(
        signals,
        portfolio_nav=snapshot.nav,
        drawdown=snapshot.drawdown,
        daily_pnl=snapshot.daily_pnl,
        weekly_pnl=snapshot.weekly_pnl,
    )
    for intent in intents:
        app_one.execution.submit(intent)

    app_two = TradingCatApplication(config=config)

    assert len(app_two.approvals.list_requests()) >= 1
    assert len(app_two.execution.list_orders()) >= 1


def test_manual_fill_updates_portfolio_snapshot(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()

    preview = app.preview_execution(date(2026, 3, 7))
    intent = preview["order_intents"][0]
    starting_cash = app.portfolio.snapshot().cash

    app.execution.submit(intent)
    fill = ManualFill(
        order_intent_id=intent.id,
        broker_order_id="manual-fill-1",
        external_source="broker_statement",
        filled_quantity=10,
        average_price=100.0,
        notes="seed fill",
    )
    result = app.reconcile_manual_fill(fill)

    snapshot = app.portfolio.snapshot()
    audit_events = app.audit.list_events(order_intent_id=intent.id)

    assert snapshot.cash < starting_cash
    assert any(position.instrument.symbol == intent.instrument.symbol for position in snapshot.positions)
    assert result["snapshot"].cash == snapshot.cash
    assert result["report"].status.value == "filled"
    assert audit_events[0].details["reconciliation_source"] == "broker_statement"


def test_manual_fill_import_parser(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    app = TradingCatApplication(config=config)
    app.reset_state()

    csv_text = (
        "order_intent_id,broker_order_id,filled_quantity,average_price,notes\n"
        "intent-1,manual-import-1,10,100.0,first row\n"
        "intent-2,manual-import-2,20,50.0,second row\n"
    )

    fills = app.parse_manual_fill_import(csv_text)

    assert len(fills) == 2
    assert fills[0].broker_order_id == "manual-import-1"
    assert fills[1].filled_quantity == 20

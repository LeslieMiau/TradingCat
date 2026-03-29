from __future__ import annotations

from tradingcat.domain.models import AssetClass, Instrument, ManualFill, Market, OrderIntent, OrderSide


def reset_runtime_state(app_state) -> None:
    app_state.reset_state()


def seed_execution_fill(
    app_state,
    *,
    symbol: str,
    market: Market,
    asset_class: AssetClass,
    side: OrderSide,
    quantity: float,
    expected_price: float,
    realized_price: float,
    signal_id: str,
    broker_order_id: str,
    currency: str = "USD",
    reference_source: str = "market_quote",
    external_source: str | None = None,
) -> OrderIntent:
    intent = OrderIntent(
        signal_id=signal_id,
        instrument=Instrument(symbol=symbol, market=market, asset_class=asset_class, currency=currency),
        side=side,
        quantity=quantity,
    )
    app_state.execution.register_expected_prices(
        [intent],
        {symbol: {"price": expected_price, "source": reference_source}},
    )
    app_state.execution.reconcile_manual_fill(
        ManualFill(
            order_intent_id=intent.id,
            broker_order_id=broker_order_id,
            external_source=external_source,
            filled_quantity=quantity,
            average_price=realized_price,
            side=side,
        )
    )
    return intent


def record_test_alert(
    app_state,
    *,
    severity: str,
    category: str,
    message: str,
    recovery_action: str,
    details: dict[str, str | int | float | bool],
) -> None:
    app_state.alerts._record(
        severity=severity,
        category=category,
        message=message,
        recovery_action=recovery_action,
        details=details,
    )

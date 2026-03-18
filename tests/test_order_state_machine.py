from datetime import UTC, datetime

from tradingcat.domain.models import ExecutionReport, OrderStatus
from tradingcat.services.order_state_machine import OrderStateMachine


def _report(status: OrderStatus, *, order_intent_id: str = "intent-1", broker_order_id: str = "broker-1", filled_quantity: float = 0.0):
    return ExecutionReport(
        order_intent_id=order_intent_id,
        broker_order_id=broker_order_id,
        status=status,
        filled_quantity=filled_quantity,
        timestamp=datetime(2026, 3, 8, tzinfo=UTC),
    )


def test_order_state_machine_allows_terminal_fill_after_cancel():
    machine = OrderStateMachine()

    merged = machine.merge(_report(OrderStatus.CANCELLED), _report(OrderStatus.FILLED, filled_quantity=10.0))

    assert merged.status == OrderStatus.FILLED
    assert merged.filled_quantity == 10.0


def test_order_state_machine_blocks_regression_from_submitted_to_pending():
    machine = OrderStateMachine()

    merged = machine.merge(_report(OrderStatus.SUBMITTED), _report(OrderStatus.PENDING_APPROVAL))

    assert merged.status == OrderStatus.SUBMITTED


def test_order_state_machine_keeps_rejected_terminal():
    machine = OrderStateMachine()

    merged = machine.merge(_report(OrderStatus.REJECTED), _report(OrderStatus.SUBMITTED))

    assert merged.status == OrderStatus.REJECTED

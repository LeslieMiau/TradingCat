from __future__ import annotations

from tradingcat.domain.models import ExecutionReport, OrderStatus


class OrderStateMachine:
    _priority = {
        OrderStatus.PENDING_APPROVAL: 0,
        OrderStatus.SUBMITTED: 1,
        OrderStatus.CANCELLED: 2,
        OrderStatus.REJECTED: 2,
        OrderStatus.FILLED: 3,
    }

    _allowed_transitions = {
        OrderStatus.PENDING_APPROVAL: {
            OrderStatus.PENDING_APPROVAL,
            OrderStatus.SUBMITTED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FILLED,
        },
        OrderStatus.SUBMITTED: {
            OrderStatus.SUBMITTED,
            OrderStatus.CANCELLED,
            OrderStatus.REJECTED,
            OrderStatus.FILLED,
        },
        OrderStatus.CANCELLED: {
            OrderStatus.CANCELLED,
            OrderStatus.FILLED,
        },
        OrderStatus.REJECTED: {
            OrderStatus.REJECTED,
        },
        OrderStatus.FILLED: {
            OrderStatus.FILLED,
        },
    }

    def can_transition(self, current: OrderStatus, incoming: OrderStatus) -> bool:
        return incoming in self._allowed_transitions[current]

    def merge(self, current: ExecutionReport | None, incoming: ExecutionReport) -> ExecutionReport:
        if current is None:
            return incoming
        if self.can_transition(current.status, incoming.status):
            chosen = incoming
        elif self._priority[incoming.status] > self._priority[current.status]:
            chosen = incoming
        else:
            chosen = current
        return ExecutionReport(
            order_intent_id=current.order_intent_id,
            broker_order_id=incoming.broker_order_id or current.broker_order_id,
            status=chosen.status,
            filled_quantity=max(current.filled_quantity, incoming.filled_quantity),
            average_price=incoming.average_price or current.average_price,
            message=incoming.message or current.message,
            timestamp=chosen.timestamp,
        )

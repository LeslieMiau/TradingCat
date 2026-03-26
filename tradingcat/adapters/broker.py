from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import ExecutionReport, Market, OrderIntent, OrderStatus, Position


class SimulatedBrokerAdapter:
    def __init__(self) -> None:
        self._orders: list[ExecutionReport] = []
        self._positions: list[Position] = []
        self._cash: float = 1_000_000.0

    def place_order(self, intent: OrderIntent) -> ExecutionReport:
        report = ExecutionReport(
            order_intent_id=intent.id,
            broker_order_id=f"sim-{len(self._orders) + 1}",
            status=OrderStatus.SUBMITTED,
            message="Accepted by simulated broker",
            timestamp=datetime.now(UTC),
        )
        self._orders.append(report)
        return report

    def cancel_order(self, broker_order_id: str) -> ExecutionReport:
        report = ExecutionReport(
            order_intent_id=broker_order_id,
            broker_order_id=broker_order_id,
            status=OrderStatus.CANCELLED,
            message="Cancelled in simulated broker",
        )
        self._orders.append(report)
        return report

    def get_orders(self) -> list[ExecutionReport]:
        return list(self._orders)

    def get_positions(self) -> list[Position]:
        return list(self._positions)

    def get_cash(self) -> float:
        return self._cash

    def get_cash_by_market(self) -> dict[Market, float]:
        return {
            Market.US: self._cash,
            Market.HK: self._cash,
            Market.CN: self._cash,
        }

    def reconcile_fills(self) -> list[ExecutionReport]:
        return list(self._orders)

    def health_check(self) -> dict[str, object]:
        return {"healthy": True, "detail": "Simulated broker is active"}

    def probe(self) -> dict:
        return {
            "status": "ok",
            "detail": "Simulated broker is active",
            "cash": self._cash,
            "positions": len(self._positions),
            "orders": len(self._orders),
        }


class ManualExecutionAdapter(SimulatedBrokerAdapter):
    def place_order(self, intent: OrderIntent) -> ExecutionReport:
        report = ExecutionReport(
            order_intent_id=intent.id,
            broker_order_id=f"manual-{len(self._orders) + 1}",
            status=OrderStatus.PENDING_APPROVAL,
            message="Awaiting manual execution and fill reconciliation",
        )
        self._orders.append(report)
        return report

    def probe(self) -> dict:
        return {
            "status": "ok",
            "detail": "Manual execution adapter is active",
            "cash": self._cash,
            "positions": len(self._positions),
            "orders": len(self._orders),
        }

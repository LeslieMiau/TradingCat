from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import ExecutionReport, Market, OrderIntent, OrderStatus, Position


class SimulatedBrokerAdapter:
    def __init__(self) -> None:
        self._orders: list[ExecutionReport] = []
        self._positions: list[Position] = []
        self._cash: float = 1_000_000.0

    def place_order(self, intent: OrderIntent) -> ExecutionReport:
        if intent.algo:
            if intent.algo.strategy in ["TWAP", "VWAP"]:
                # Simulate breaking a large order into e.g. 5 smaller slices
                slices = 5
                base_qty = intent.quantity / slices
                now = datetime.now(UTC)
                for i in range(slices):
                    child = ExecutionReport(
                        order_intent_id=intent.id,
                        broker_order_id=f"sim-algo-{len(self._orders) + 1}-{i}",
                        status=OrderStatus.SUBMITTED,
                        message=f"[{intent.algo.strategy} Slice {i+1}/{slices}] Accepted",
                        timestamp=now,
                        filled_quantity=base_qty,  # Mock immediate partial fill
                    )
                    self._orders.append(child)
                
                return ExecutionReport(
                    order_intent_id=intent.id,
                    broker_order_id=f"sim-algo-parent-{len(self._orders)}",
                    status=OrderStatus.SUBMITTED,
                    message=f"Parent Algo {intent.algo.strategy} Registered, slicing active.",
                    timestamp=now,
                )

            elif intent.algo.strategy == "LADDER":
                levels = intent.algo.levels or 5
                p_start = intent.algo.price_start or 100.0
                p_end = intent.algo.price_end or 90.0
                base_qty = intent.quantity / levels
                price_step = (p_end - p_start) / (levels - 1) if levels > 1 else 0
                now = datetime.now(UTC)
                for i in range(levels):
                    level_price = p_start + (i * price_step)
                    child = ExecutionReport(
                        order_intent_id=intent.id,
                        broker_order_id=f"sim-ladder-{len(self._orders) + 1}-{i}",
                        status=OrderStatus.SUBMITTED,
                        message=f"[LADDER Level {i+1}/{levels}] Limit @ {level_price:.2f}",
                        timestamp=now,
                        average_price=level_price,
                        filled_quantity=base_qty,  # Mock immediate fill for simulation
                    )
                    self._orders.append(child)
                
                return ExecutionReport(
                    order_intent_id=intent.id,
                    broker_order_id=f"sim-ladder-parent-{len(self._orders)}",
                    status=OrderStatus.SUBMITTED,
                    message=f"Parent Ladder Registered: {levels} levels from {p_start} to {p_end}",
                    timestamp=now,
                )

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

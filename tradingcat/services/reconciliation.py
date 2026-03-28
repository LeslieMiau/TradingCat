from __future__ import annotations

from tradingcat.adapters.base import BrokerAdapter
from tradingcat.domain.models import ExecutionReport, ManualFill, OrderStatus, ReconciliationSummary
from tradingcat.services.order_state_machine import OrderStateMachine


class ReconciliationService:
    def __init__(self, state_machine: OrderStateMachine) -> None:
        self._state_machine = state_machine

    def reconcile_manual_fill(
        self,
        fill: ManualFill,
        *,
        expected_prices: dict[str, dict[str, object]],
    ) -> ExecutionReport:
        computed_slippage = fill.slippage
        baseline = expected_prices.get(fill.order_intent_id)
        if computed_slippage is None and baseline is not None and fill.average_price > 0:
            reference_price = float(baseline.get("reference_price", 0.0))
            if reference_price > 0:
                multiplier = 1.0 if fill.side.value == "buy" else -1.0
                computed_slippage = multiplier * (fill.average_price - reference_price) / reference_price

        return ExecutionReport(
            order_intent_id=fill.order_intent_id,
            broker_order_id=fill.broker_order_id,
            status=OrderStatus.FILLED,
            filled_quantity=fill.filled_quantity,
            average_price=fill.average_price,
            message=fill.notes,
            emotional_tag=fill.emotional_tag,
            slippage=computed_slippage,
        )

    def reconcile_live_state(
        self,
        *,
        live_broker: BrokerAdapter,
        orders: dict[str, ExecutionReport],
        fill_fingerprints: set[str],
    ) -> tuple[ReconciliationSummary, dict[str, ExecutionReport], set[str]]:
        updated_orders = dict(orders)
        updated_fingerprints = set(fill_fingerprints)
        order_updates = 0
        fill_updates = 0
        duplicate_fills = 0
        unmatched_broker_orders = 0
        applied_fill_order_ids: list[str] = []

        known_by_broker_order_id = {
            report.broker_order_id: intent_id
            for intent_id, report in updated_orders.items()
            if report.broker_order_id
        }

        for broker_order in live_broker.get_orders():
            intent_id = known_by_broker_order_id.get(broker_order.broker_order_id)
            if intent_id is None:
                unmatched_broker_orders += 1
                continue
            current = updated_orders[intent_id]
            merged = self.merge_report(current, broker_order)
            if merged != current:
                updated_orders[intent_id] = merged
                order_updates += 1

        for fill in live_broker.reconcile_fills():
            fingerprint = self.fill_fingerprint(fill)
            if fingerprint in updated_fingerprints:
                duplicate_fills += 1
                continue
            updated_fingerprints.add(fingerprint)
            intent_id = known_by_broker_order_id.get(fill.broker_order_id, fill.order_intent_id)
            existing = updated_orders.get(intent_id)
            updated_orders[intent_id] = self.merge_report(existing, fill) if existing else fill
            fill_updates += 1
            applied_fill_order_ids.append(intent_id)

        summary = ReconciliationSummary(
            order_updates=order_updates,
            fill_updates=fill_updates,
            duplicate_fills=duplicate_fills,
            unmatched_broker_orders=unmatched_broker_orders,
            state_counts=self.order_state_summary(updated_orders),
            applied_fill_order_ids=applied_fill_order_ids,
        )
        return summary, updated_orders, updated_fingerprints

    def execution_quality_summary(self, *, orders: dict[str, ExecutionReport], expected_prices: dict[str, dict[str, object]]) -> dict[str, object]:
        samples: list[dict[str, object]] = []
        missing_baselines = 0
        for report in orders.values():
            if report.status != OrderStatus.FILLED or report.average_price is None or report.average_price <= 0:
                continue
            baseline = expected_prices.get(report.order_intent_id)
            if baseline is None:
                missing_baselines += 1
                continue
            reference_price = float(baseline["reference_price"])
            slippage_ratio = abs(report.average_price - reference_price) / reference_price if reference_price > 0 else 0.0
            asset_class = str(baseline.get("asset_class", "stock"))
            if asset_class == "option":
                threshold = 0.10
                metric = round(slippage_ratio, 4)
                metric_name = "premium_deviation"
                within_threshold = metric <= threshold
            else:
                threshold = 20.0
                metric = round(slippage_ratio * 10_000, 2)
                metric_name = "slippage_bps"
                within_threshold = metric <= threshold
            samples.append(
                {
                    "order_intent_id": report.order_intent_id,
                    "broker_order_id": report.broker_order_id,
                    "symbol": baseline.get("symbol"),
                    "market": baseline.get("market"),
                    "asset_class": asset_class,
                    "reference_price": reference_price,
                    "fill_price": report.average_price,
                    metric_name: metric,
                    "threshold": threshold,
                    "within_threshold": within_threshold,
                    "emotional_tag": report.emotional_tag,
                    "recorded_slippage": report.slippage,
                }
            )

        equity_samples = [sample for sample in samples if sample["asset_class"] != "option"]
        option_samples = [sample for sample in samples if sample["asset_class"] == "option"]
        equity_breaches = sum(1 for sample in equity_samples if not sample["within_threshold"])
        option_breaches = sum(1 for sample in option_samples if not sample["within_threshold"])
        return {
            "filled_samples": len(samples),
            "missing_baselines": missing_baselines,
            "equity_samples": len(equity_samples),
            "option_samples": len(option_samples),
            "equity_breaches": equity_breaches,
            "option_breaches": option_breaches,
            "equity_slippage_limit_bps": 20.0,
            "option_premium_deviation_limit": 0.10,
            "within_limits": equity_breaches == 0 and option_breaches == 0,
            "samples": samples,
        }

    def order_state_summary(self, orders: dict[str, ExecutionReport]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for order in orders.values():
            counts.setdefault(order.status.value, 0)
            counts[order.status.value] += 1
        return counts

    def merge_report(self, current: ExecutionReport | None, incoming: ExecutionReport) -> ExecutionReport:
        return self._state_machine.merge(current, incoming)

    def fill_fingerprint(self, report: ExecutionReport) -> str:
        return "|".join(
            [
                report.broker_order_id,
                f"{report.filled_quantity:.6f}",
                f"{(report.average_price or 0.0):.6f}",
                report.status.value,
            ]
        )

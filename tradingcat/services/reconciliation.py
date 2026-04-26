from __future__ import annotations

from tradingcat.adapters.base import BrokerAdapter
from tradingcat.domain.models import ExecutionReport, ManualFill, OrderStatus, PortfolioSnapshot, ReconciliationSummary
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
                    "side": baseline.get("side"),
                    "timestamp": report.timestamp.isoformat(),
                    "reference_price": reference_price,
                    "reference_source": baseline.get("reference_source", "market_quote"),
                    "fill_price": report.average_price,
                    "filled_quantity": report.filled_quantity,
                    metric_name: metric,
                    "threshold": threshold,
                    "within_threshold": within_threshold,
                    "emotional_tag": report.emotional_tag,
                    "recorded_slippage": report.slippage,
                }
            )

        stock_samples = [sample for sample in samples if sample["asset_class"] == "stock"]
        etf_samples = [sample for sample in samples if sample["asset_class"] == "etf"]
        option_samples = [sample for sample in samples if sample["asset_class"] == "option"]
        equity_samples = [sample for sample in samples if sample["asset_class"] != "option"]
        asset_class_summary = {
            "stock": self._asset_class_quality_summary("stock", stock_samples),
            "etf": self._asset_class_quality_summary("etf", etf_samples),
            "option": self._asset_class_quality_summary("option", option_samples),
        }
        stock_breaches = sum(1 for sample in stock_samples if not sample["within_threshold"])
        etf_breaches = sum(1 for sample in etf_samples if not sample["within_threshold"])
        equity_breaches = sum(1 for sample in equity_samples if not sample["within_threshold"])
        option_breaches = sum(1 for sample in option_samples if not sample["within_threshold"])
        return {
            "filled_samples": len(samples),
            "missing_baselines": missing_baselines,
            "stock_samples": len(stock_samples),
            "etf_samples": len(etf_samples),
            "equity_samples": len(equity_samples),
            "option_samples": len(option_samples),
            "stock_breaches": stock_breaches,
            "etf_breaches": etf_breaches,
            "equity_breaches": equity_breaches,
            "option_breaches": option_breaches,
            "equity_slippage_limit_bps": 20.0,
            "option_premium_deviation_limit": 0.10,
            "within_limits": equity_breaches == 0 and option_breaches == 0,
            "asset_class_summary": asset_class_summary,
            "samples": samples,
        }

    def transaction_cost_summary(self, *, orders: dict[str, ExecutionReport], expected_prices: dict[str, dict[str, object]]) -> dict[str, object]:
        quality = self.execution_quality_summary(orders=orders, expected_prices=expected_prices)
        samples = [self._tca_sample(sample) for sample in quality["samples"]]
        direction_summary = {
            "buy": self._tca_bucket_summary([sample for sample in samples if sample["direction"] == "buy"]),
            "sell": self._tca_bucket_summary([sample for sample in samples if sample["direction"] == "sell"]),
        }
        total_filled_quantity = round(sum(float(sample["filled_quantity"]) for sample in samples), 4) if samples else 0.0
        return {
            "sample_count": len(samples),
            "filled_quantity": total_filled_quantity,
            "missing_baselines": quality["missing_baselines"],
            "insufficient_data": len(samples) == 0,
            "message": "当前还没有带基线的执行样本可用。" if not samples else f"TCA 基于 {len(samples)} 笔已成交样本构建。",
            "asset_class_summary": quality["asset_class_summary"],
            "direction_summary": direction_summary,
            "samples": samples,
        }

    def build_trace(
        self,
        *,
        order_intent_id: str,
        report: ExecutionReport,
        fill_source: str,
        before_snapshot: PortfolioSnapshot,
        after_snapshot: PortfolioSnapshot,
        intent_context: dict[str, object],
        price_context: dict[str, object],
        authorization_context: dict[str, object],
    ) -> dict[str, object]:
        return {
            "order_intent_id": order_intent_id,
            "broker_order_id": report.broker_order_id,
            "fill_source": fill_source,
            "order": {
                "symbol": intent_context.get("symbol"),
                "market": intent_context.get("market"),
                "asset_class": intent_context.get("asset_class"),
                "side": intent_context.get("side"),
                "strategy_id": intent_context.get("strategy_id"),
                "status": report.status.value,
                "filled_quantity": report.filled_quantity,
                "average_price": report.average_price,
            },
            "pricing": price_context,
            "authorization": authorization_context,
            "portfolio_before": self._snapshot_summary(before_snapshot),
            "portfolio_after": self._snapshot_summary(after_snapshot),
            "portfolio_effect": {
                "nav_delta": round(after_snapshot.nav - before_snapshot.nav, 4),
                "cash_delta": round(after_snapshot.cash - before_snapshot.cash, 4),
                "position_count_delta": len(after_snapshot.positions) - len(before_snapshot.positions),
            },
        }

    def _asset_class_quality_summary(self, asset_class: str, samples: list[dict[str, object]]) -> dict[str, object]:
        metric_name = "premium_deviation" if asset_class == "option" else "slippage_bps"
        threshold = 0.10 if asset_class == "option" else 20.0
        sample_count = len(samples)
        if sample_count == 0:
            return {
                "asset_class": asset_class,
                "sample_count": 0,
                "breach_count": 0,
                "breach_ratio": None,
                "within_limits": None,
                "metric_name": metric_name,
                "threshold": threshold,
                "average_metric": None,
                "max_metric": None,
                "severity": "insufficient_data",
                "message": f"当前还没有已成交的 {asset_class} 样本。",
            }

        metric_values = [float(sample[metric_name]) for sample in samples]
        breach_count = sum(1 for sample in samples if not sample["within_threshold"])
        breach_ratio = breach_count / sample_count
        rounding = 4 if asset_class == "option" else 2
        severity = "info"
        message = f"All filled {asset_class} samples are within threshold."
        if breach_count > 0:
            severity = "error" if sample_count >= 3 and breach_ratio >= 0.5 else "warning"
            message = (
                f"{breach_count}/{sample_count} filled {asset_class} samples breached threshold."
                if severity == "warning"
                else f"Most filled {asset_class} samples breached threshold."
            )
        return {
            "asset_class": asset_class,
            "sample_count": sample_count,
            "breach_count": breach_count,
            "breach_ratio": round(breach_ratio, 4),
            "within_limits": breach_count == 0,
            "metric_name": metric_name,
            "threshold": threshold,
            "average_metric": round(sum(metric_values) / sample_count, rounding),
            "max_metric": round(max(metric_values), rounding),
            "severity": severity,
            "message": message,
        }

    def _tca_sample(self, sample: dict[str, object]) -> dict[str, object]:
        is_option = sample["asset_class"] == "option"
        deviation_metric = "premium_deviation" if is_option else "slippage_bps"
        return {
            "order_intent_id": sample["order_intent_id"],
            "broker_order_id": sample["broker_order_id"],
            "symbol": sample["symbol"],
            "market": sample["market"],
            "asset_class": sample["asset_class"],
            "direction": sample.get("side"),
            "timestamp": sample.get("timestamp"),
            "filled_quantity": sample.get("filled_quantity", 0.0),
            "expected_price": sample["reference_price"],
            "realized_price": sample["fill_price"],
            "reference_source": sample["reference_source"],
            "deviation_metric": deviation_metric,
            "deviation_value": sample[deviation_metric],
            "threshold": sample["threshold"],
            "within_threshold": sample["within_threshold"],
            "recorded_slippage": sample["recorded_slippage"],
        }

    def _tca_bucket_summary(self, samples: list[dict[str, object]]) -> dict[str, object]:
        if not samples:
            return {
                "sample_count": 0,
                "filled_quantity": 0.0,
                "average_slippage_bps": None,
                "average_premium_deviation": None,
                "message": "当前方向没有可用样本。",
            }

        equity_values = [float(sample["deviation_value"]) for sample in samples if sample["deviation_metric"] == "slippage_bps"]
        option_values = [float(sample["deviation_value"]) for sample in samples if sample["deviation_metric"] == "premium_deviation"]
        return {
            "sample_count": len(samples),
            "filled_quantity": round(sum(float(sample["filled_quantity"]) for sample in samples), 4),
            "average_slippage_bps": round(sum(equity_values) / len(equity_values), 2) if equity_values else None,
            "average_premium_deviation": round(sum(option_values) / len(option_values), 4) if option_values else None,
            "message": f"{len(samples)} samples in this direction.",
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
        if report.fill_id:
            return f"fill:{report.fill_id}"
        return "|".join(
            [
                report.broker_order_id,
                f"{report.filled_quantity:.6f}",
                f"{(report.average_price or 0.0):.6f}",
                report.status.value,
            ]
        )

    @staticmethod
    def _snapshot_summary(snapshot: PortfolioSnapshot) -> dict[str, object]:
        return {
            "timestamp": snapshot.timestamp,
            "nav": snapshot.nav,
            "cash": snapshot.cash,
            "position_count": len(snapshot.positions),
        }

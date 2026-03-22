from __future__ import annotations

import threading

from tradingcat.adapters.base import BrokerAdapter
from tradingcat.domain.models import ExecutionReport, ManualFill, OrderIntent, OrderStatus, ReconciliationSummary
from tradingcat.repositories.state import ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.order_state_machine import OrderStateMachine


class ExecutionService:
    def __init__(
        self,
        live_broker: BrokerAdapter,
        manual_broker: BrokerAdapter,
        approvals: ApprovalService,
        repository: OrderRepository,
        state_repository: ExecutionStateRepository,
    ) -> None:
        self._live_broker = live_broker
        self._manual_broker = manual_broker
        self._approvals = approvals
        self._repository = repository
        self._state_repository = state_repository
        self._lock = threading.Lock()
        self._orders = repository.load()
        self._intents: dict[str, OrderIntent] = {}
        self._state_machine = OrderStateMachine()
        raw_state = state_repository.load()
        self._fill_fingerprints: set[str] = set(raw_state.get("fill_fingerprints", []))
        self._expected_prices: dict[str, dict[str, object]] = {
            key: value
            for key, value in raw_state.get("expected_prices", {}).items()
            if isinstance(value, dict)
        }
        self._intent_metadata: dict[str, dict[str, object]] = {
            key: value
            for key, value in raw_state.get("intent_metadata", {}).items()
            if isinstance(value, dict)
        }
        self._authorizations: dict[str, dict[str, object]] = {
            key: value
            for key, value in raw_state.get("authorizations", {}).items()
            if isinstance(value, dict)
        }

    def register_expected_prices(self, intents: list[OrderIntent], prices: dict[str, float]) -> None:
        with self._lock:
            updated = False
            for intent in intents:
                reference_price = prices.get(intent.instrument.symbol)
                if reference_price is None or reference_price <= 0:
                    continue
                self._expected_prices[intent.id] = {
                    "symbol": intent.instrument.symbol,
                    "market": intent.instrument.market.value,
                    "asset_class": intent.instrument.asset_class.value,
                    "reference_price": float(reference_price),
                }
                updated = True
            if updated:
                self._save_state()

    def submit(self, intent: OrderIntent) -> ExecutionReport:
        with self._lock:
            self._intents[intent.id] = intent
            self._register_intent_metadata(intent)
            if intent.requires_approval:
                approval = self._approvals.create_request(intent)
                self._authorizations[intent.id] = {
                    "mode": "manual_pending",
                    "requires_approval": True,
                    "approval_request_id": approval.id,
                    "approval_status": approval.status.value,
                }
                report = self._manual_broker.place_order(intent)
            else:
                self._authorizations[intent.id] = {
                    "mode": "risk_approved",
                    "requires_approval": False,
                    "approval_request_id": None,
                    "approval_status": "not_required",
                }
                report = self._live_broker.place_order(intent)
            self._orders[intent.id] = report
            self._save_state()
            return report

    def submit_approved(self, request_id: str) -> ExecutionReport:
        with self._lock:
            request = self._approvals.get(request_id)
            self._register_intent_metadata(request.order_intent)
            self._authorizations[request.order_intent.id] = {
                "mode": "manual_approved",
                "requires_approval": True,
                "approval_request_id": request.id,
                "approval_status": request.status.value,
                "decision_reason": request.decision_reason,
            }
            report = self._manual_broker.place_order(request.order_intent)
            self._orders[request.order_intent.id] = report
            self._save_state()
            return report

    def reconcile_manual_fill(self, fill: ManualFill) -> ExecutionReport:
        with self._lock:
            report = ExecutionReport(
                order_intent_id=fill.order_intent_id,
                broker_order_id=fill.broker_order_id,
                status=OrderStatus.FILLED,
                filled_quantity=fill.filled_quantity,
                average_price=fill.average_price,
                message=fill.notes,
            )
            self._orders[fill.order_intent_id] = report
            self._fill_fingerprints.add(self._fill_fingerprint(report))
            self._authorizations.setdefault(
                fill.order_intent_id,
                {
                    "mode": "manual_fill_external",
                    "requires_approval": True,
                    "approval_request_id": None,
                    "approval_status": "external_fill",
                },
            )
            self._save_state()
            return report

    def cancel(self, broker_order_id: str) -> ExecutionReport:
        with self._lock:
            matching_order = next((order for order in self._orders.values() if order.broker_order_id == broker_order_id), None)
            if matching_order and broker_order_id.startswith("manual-"):
                report = self._manual_broker.cancel_order(broker_order_id)
            else:
                report = self._live_broker.cancel_order(broker_order_id)
            key = matching_order.order_intent_id if matching_order else broker_order_id
            self._orders[key] = report
            self._save_state()
            return report

    def list_orders(self) -> list[ExecutionReport]:
        return list(self._orders.values())

    def cancel_open_orders(self) -> dict[str, list[ExecutionReport] | list[dict[str, str]]]:
        reports: list[ExecutionReport] = []
        failures: list[dict[str, str]] = []
        seen: set[str] = set()
        for order in self._live_broker.get_orders():
            if order.status != OrderStatus.SUBMITTED:
                continue
            if order.broker_order_id in seen:
                continue
            seen.add(order.broker_order_id)
            try:
                reports.append(self.cancel(order.broker_order_id))
            except Exception as exc:
                failures.append(
                    {
                        "broker_order_id": order.broker_order_id,
                        "error": str(exc),
                    }
                )
        return {
            "cancelled": reports,
            "failed": failures,
        }

    def clear(self) -> None:
        with self._lock:
            self._orders = {}
            self._fill_fingerprints = set()
            self._intent_metadata = {}
            self._authorizations = {}
            self._expected_prices = {}
            self._save_state()

    def reconcile_live_state(self) -> ReconciliationSummary:
        with self._lock:
            order_updates = 0
            fill_updates = 0
            duplicate_fills = 0
            unmatched_broker_orders = 0
            applied_fill_order_ids: list[str] = []

            known_by_broker_order_id = {
                report.broker_order_id: intent_id
                for intent_id, report in self._orders.items()
                if report.broker_order_id
            }

            for broker_order in self._live_broker.get_orders():
                intent_id = known_by_broker_order_id.get(broker_order.broker_order_id)
                if intent_id is None:
                    unmatched_broker_orders += 1
                    continue
                current = self._orders[intent_id]
                merged = self._merge_report(current, broker_order)
                if merged != current:
                    self._orders[intent_id] = merged
                    order_updates += 1

            for fill in self._live_broker.reconcile_fills():
                fingerprint = self._fill_fingerprint(fill)
                if fingerprint in self._fill_fingerprints:
                    duplicate_fills += 1
                    continue
                self._fill_fingerprints.add(fingerprint)
                intent_id = known_by_broker_order_id.get(fill.broker_order_id, fill.order_intent_id)
                existing = self._orders.get(intent_id)
                self._orders[intent_id] = self._merge_report(existing, fill) if existing else fill
                fill_updates += 1
                applied_fill_order_ids.append(intent_id)

            self._save_state()
            return ReconciliationSummary(
                order_updates=order_updates,
                fill_updates=fill_updates,
                duplicate_fills=duplicate_fills,
                unmatched_broker_orders=unmatched_broker_orders,
                state_counts=self.order_state_summary(),
                applied_fill_order_ids=applied_fill_order_ids,
            )

    def order_state_summary(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for order in self._orders.values():
            counts.setdefault(order.status.value, 0)
            counts[order.status.value] += 1
        return counts

    def execution_quality_summary(self) -> dict[str, object]:
        samples: list[dict[str, object]] = []
        missing_baselines = 0
        for report in self._orders.values():
            if report.status != OrderStatus.FILLED or report.average_price is None or report.average_price <= 0:
                continue
            baseline = self._expected_prices.get(report.order_intent_id)
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

    def authorization_summary(self) -> dict[str, object]:
        authorized = 0
        unauthorized = 0
        samples: list[dict[str, object]] = []
        for report in self._orders.values():
            auth = self._authorizations.get(report.order_intent_id)
            is_authorized = auth is not None and (
                not auth.get("requires_approval", False)
                or auth.get("approval_status") in {"approved", "external_fill", "not_required"}
                or report.status == OrderStatus.PENDING_APPROVAL
            )
            if is_authorized:
                authorized += 1
            else:
                unauthorized += 1
            samples.append(
                {
                    "order_intent_id": report.order_intent_id,
                    "broker_order_id": report.broker_order_id,
                    "status": report.status.value,
                    "authorized": is_authorized,
                    "authorization_mode": auth.get("mode") if auth else None,
                    "approval_request_id": auth.get("approval_request_id") if auth else None,
                    "approval_status": auth.get("approval_status") if auth else None,
                }
            )
        return {
            "order_count": len(self._orders),
            "authorized_count": authorized,
            "unauthorized_count": unauthorized,
            "all_authorized": unauthorized == 0,
            "orders": samples,
        }

    def resolve_intent_context(self, order_intent_id: str) -> dict[str, object] | None:
        return self._intent_metadata.get(order_intent_id)

    def _merge_report(self, current: ExecutionReport | None, incoming: ExecutionReport) -> ExecutionReport:
        return self._state_machine.merge(current, incoming)

    def _fill_fingerprint(self, report: ExecutionReport) -> str:
        return "|".join(
            [
                report.broker_order_id,
                f"{report.filled_quantity:.6f}",
                f"{(report.average_price or 0.0):.6f}",
                report.status.value,
            ]
        )

    def _register_intent_metadata(self, intent: OrderIntent) -> None:
        self._intent_metadata[intent.id] = {
            "symbol": intent.instrument.symbol,
            "market": intent.instrument.market.value,
            "asset_class": intent.instrument.asset_class.value,
            "currency": intent.instrument.currency,
            "side": intent.side.value,
            "strategy_id": self._infer_strategy_id(intent),
        }

    @staticmethod
    def _infer_strategy_id(intent: OrderIntent) -> str:
        signal_id = intent.signal_id or ""
        if signal_id.startswith("broker-check:"):
            return "broker_probe"
        if ":" in signal_id:
            prefix = signal_id.split(":", 1)[0]
            if prefix:
                return prefix
        return "unknown"

    def _save_state(self) -> None:
        self._repository.save(self._orders)
        self._state_repository.save(
            {
                "fill_fingerprints": sorted(self._fill_fingerprints),
                "expected_prices": self._expected_prices,
                "intent_metadata": self._intent_metadata,
                "authorizations": self._authorizations,
            }
        )

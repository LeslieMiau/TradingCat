from __future__ import annotations

import logging
import threading

from tradingcat.adapters.base import BrokerAdapter
from tradingcat.domain.models import ExecutionReport, ManualFill, OrderIntent, OrderStatus, ReconciliationSummary
from tradingcat.repositories.state import ExecutionStateRepository, OrderRepository
from tradingcat.services.approval import ApprovalService
from tradingcat.services.order_state_machine import OrderStateMachine
from tradingcat.services.reconciliation import ReconciliationService


logger = logging.getLogger(__name__)


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
        self._reconciliation = ReconciliationService(self._state_machine)
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
            else:
                self._authorizations[intent.id] = {
                    "mode": "risk_approved",
                    "requires_approval": False,
                    "approval_request_id": None,
                    "approval_status": "not_required",
                }
            try:
                report = self._manual_broker.place_order(intent) if intent.requires_approval else self._live_broker.place_order(intent)
            except Exception:
                logger.exception(
                    "Order submission failed",
                    extra={"order_intent_id": intent.id, "symbol": intent.instrument.symbol, "market": intent.instrument.market.value},
                )
                raise
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
            try:
                report = self._manual_broker.place_order(request.order_intent)
            except Exception:
                logger.exception("Approved manual order submission failed", extra={"approval_request_id": request.id})
                raise
            self._orders[request.order_intent.id] = report
            self._save_state()
            return report

    def reconcile_manual_fill(self, fill: ManualFill) -> ExecutionReport:
        with self._lock:
            report = self._reconciliation.reconcile_manual_fill(fill, expected_prices=self._expected_prices)
            self._orders[fill.order_intent_id] = report
            self._fill_fingerprints.add(self._reconciliation.fill_fingerprint(report))
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

    def get_order(self, order_intent_id: str) -> ExecutionReport | None:
        return self._orders.get(order_intent_id)

    def get_registered_intent(self, order_intent_id: str) -> OrderIntent | None:
        return self._intents.get(order_intent_id)

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
                logger.exception("Cancel open order failed", extra={"broker_order_id": order.broker_order_id})
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
            self._intents = {}
            self._fill_fingerprints = set()
            self._intent_metadata = {}
            self._authorizations = {}
            self._expected_prices = {}
            self._save_state()

    def reconcile_live_state(self) -> ReconciliationSummary:
        with self._lock:
            summary, updated_orders, updated_fingerprints = self._reconciliation.reconcile_live_state(
                live_broker=self._live_broker,
                orders=self._orders,
                fill_fingerprints=self._fill_fingerprints,
            )
            self._orders = updated_orders
            self._fill_fingerprints = updated_fingerprints
            self._save_state()
            return summary

    def order_state_summary(self) -> dict[str, int]:
        return self._reconciliation.order_state_summary(self._orders)

    def execution_quality_summary(self) -> dict[str, object]:
        return self._reconciliation.execution_quality_summary(orders=self._orders, expected_prices=self._expected_prices)

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

    def update_order_report(self, order_intent_id: str, **changes: object) -> ExecutionReport:
        with self._lock:
            report = self._orders[order_intent_id]
            updated = report.model_copy(update=changes)
            self._orders[order_intent_id] = updated
            self._save_state()
            return updated

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

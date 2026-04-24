"""Daily trade-ledger reconciliation audit.

Cross-checks the derived ``TradeLedgerEntry`` rows against the underlying
``ExecutionReport`` population on the same trade date. This is the second
layer of "对账零差异" evidence required by PLAN.md Stage C:

- Portfolio reconciliation catches cash/position drift on the broker balance.
- Execution reconciliation catches duplicate fills and unmatched broker
  orders inside the live-state reconcile loop.
- *This* audit catches the remaining silent-failure class: a filled order
  that the ledger pipeline quietly dropped (missing intent context, fee
  lookup error, schedule mismatch, etc.).

The service is pure: it consumes already-persisted execution state via the
same callables ``TradeLedgerService`` takes, so it stays decoupled from the
broker adapter and testable with plain in-memory fixtures.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, Iterable
from uuid import uuid4

from tradingcat.domain.models import (
    ExecutionReport,
    OrderStatus,
    TradeLedgerEntry,
    TradeLedgerReconciliationRun,
)
from tradingcat.repositories.state import TradeLedgerReconciliationRunRepository


AMOUNT_DRIFT_RELATIVE_TOLERANCE = 1e-4
DRIFT_INCIDENT_THRESHOLD = 3
CRITICAL_DRIFT_PCT = 0.01  # 1% single-row gross-amount deviation is critical
TOP_FINDINGS_LIMIT = 10


class TradeLedgerReconciliationService:
    """Daily audit that persists drift between execution reports and ledger rows."""

    def __init__(
        self,
        repository: TradeLedgerReconciliationRunRepository,
        *,
        list_orders: Callable[[], Iterable[ExecutionReport]],
        build_ledger_entries: Callable[..., list[TradeLedgerEntry]],
    ) -> None:
        self._repository = repository
        self._list_orders = list_orders
        self._build_entries = build_ledger_entries
        self._runs = repository.load()

    def capture(
        self,
        *,
        as_of: date | None = None,
        notes: list[str] | None = None,
    ) -> TradeLedgerReconciliationRun:
        target = as_of or date.today()
        existing = self._runs.get(target.isoformat())

        broker_fills = self._fills_on(target)
        ledger_entries = self._build_entries(start=target, end=target)

        broker_index = {self._key(report): report for report in broker_fills}
        ledger_index = {self._entry_key(entry): entry for entry in ledger_entries}

        missing_ledger: list[dict[str, object]] = []
        for key, report in broker_index.items():
            if key not in ledger_index:
                missing_ledger.append(
                    {
                        "kind": "missing_ledger_entry",
                        "order_intent_id": report.order_intent_id,
                        "broker_order_id": report.broker_order_id,
                        "fill_id": report.fill_id,
                        "filled_quantity": float(report.filled_quantity),
                        "average_price": float(report.average_price or 0.0),
                        "timestamp": report.timestamp.isoformat(),
                    }
                )

        missing_broker: list[dict[str, object]] = []
        for key, entry in ledger_index.items():
            if key not in broker_index:
                missing_broker.append(
                    {
                        "kind": "missing_broker_fill",
                        "order_intent_id": entry.order_intent_id,
                        "broker_order_id": entry.broker_order_id,
                        "fill_id": entry.fill_id,
                        "quantity": float(entry.quantity),
                        "price": float(entry.price),
                        "trade_datetime": entry.trade_datetime.isoformat(),
                    }
                )

        amount_drift: list[dict[str, object]] = []
        max_drift_pct = 0.0
        for key, entry in ledger_index.items():
            report = broker_index.get(key)
            if report is None:
                continue
            broker_gross = float(report.filled_quantity) * float(report.average_price or 0.0)
            ledger_gross = float(entry.gross_amount)
            if broker_gross == 0.0 and ledger_gross == 0.0:
                continue
            denom = max(abs(broker_gross), abs(ledger_gross), 1e-9)
            drift_pct = abs(broker_gross - ledger_gross) / denom
            if drift_pct > AMOUNT_DRIFT_RELATIVE_TOLERANCE:
                max_drift_pct = max(max_drift_pct, drift_pct)
                amount_drift.append(
                    {
                        "kind": "amount_drift",
                        "order_intent_id": entry.order_intent_id,
                        "broker_order_id": entry.broker_order_id,
                        "fill_id": entry.fill_id,
                        "symbol": entry.symbol,
                        "broker_gross": round(broker_gross, 6),
                        "ledger_gross": round(ledger_gross, 6),
                        "drift_pct": round(drift_pct, 6),
                    }
                )

        findings = sorted(
            missing_ledger + missing_broker + amount_drift,
            key=lambda item: float(item.get("drift_pct", 1.0)) if item["kind"] == "amount_drift" else 1.0,
            reverse=True,
        )[:TOP_FINDINGS_LIMIT]

        status = self._classify(
            missing_ledger_count=len(missing_ledger),
            missing_broker_count=len(missing_broker),
            amount_drift_count=len(amount_drift),
            max_drift_pct=max_drift_pct,
        )

        run = TradeLedgerReconciliationRun(
            id=existing.id if existing else str(uuid4()),
            as_of=target,
            broker_fill_count=len(broker_fills),
            ledger_entry_count=len(ledger_entries),
            missing_ledger_count=len(missing_ledger),
            missing_broker_count=len(missing_broker),
            amount_drift_count=len(amount_drift),
            max_amount_drift_pct=round(max_drift_pct, 6),
            top_findings=findings,
            status=status,
            notes=list(notes or []),
        )
        self._runs[target.isoformat()] = run
        self._repository.save(self._runs)
        return run

    def list_runs(self) -> list[TradeLedgerReconciliationRun]:
        return sorted(self._runs.values(), key=lambda item: item.as_of, reverse=True)

    def latest(self) -> TradeLedgerReconciliationRun | None:
        runs = self.list_runs()
        return runs[0] if runs else None

    def timeline(self, *, window_days: int = 30) -> dict[str, object]:
        today = date.today()
        window_start = today - timedelta(days=max(window_days - 1, 0))
        points = [run for run in self.list_runs() if window_start <= run.as_of <= today]
        points.sort(key=lambda item: item.as_of)
        counts = {"ok": 0, "drift": 0, "critical": 0}
        for run in points:
            counts[run.status] = counts.get(run.status, 0) + 1
        latest = points[-1] if points else None
        return {
            "window_days": window_days,
            "points": [run.model_dump(mode="json") for run in points],
            "summary": {
                "run_count": len(points),
                "ok_count": counts.get("ok", 0),
                "drift_count": counts.get("drift", 0),
                "critical_count": counts.get("critical", 0),
                "latest_status": latest.status if latest else None,
                "latest_as_of": latest.as_of.isoformat() if latest else None,
                "latest_missing_ledger_count": latest.missing_ledger_count if latest else 0,
                "latest_missing_broker_count": latest.missing_broker_count if latest else 0,
                "latest_amount_drift_count": latest.amount_drift_count if latest else 0,
            },
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fills_on(self, target: date) -> list[ExecutionReport]:
        fills: list[ExecutionReport] = []
        for report in self._list_orders():
            if report.status != OrderStatus.FILLED:
                continue
            if report.filled_quantity <= 0 or report.average_price is None:
                continue
            timestamp = report.timestamp if isinstance(report.timestamp, datetime) else None
            if timestamp is None or timestamp.date() != target:
                continue
            fills.append(report)
        return fills

    @staticmethod
    def _key(report: ExecutionReport) -> tuple[str, str, str]:
        return (
            report.order_intent_id or "",
            report.broker_order_id or "",
            report.fill_id or "",
        )

    @staticmethod
    def _entry_key(entry: TradeLedgerEntry) -> tuple[str, str, str]:
        return (
            entry.order_intent_id or "",
            entry.broker_order_id or "",
            entry.fill_id or "",
        )

    @staticmethod
    def _classify(
        *,
        missing_ledger_count: int,
        missing_broker_count: int,
        amount_drift_count: int,
        max_drift_pct: float,
    ) -> str:
        total_incidents = missing_ledger_count + missing_broker_count + amount_drift_count
        if total_incidents == 0:
            return "ok"
        if max_drift_pct >= CRITICAL_DRIFT_PCT or total_incidents > DRIFT_INCIDENT_THRESHOLD:
            return "critical"
        return "drift"

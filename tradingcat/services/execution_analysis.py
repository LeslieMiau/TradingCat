"""Execution Analysis — quality, TCA, authorization, readiness, period insights.

Replaces OperationsAnalyticsService and consolidates execution analysis
methods into a single service. The underlying ExecutionService still owns
submit/cancel/reconcile/state; this service provides the analysis layer
that routes, facades, and dashboards consume.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from tradingcat.domain.models import AlertEvent, AuditLogEntry, RecoveryAttempt
    from tradingcat.services.alerts import AlertService
    from tradingcat.services.audit import AuditService
    from tradingcat.services.execution import ExecutionService

logger = logging.getLogger(__name__)


class ExecutionAnalysisService:
    """Analysis queries over execution state: quality, TCA, authorization, readiness."""

    def __init__(
        self,
        *,
        execution_getter: Callable[[], "ExecutionService"],
        audit: "AuditService",
        alerts: "AlertService",
    ) -> None:
        self._execution_getter = execution_getter
        self._audit = audit
        self._alerts = alerts

    @property
    def _execution(self) -> "ExecutionService":
        return self._execution_getter()

    # ── Quality / TCA ───────────────────────────────────────────────────────

    def quality_summary(self) -> dict[str, object]:
        return self._execution.execution_quality_summary()

    def tca_summary(self) -> dict[str, object]:
        return self._execution.transaction_cost_summary()

    # ── Authorization ───────────────────────────────────────────────────────

    def authorization_summary(self) -> dict[str, object]:
        return self._execution.authorization_summary()

    def order_state_summary(self) -> dict[str, int]:
        return self._execution.order_state_summary()

    # ── Aggregated metrics (replaces OperationsAnalyticsService.execution_metrics) ──

    def execution_metrics(self) -> dict[str, object]:
        audit_metrics = self._audit.execution_metrics_summary()
        quality = self.quality_summary()
        tca = self.tca_summary()
        auth = self.authorization_summary()
        return {
            **audit_metrics,
            "filled_samples": quality.get("filled_samples", 0),
            "slippage_within_limits": quality.get("within_limits", False),
            "authorization_ok": auth.get("all_authorized", False),
            "unauthorized_count": auth.get("unauthorized_count", 0),
            "execution_quality": quality,
            "execution_tca": tca,
            "authorization": auth,
        }

    def tca_metrics(self) -> dict[str, object]:
        """Lightweight TCA + audit combo (replaces OperationsAnalyticsService.tca_summary)."""
        audit_metrics = self._audit.execution_metrics_summary()
        tca = self.tca_summary()
        return {**audit_metrics, **tca}

    # ── Readiness blockers ─────────────────────────────────────────────────

    def execution_readiness(
        self,
        *,
        state_counts: dict[str, int] | None = None,
        authorization: dict[str, object] | None = None,
        alerts_summary: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Execution readiness check — matches the callable signature used by ReadinessQueryService."""
        state_counts = state_counts or self.order_state_summary()
        authorization = authorization or self.authorization_summary()
        return self._readiness_blockers(state_counts=state_counts, authorization=authorization, alerts_summary=alerts_summary)

    def _readiness_blockers(
        self,
        *,
        state_counts: dict[str, int] | None = None,
        authorization: dict[str, object] | None = None,
        alerts_summary: dict[str, object] | None = None,
    ) -> dict[str, object]:
        """Execution readiness check (replaces OperationsAnalyticsService.execution_readiness)."""
        state_counts = state_counts or self.order_state_summary()
        auth = authorization or self.authorization_summary()

        pending_approval = int(state_counts.get("pending_approval", 0))
        submitted = int(state_counts.get("submitted", 0))
        partially_filled = int(state_counts.get("partially_filled", 0))
        unauthorized = int(auth.get("unauthorized_count", 0))

        blockers: list[str] = []
        if pending_approval:
            blockers.append(f"{pending_approval} order(s) remain pending approval.")
        reconcile_pending = submitted + partially_filled
        if reconcile_pending:
            blockers.append(f"{reconcile_pending} order(s) still need reconciliation before the next execution cycle.")
        if unauthorized:
            blockers.append(f"{unauthorized} order(s) are missing a clean authorization state.")

        if alerts_summary is not None:
            blocker_alerts = self._collect_alert_blockers(alerts_summary)
            blockers.extend(blocker_alerts)

        return {
            "ready": len(blockers) == 0,
            "state_counts": state_counts,
            "pending_approval_count": pending_approval,
            "reconcile_pending_count": reconcile_pending,
            "unauthorized_count": unauthorized,
            "all_authorized": bool(auth.get("all_authorized", False)),
            "blockers": blockers,
        }

    # ── Period insights ────────────────────────────────────────────────────

    def period_insights(
        self,
        *,
        window_days: int,
        alerts: list[AlertEvent],
        audit_events: list[AuditLogEntry],
        recoveries: list[RecoveryAttempt],
    ) -> dict[str, object]:
        """Longer-window analysis of execution quality, anomalies, and risks."""
        tca = self.tca_summary()
        execution_errors = [e for e in audit_events if e.category == "execution" and e.status == "error"]
        risk_violations = [e for e in audit_events if e.category == "risk" and e.action == "violation"]
        recent_samples = self._recent_tca_samples(tca, window_days)
        return {
            "tca_sample_count": len(recent_samples),
            "top_execution_drags": self._top_execution_drags(recent_samples),
            "top_anomaly_sources": self._top_anomaly_sources(alerts, execution_errors, risk_violations, recoveries),
        }

    # ── Internal helpers ───────────────────────────────────────────────────

    @staticmethod
    def _collect_alert_blockers(alerts_summary: dict[str, object]) -> list[str]:
        active = alerts_summary.get("active", []) if isinstance(alerts_summary, dict) else []
        blockers: list[str] = []
        actionable_categories = {
            "cash_mismatch",
            "position_mismatch",
            "unmatched_broker_orders",
            "duplicate_fills_detected",
        }
        for alert in active:
            if isinstance(alert, dict):
                category = alert.get("category")
                message = alert.get("message")
            else:
                category = getattr(alert, "category", None)
                message = getattr(alert, "message", None)
            if category in actionable_categories and message:
                blockers.append(str(message))
        if not blockers:
            count = int(alerts_summary.get("count", 0)) if isinstance(alerts_summary, dict) else 0
            if count > 0:
                blockers.append(f"{count} active alert(s) require review before the next execution cycle.")
        return blockers

    @staticmethod
    def _recent_tca_samples(tca: dict[str, object], window_days: int) -> list[dict[str, object]]:
        samples = tca.get("samples", []) if isinstance(tca, dict) else []
        if not isinstance(samples, list):
            return []
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        recent: list[dict[str, object]] = []
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            ts = sample.get("timestamp")
            if not ts:
                recent.append(sample)
                continue
            try:
                dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            except ValueError:
                recent.append(sample)
                continue
            if dt >= cutoff:
                recent.append(sample)
        return recent

    @staticmethod
    def _top_execution_drags(samples: list[dict[str, object]], limit: int = 3) -> list[dict[str, object]]:
        ranked: list[tuple[float, dict[str, object]]] = []
        for sample in samples:
            try:
                threshold = float(sample.get("threshold") or 0.0)
                deviation = float(sample.get("deviation_value") or 0.0)
            except (TypeError, ValueError):
                continue
            score = deviation / threshold if threshold > 0 else deviation
            ranked.append((score, sample))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [
            {
                "symbol": s.get("symbol"),
                "direction": s.get("direction"),
                "asset_class": s.get("asset_class"),
                "deviation_metric": s.get("deviation_metric"),
                "deviation_value": s.get("deviation_value"),
                "threshold": s.get("threshold"),
                "expected_price": s.get("expected_price"),
                "realized_price": s.get("realized_price"),
                "reference_source": s.get("reference_source"),
                "within_threshold": s.get("within_threshold"),
            }
            for _, s in ranked[:limit]
        ]

    @staticmethod
    def _top_anomaly_sources(
        alerts: list[AlertEvent],
        execution_errors: list[AuditLogEntry],
        risk_violations: list[AuditLogEntry],
        recoveries: list[RecoveryAttempt],
        limit: int = 3,
    ) -> list[dict[str, object]]:
        sources: dict[str, dict[str, object]] = {}

        def bump(key: str, source_type: str, timestamp: datetime) -> None:
            record = sources.setdefault(
                key, {"source": key, "type": source_type, "count": 0, "latest_at": timestamp.isoformat()}
            )
            record["count"] = int(record["count"]) + 1
            record["latest_at"] = max(str(record["latest_at"]), timestamp.isoformat())

        for alert in alerts:
            bump(f"alert:{alert.category}", "alert", alert.created_at)
        for event in execution_errors:
            bump(f"execution:{event.action}", "execution", event.created_at)
        for event in risk_violations:
            bump(f"risk:{event.action}", "risk", event.created_at)
        for attempt in recoveries:
            bump(f"recovery:{attempt.status}", "recovery", attempt.attempted_at)

        ranked = sorted(sources.values(), key=lambda item: (int(item["count"]), str(item["latest_at"])), reverse=True)
        return ranked[:limit]

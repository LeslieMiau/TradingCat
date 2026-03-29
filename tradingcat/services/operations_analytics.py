from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.domain.models import AlertEvent, AuditLogEntry, RecoveryAttempt


class OperationsAnalyticsService:
    def execution_metrics(
        self,
        *,
        audit_metrics: dict[str, object],
        execution_quality: dict[str, object],
        execution_tca: dict[str, object],
        authorization: dict[str, object],
    ) -> dict[str, object]:
        return {
            **audit_metrics,
            "filled_samples": execution_quality["filled_samples"],
            "slippage_within_limits": execution_quality["within_limits"],
            "authorization_ok": authorization["all_authorized"],
            "unauthorized_count": authorization["unauthorized_count"],
            "execution_quality": execution_quality,
            "execution_tca": execution_tca,
            "authorization": authorization,
        }

    def tca_summary(
        self,
        *,
        audit_metrics: dict[str, object],
        execution_tca: dict[str, object],
    ) -> dict[str, object]:
        return {
            **audit_metrics,
            **execution_tca,
        }

    def period_insights(
        self,
        *,
        window_days: int,
        execution_tca: dict[str, object],
        alerts: list[AlertEvent],
        audit_events: list[AuditLogEntry],
        recoveries: list[RecoveryAttempt],
    ) -> dict[str, object]:
        execution_errors = [event for event in audit_events if event.category == "execution" and event.status == "error"]
        risk_violations = [event for event in audit_events if event.category == "risk" and event.action == "violation"]
        recent_tca_samples = self._recent_tca_samples(execution_tca, window_days)
        return {
            "tca_sample_count": len(recent_tca_samples),
            "top_execution_drags": self._top_execution_drags(recent_tca_samples),
            "top_anomaly_sources": self._top_anomaly_sources(alerts, execution_errors, risk_violations, recoveries),
        }

    def _recent_tca_samples(self, execution_tca: dict[str, object], window_days: int) -> list[dict[str, object]]:
        samples = execution_tca.get("samples", []) if isinstance(execution_tca, dict) else []
        if not isinstance(samples, list):
            return []
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        recent: list[dict[str, object]] = []
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            timestamp = sample.get("timestamp")
            if not timestamp:
                recent.append(sample)
                continue
            try:
                sample_dt = datetime.fromisoformat(str(timestamp).replace("Z", "+00:00"))
            except ValueError:
                recent.append(sample)
                continue
            if sample_dt >= cutoff:
                recent.append(sample)
        return recent

    def _top_execution_drags(self, samples: list[dict[str, object]], limit: int = 3) -> list[dict[str, object]]:
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
                "symbol": sample.get("symbol"),
                "direction": sample.get("direction"),
                "asset_class": sample.get("asset_class"),
                "deviation_metric": sample.get("deviation_metric"),
                "deviation_value": sample.get("deviation_value"),
                "threshold": sample.get("threshold"),
                "expected_price": sample.get("expected_price"),
                "realized_price": sample.get("realized_price"),
                "reference_source": sample.get("reference_source"),
                "within_threshold": sample.get("within_threshold"),
            }
            for _, sample in ranked[:limit]
        ]

    def _top_anomaly_sources(
        self,
        alerts: list[AlertEvent],
        execution_errors: list[AuditLogEntry],
        risk_violations: list[AuditLogEntry],
        recoveries: list[RecoveryAttempt],
        limit: int = 3,
    ) -> list[dict[str, object]]:
        sources: dict[str, dict[str, object]] = {}

        def bump(key: str, source_type: str, timestamp: datetime) -> None:
            record = sources.setdefault(key, {"source": key, "type": source_type, "count": 0, "latest_at": timestamp.isoformat()})
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

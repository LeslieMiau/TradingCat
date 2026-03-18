from __future__ import annotations

from tradingcat.domain.models import AlertEvent, PortfolioReconciliationSummary, ReconciliationSummary
from tradingcat.repositories.state import AlertRepository


class AlertService:
    def __init__(self, repository: AlertRepository) -> None:
        self._repository = repository
        self._alerts = repository.load()

    def evaluate(
        self,
        broker_status: dict[str, object],
        broker_validation: dict[str, object],
        market_data_smoke_test: dict[str, object],
        execution_reconciliation: ReconciliationSummary,
        portfolio_reconciliation: PortfolioReconciliationSummary,
    ) -> list[AlertEvent]:
        alerts: list[AlertEvent] = []

        if not bool(broker_status.get("healthy", False)):
            alerts.append(
                self._record(
                    severity="error",
                    category="broker_unhealthy",
                    message=str(broker_status.get("detail", "Broker health check failed")),
                    recovery_action="Check OpenD login state and rerun /broker/validate.",
                    details={"backend": str(broker_status.get("backend", "unknown"))},
                )
            )

        validation_checks = broker_validation.get("checks", {}) if isinstance(broker_validation, dict) else {}
        for channel in ("quote", "trade"):
            channel_payload = validation_checks.get(channel, {}) if isinstance(validation_checks, dict) else {}
            if channel_payload.get("status") == "failed":
                alerts.append(
                    self._record(
                        severity="error",
                        category=f"{channel}_channel_failed",
                        message=str(channel_payload.get("detail", f"{channel} channel failed")),
                        recovery_action=f"Repair the {channel} channel before attempting execution.",
                        details={"channel": channel},
                    )
                )

        failed_symbols = market_data_smoke_test.get("failed_symbols", {}) if isinstance(market_data_smoke_test, dict) else {}
        if failed_symbols:
            alerts.append(
                self._record(
                    severity="warning",
                    category="market_data_partial_failure",
                    message=f"Market data smoke test failed for {len(failed_symbols)} symbol checks.",
                    recovery_action="Review symbol permissions and field mappings, then rerun /market-data/smoke-test.",
                    details={"failed_count": len(failed_symbols)},
                )
            )

        if execution_reconciliation.duplicate_fills > 0:
            alerts.append(
                self._record(
                    severity="warning",
                    category="duplicate_fills_detected",
                    message=f"Detected {execution_reconciliation.duplicate_fills} duplicate broker fills during reconciliation.",
                    recovery_action="Inspect broker deal history and confirm duplicate fills are expected retries, not replay errors.",
                    details={"duplicate_fills": execution_reconciliation.duplicate_fills},
                )
            )

        if execution_reconciliation.unmatched_broker_orders > 0:
            alerts.append(
                self._record(
                    severity="error",
                    category="unmatched_broker_orders",
                    message=f"Found {execution_reconciliation.unmatched_broker_orders} broker orders that are not linked to local state.",
                    recovery_action="Investigate unexpected broker orders before continuing automated execution.",
                    details={"unmatched_broker_orders": execution_reconciliation.unmatched_broker_orders},
                )
            )

        if abs(portfolio_reconciliation.cash_difference) > 1.0:
            alerts.append(
                self._record(
                    severity="warning",
                    category="cash_mismatch",
                    message=f"Broker cash differs from local snapshot by {portfolio_reconciliation.cash_difference:.2f}.",
                    recovery_action="Refresh fills and portfolio state, then verify broker cash manually.",
                    details={"cash_difference": portfolio_reconciliation.cash_difference},
                )
            )

        if portfolio_reconciliation.missing_symbols or portfolio_reconciliation.unexpected_symbols:
            alerts.append(
                self._record(
                    severity="warning",
                    category="position_mismatch",
                    message="Broker positions differ from the local portfolio snapshot.",
                    recovery_action="Run execution reconciliation and compare live positions before next trading cycle.",
                    details={
                        "missing_symbols": len(portfolio_reconciliation.missing_symbols),
                        "unexpected_symbols": len(portfolio_reconciliation.unexpected_symbols),
                    },
                )
            )

        return alerts

    def list_alerts(self) -> list[AlertEvent]:
        return sorted(self._alerts.values(), key=lambda item: item.created_at, reverse=True)

    def latest_summary(self) -> dict[str, object]:
        alerts = self.list_alerts()
        return {
            "count": len(alerts),
            "latest": alerts[0] if alerts else None,
            "active": alerts[:10],
        }

    def clear(self) -> None:
        self._alerts = {}
        self._repository.save(self._alerts)

    def _record(
        self,
        severity: str,
        category: str,
        message: str,
        recovery_action: str,
        details: dict[str, str | int | float | bool],
    ) -> AlertEvent:
        alert = AlertEvent(
            severity=severity,
            category=category,
            message=message,
            recovery_action=recovery_action,
            details=details,
        )
        self._alerts[alert.id] = alert
        self._repository.save(self._alerts)
        return alert

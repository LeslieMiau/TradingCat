from __future__ import annotations

import logging

from tradingcat.domain.models import AlertEvent, PortfolioReconciliationSummary, ReconciliationSummary
from tradingcat.repositories.state import AlertRepository
from tradingcat.services.notifier import AlertDispatcher


logger = logging.getLogger(__name__)


class AlertService:
    def __init__(self, repository: AlertRepository, dispatcher: AlertDispatcher | None = None) -> None:
        self._repository = repository
        self._alerts = repository.load()
        self._dispatcher = dispatcher

    def set_dispatcher(self, dispatcher: AlertDispatcher | None) -> None:
        self._dispatcher = dispatcher

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
                    message=str(broker_status.get("detail", "券商健康检查失败")),
                    recovery_action="检查 OpenD 登录状态，然后重新运行 /broker/validate。",
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
                        message=str(channel_payload.get("detail", f"{channel} 通道失败")),
                        recovery_action=f"先修复 {channel} 通道，再尝试执行。",
                        details={"channel": channel},
                    )
                )

        failed_symbols = market_data_smoke_test.get("failed_symbols", {}) if isinstance(market_data_smoke_test, dict) else {}
        if failed_symbols:
            alerts.append(
                self._record(
                    severity="warning",
                    category="market_data_partial_failure",
                    message=f"市场数据冒烟测试在 {len(failed_symbols)} 个标的检查上失败。",
                    recovery_action="检查标的权限和字段映射，然后重新运行 /market-data/smoke-test。",
                    details={"failed_count": len(failed_symbols)},
                )
            )

        if execution_reconciliation.duplicate_fills > 0:
            alerts.append(
                self._record(
                    severity="warning",
                    category="duplicate_fills_detected",
                    message=f"对账过程中检测到 {execution_reconciliation.duplicate_fills} 笔重复券商成交。",
                    recovery_action="检查券商成交历史，确认重复成交是预期重试而不是回放错误。",
                    details={"duplicate_fills": execution_reconciliation.duplicate_fills},
                )
            )

        if execution_reconciliation.unmatched_broker_orders > 0:
            alerts.append(
                self._record(
                    severity="error",
                    category="unmatched_broker_orders",
                    message=f"发现 {execution_reconciliation.unmatched_broker_orders} 笔券商订单未关联到本地状态。",
                    recovery_action="在继续自动执行前，先排查这些意外券商订单。",
                    details={"unmatched_broker_orders": execution_reconciliation.unmatched_broker_orders},
                )
            )

        if abs(portfolio_reconciliation.cash_difference) > 1.0:
            alerts.append(
                self._record(
                    severity="warning",
                    category="cash_mismatch",
                    message=f"券商现金与本地快照相差 {portfolio_reconciliation.cash_difference:.2f}。",
                    recovery_action="刷新成交和组合状态，然后人工核对券商现金。",
                    details={"cash_difference": portfolio_reconciliation.cash_difference},
                )
            )

        if portfolio_reconciliation.missing_symbols or portfolio_reconciliation.unexpected_symbols:
            alerts.append(
                self._record(
                    severity="warning",
                    category="position_mismatch",
                    message="券商持仓与本地组合快照不一致。",
                    recovery_action="在下一次交易周期前运行执行对账，并比较实时持仓。",
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

    def record(
        self,
        *,
        severity: str,
        category: str,
        message: str,
        recovery_action: str = "",
        details: dict[str, str | int | float | bool] | None = None,
    ) -> AlertEvent:
        return self._record(
            severity=severity,
            category=category,
            message=message,
            recovery_action=recovery_action,
            details=details or {},
        )

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
        if self._dispatcher is not None:
            try:
                self._dispatcher.dispatch(alert)
            except Exception:
                logger.exception("Alert dispatcher failed for category=%s", alert.category)
        return alert

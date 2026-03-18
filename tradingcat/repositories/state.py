from __future__ import annotations

from pathlib import Path

from tradingcat.config import AppConfig
from tradingcat.domain.models import AlertEvent, ApprovalRequest, AuditLogEntry, ComplianceChecklist, DailyTradingPlanNote, DailyTradingSummaryNote, ExecutionReport, HistorySyncRun, KillSwitchEvent, OperationsJournalEntry, PortfolioSnapshot, RecoveryAttempt, RolloutPolicy, RolloutPromotionAttempt, StrategyAllocationRecord, StrategySelectionRecord
from tradingcat.repositories.json_store import JsonStore
from tradingcat.repositories.postgres_store import PostgresStore


def _build_store(config_or_data_dir: AppConfig | Path, bucket: str):
    if isinstance(config_or_data_dir, AppConfig):
        if config_or_data_dir.postgres.enabled:
            return PostgresStore(config_or_data_dir.postgres.dsn), bucket
        return JsonStore(config_or_data_dir.data_dir / f"{bucket}.json"), None
    return JsonStore(config_or_data_dir / f"{bucket}.json"), None


class ApprovalRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "approvals")

    def load(self) -> dict[str, ApprovalRequest]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: ApprovalRequest.model_validate(record) for record in records}

    def save(self, approvals: dict[str, ApprovalRequest]) -> None:
        payload = [approval.model_dump(mode="json") for approval in approvals.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class OrderRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "orders")

    def load(self) -> dict[str, ExecutionReport]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["order_intent_id"]: ExecutionReport.model_validate(record) for record in records}

    def save(self, orders: dict[str, ExecutionReport]) -> None:
        payload = [order.model_dump(mode="json") for order in orders.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class PortfolioRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "portfolio")

    def load(self) -> PortfolioSnapshot | None:
        record = self._store.load(self._bucket, None) if self._bucket else self._store.load(None)
        if not record:
            return None
        return PortfolioSnapshot.model_validate(record)

    def save(self, snapshot: PortfolioSnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class PortfolioHistoryRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "portfolio_history")

    def load(self) -> dict[str, PortfolioSnapshot]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["timestamp"]: PortfolioSnapshot.model_validate(record) for record in records}

    def save(self, history: dict[str, PortfolioSnapshot]) -> None:
        payload = [snapshot.model_dump(mode="json") for snapshot in history.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class ExecutionStateRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "execution_state")

    def load(self) -> dict[str, object]:
        return self._store.load(self._bucket, {"fill_fingerprints": []}) if self._bucket else self._store.load({"fill_fingerprints": []})

    def save(self, state: dict[str, object]) -> None:
        if self._bucket:
            self._store.save(self._bucket, state)
        else:
            self._store.save(state)


class AlertRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "alerts")

    def load(self) -> dict[str, AlertEvent]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: AlertEvent.model_validate(record) for record in records}

    def save(self, alerts: dict[str, AlertEvent]) -> None:
        payload = [alert.model_dump(mode="json") for alert in alerts.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class ComplianceRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "compliance")

    def load(self) -> dict[str, ComplianceChecklist]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["checklist_id"]: ComplianceChecklist.model_validate(record) for record in records}

    def save(self, checklists: dict[str, ComplianceChecklist]) -> None:
        payload = [checklist.model_dump(mode="json") for checklist in checklists.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class OperationsJournalRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "operations_journal")

    def load(self) -> dict[str, OperationsJournalEntry]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: OperationsJournalEntry.model_validate(record) for record in records}

    def save(self, entries: dict[str, OperationsJournalEntry]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class DailyTradingPlanRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "daily_trading_plans")

    def load(self) -> dict[str, DailyTradingPlanNote]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: DailyTradingPlanNote.model_validate(record) for record in records}

    def save(self, entries: dict[str, DailyTradingPlanNote]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class DailyTradingSummaryRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "daily_trading_summaries")

    def load(self) -> dict[str, DailyTradingSummaryNote]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: DailyTradingSummaryNote.model_validate(record) for record in records}

    def save(self, entries: dict[str, DailyTradingSummaryNote]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class RecoveryAttemptRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "recovery_attempts")

    def load(self) -> dict[str, RecoveryAttempt]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: RecoveryAttempt.model_validate(record) for record in records}

    def save(self, entries: dict[str, RecoveryAttempt]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class StrategySelectionRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "strategy_selections")

    def load(self) -> dict[str, StrategySelectionRecord]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["strategy_id"]: StrategySelectionRecord.model_validate(record) for record in records}

    def save(self, entries: dict[str, StrategySelectionRecord]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class StrategyAllocationRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "strategy_allocations")

    def load(self) -> dict[str, StrategyAllocationRecord]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["strategy_id"]: StrategyAllocationRecord.model_validate(record) for record in records}

    def save(self, entries: dict[str, StrategyAllocationRecord]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class HistorySyncRunRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "history_sync_runs")

    def load(self) -> dict[str, HistorySyncRun]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: HistorySyncRun.model_validate(record) for record in records}

    def save(self, entries: dict[str, HistorySyncRun]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class RolloutPolicyRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "rollout_policy")

    def load(self) -> RolloutPolicy | None:
        record = self._store.load(self._bucket, None) if self._bucket else self._store.load(None)
        if not record:
            return None
        return RolloutPolicy.model_validate(record)

    def save(self, policy: RolloutPolicy) -> None:
        payload = policy.model_dump(mode="json")
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class RolloutPromotionRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "rollout_promotions")

    def load(self) -> dict[str, RolloutPromotionAttempt]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: RolloutPromotionAttempt.model_validate(record) for record in records}

    def save(self, entries: dict[str, RolloutPromotionAttempt]) -> None:
        payload = [entry.model_dump(mode="json") for entry in entries.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class KillSwitchRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "kill_switch_events")

    def load(self) -> dict[str, KillSwitchEvent]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
        return {record["id"]: KillSwitchEvent.model_validate(record) for record in records}

    def save(self, events: dict[str, KillSwitchEvent]) -> None:
        payload = [event.model_dump(mode="json") for event in events.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)


class AuditLogRepository:
    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "audit_events")
        self._path = None if isinstance(config_or_data_dir, AppConfig) else Path(config_or_data_dir) / "audit_events.json"
        if isinstance(config_or_data_dir, AppConfig) and not config_or_data_dir.postgres.enabled:
            self._path = config_or_data_dir.data_dir / "audit_events.json"

    def load(self) -> dict[str, AuditLogEntry]:
        if self._bucket:
            records = self._store.load(self._bucket, [])
        else:
            records = self._store.load([])
        return {record["id"]: AuditLogEntry.model_validate(record) for record in records}

    def save(self, events: dict[str, AuditLogEntry]) -> None:
        payload = [event.model_dump(mode="json") for event in events.values()]
        if self._bucket:
            self._store.save(self._bucket, payload)
        else:
            self._store.save(payload)

    def append(self, event: AuditLogEntry) -> None:
        if self._bucket and hasattr(self._store, "append_audit"):
            self._store.append_audit("audit_events", event.action, event.model_dump(mode="json"))
        events = self.load()
        events[event.id] = event
        self.save(events)

"""Repository classes for domain model persistence.

All dict-based repositories share the same pattern via ``_DictRepository``.
Named classes are kept as thin aliases so that existing imports and type
annotations remain unchanged.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    AcceptanceGateSnapshot,
    AlertEvent,
    ApprovalRequest,
    AuditLogEntry,
    ComplianceChecklist,
    DailyTradingPlanNote,
    DailyTradingSummaryNote,
    ExecutionReport,
    HistoryAuditRun,
    HistorySyncRun,
    KillSwitchEvent,
    OperationsJournalEntry,
    PortfolioSnapshot,
    RecoveryAttempt,
    RolloutPolicy,
    RolloutPromotionAttempt,
    StrategyAllocationRecord,
    StrategySelectionRecord,
)
from tradingcat.repositories.json_store import JsonStore
from tradingcat.repositories.postgres_store import PostgresStore


# ---------------------------------------------------------------------------
# Store factory
# ---------------------------------------------------------------------------

def _build_store(config_or_data_dir: AppConfig | Path, bucket: str):
    if isinstance(config_or_data_dir, AppConfig):
        if config_or_data_dir.postgres.enabled:
            return PostgresStore(config_or_data_dir.postgres.dsn), bucket
        return JsonStore(config_or_data_dir.data_dir / f"{bucket}.json"), None
    return JsonStore(config_or_data_dir / f"{bucket}.json"), None


# ---------------------------------------------------------------------------
# Generic base: dict[key, Model]
# ---------------------------------------------------------------------------

T = TypeVar("T", bound=BaseModel)


class _DictRepository(Generic[T]):
    """Generic repository that stores ``dict[str, T]`` as a JSON list."""

    _bucket_name: str
    _model_class: type[T]
    _key_field: str  # which field on the model to use as the dict key

    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._pg_bucket = _build_store(config_or_data_dir, self._bucket_name)

    def load(self) -> dict[str, T]:
        records = self._store.load(self._pg_bucket, []) if self._pg_bucket else self._store.load([])
        return {record[self._key_field]: self._model_class.model_validate(record) for record in records}

    def save(self, items: dict[str, T]) -> None:
        payload = [item.model_dump(mode="json") for item in items.values()]
        if self._pg_bucket:
            self._store.save(self._pg_bucket, payload)
        else:
            self._store.save(payload)


# ---------------------------------------------------------------------------
# Generic base: single Model | None
# ---------------------------------------------------------------------------

class _SingletonRepository(Generic[T]):
    """Repository that stores a single model instance (or None)."""

    _bucket_name: str
    _model_class: type[T]

    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._pg_bucket = _build_store(config_or_data_dir, self._bucket_name)

    def load(self) -> T | None:
        record = self._store.load(self._pg_bucket, None) if self._pg_bucket else self._store.load(None)
        if not record:
            return None
        return self._model_class.model_validate(record)

    def save(self, item: T) -> None:
        payload = item.model_dump(mode="json")
        if self._pg_bucket:
            self._store.save(self._pg_bucket, payload)
        else:
            self._store.save(payload)


# ---------------------------------------------------------------------------
# Concrete repositories — one-liner declarations
# ---------------------------------------------------------------------------

class ApprovalRepository(_DictRepository[ApprovalRequest]):
    _bucket_name = "approvals"
    _model_class = ApprovalRequest
    _key_field = "id"


class OrderRepository(_DictRepository[ExecutionReport]):
    _bucket_name = "orders"
    _model_class = ExecutionReport
    _key_field = "order_intent_id"


class AlertRepository(_DictRepository[AlertEvent]):
    _bucket_name = "alerts"
    _model_class = AlertEvent
    _key_field = "id"


class ComplianceRepository(_DictRepository[ComplianceChecklist]):
    _bucket_name = "compliance"
    _model_class = ComplianceChecklist
    _key_field = "checklist_id"


class OperationsJournalRepository(_DictRepository[OperationsJournalEntry]):
    _bucket_name = "operations_journal"
    _model_class = OperationsJournalEntry
    _key_field = "id"


class DailyTradingPlanRepository(_DictRepository[DailyTradingPlanNote]):
    _bucket_name = "daily_trading_plans"
    _model_class = DailyTradingPlanNote
    _key_field = "id"


class DailyTradingSummaryRepository(_DictRepository[DailyTradingSummaryNote]):
    _bucket_name = "daily_trading_summaries"
    _model_class = DailyTradingSummaryNote
    _key_field = "id"


class RecoveryAttemptRepository(_DictRepository[RecoveryAttempt]):
    _bucket_name = "recovery_attempts"
    _model_class = RecoveryAttempt
    _key_field = "id"


class StrategySelectionRepository(_DictRepository[StrategySelectionRecord]):
    _bucket_name = "strategy_selections"
    _model_class = StrategySelectionRecord
    _key_field = "strategy_id"


class StrategyAllocationRepository(_DictRepository[StrategyAllocationRecord]):
    _bucket_name = "strategy_allocations"
    _model_class = StrategyAllocationRecord
    _key_field = "strategy_id"


class HistorySyncRunRepository(_DictRepository[HistorySyncRun]):
    _bucket_name = "history_sync_runs"
    _model_class = HistorySyncRun
    _key_field = "id"


class RolloutPromotionRepository(_DictRepository[RolloutPromotionAttempt]):
    _bucket_name = "rollout_promotions"
    _model_class = RolloutPromotionAttempt
    _key_field = "id"


class KillSwitchRepository(_DictRepository[KillSwitchEvent]):
    _bucket_name = "kill_switch_events"
    _model_class = KillSwitchEvent
    _key_field = "id"


class AcceptanceGateSnapshotRepository(_DictRepository[AcceptanceGateSnapshot]):
    _bucket_name = "acceptance_gate_snapshots"
    _model_class = AcceptanceGateSnapshot
    _key_field = "as_of"


class HistoryAuditRunRepository(_DictRepository[HistoryAuditRun]):
    _bucket_name = "history_audit_runs"
    _model_class = HistoryAuditRun
    _key_field = "as_of"


class PortfolioHistoryRepository(_DictRepository[PortfolioSnapshot]):
    _bucket_name = "portfolio_history"
    _model_class = PortfolioSnapshot
    _key_field = "timestamp"


# ---------------------------------------------------------------------------
# Singleton repositories
# ---------------------------------------------------------------------------

class PortfolioRepository(_SingletonRepository[PortfolioSnapshot]):
    _bucket_name = "portfolio"
    _model_class = PortfolioSnapshot


class RolloutPolicyRepository(_SingletonRepository[RolloutPolicy]):
    _bucket_name = "rollout_policy"
    _model_class = RolloutPolicy


# ---------------------------------------------------------------------------
# Special repositories
# ---------------------------------------------------------------------------

class ExecutionStateRepository:
    """Stores raw execution state (fingerprints, expected prices, etc.)."""

    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "execution_state")

    def load(self) -> dict[str, object]:
        return self._store.load(self._bucket, {"fill_fingerprints": []}) if self._bucket else self._store.load({"fill_fingerprints": []})

    def save(self, state: dict[str, object]) -> None:
        if self._bucket:
            self._store.save(self._bucket, state)
        else:
            self._store.save(state)


class AuditLogRepository:
    """Stores audit log entries with an ``append`` shortcut."""

    def __init__(self, config_or_data_dir: AppConfig | Path) -> None:
        self._store, self._bucket = _build_store(config_or_data_dir, "audit_events")
        self._path = None if isinstance(config_or_data_dir, AppConfig) else Path(config_or_data_dir) / "audit_events.json"
        if isinstance(config_or_data_dir, AppConfig) and not config_or_data_dir.postgres.enabled:
            self._path = config_or_data_dir.data_dir / "audit_events.json"

    def load(self) -> dict[str, AuditLogEntry]:
        records = self._store.load(self._bucket, []) if self._bucket else self._store.load([])
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

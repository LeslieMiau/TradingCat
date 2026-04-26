"""Facade for Insight persistence with graceful degradation.

When DuckDB is enabled in `AppConfig.duckdb`, delegates to
`DuckDbInsightStore`. Otherwise keeps insights in an in-memory dict — this
keeps the engine fully functional in unit tests and on machines without
the optional persistence backend.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from threading import RLock

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    Insight,
    InsightKind,
    InsightUserAction,
)


logger = logging.getLogger(__name__)


class InsightStore:
    def __init__(self, config: AppConfig) -> None:
        self._duckdb_store = None
        self._memory: dict[str, Insight] = {}
        self._memory_lock = RLock()
        if config.duckdb.enabled:
            try:
                from tradingcat.repositories.duckdb_insight_store import (
                    DuckDbInsightStore,
                )

                self._duckdb_store = DuckDbInsightStore(db_path=config.duckdb.path)
                logger.info("insight store: DuckDB initialized at %s", config.duckdb.path)
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: DuckDB unavailable (%s); using memory store", exc)

    @property
    def backend(self) -> str:
        return "duckdb" if self._duckdb_store else "memory"

    def upsert(self, insight: Insight) -> None:
        if self._duckdb_store is not None:
            try:
                self._duckdb_store.upsert(insight)
                return
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: duckdb upsert failed (%s); falling back to memory", exc)
        with self._memory_lock:
            self._memory[insight.id] = insight

    def list(
        self,
        *,
        include_dismissed: bool = False,
        kinds: list[InsightKind] | None = None,
        now: datetime | None = None,
    ) -> list[Insight]:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.list(
                    include_dismissed=include_dismissed,
                    kinds=kinds,
                    now=now,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: duckdb list failed (%s); using memory", exc)
        return self._list_memory(include_dismissed=include_dismissed, kinds=kinds, now=now)

    def get(self, insight_id: str) -> Insight | None:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.get(insight_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: duckdb get failed (%s); using memory", exc)
        with self._memory_lock:
            return self._memory.get(insight_id)

    def update_user_action(
        self,
        insight_id: str,
        action: InsightUserAction,
        *,
        reason: str | None = None,
    ) -> bool:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.update_user_action(
                    insight_id, action, reason=reason
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: duckdb update failed (%s); using memory", exc)
        with self._memory_lock:
            existing = self._memory.get(insight_id)
            if existing is None:
                return False
            self._memory[insight_id] = existing.model_copy(
                update={"user_action": action, "dismissed_reason": reason}
            )
            return True

    def expire_stale(self, *, now: datetime | None = None) -> int:
        if self._duckdb_store is not None:
            try:
                return self._duckdb_store.expire_stale(now=now)
            except Exception as exc:  # noqa: BLE001
                logger.warning("insight store: duckdb expire failed (%s); using memory", exc)
        cutoff = now or datetime.now(timezone.utc)
        with self._memory_lock:
            stale_ids = [
                insight_id
                for insight_id, insight in self._memory.items()
                if insight.expires_at <= cutoff
                and insight.user_action == InsightUserAction.PENDING
            ]
            for insight_id in stale_ids:
                self._memory.pop(insight_id, None)
            return len(stale_ids)

    def _list_memory(
        self,
        *,
        include_dismissed: bool,
        kinds: list[InsightKind] | None,
        now: datetime | None,
    ) -> list[Insight]:
        cutoff = now or datetime.now(timezone.utc)
        severity_order = {"urgent": 0, "notable": 1, "info": 2}
        with self._memory_lock:
            items = list(self._memory.values())
        filtered = [
            insight
            for insight in items
            if insight.expires_at > cutoff
            and (include_dismissed or insight.user_action != InsightUserAction.DISMISSED)
            and (not kinds or insight.kind in kinds)
        ]
        filtered.sort(
            key=lambda insight: (
                severity_order.get(insight.severity.value, 99),
                -insight.triggered_at.timestamp(),
            )
        )
        return filtered

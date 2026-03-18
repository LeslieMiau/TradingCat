from __future__ import annotations

from tradingcat.domain.models import AuditLogEntry
from tradingcat.repositories.state import AuditLogRepository


class AuditService:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository
        self._events = repository.load()

    def log(
        self,
        *,
        category: str,
        action: str,
        status: str = "ok",
        details: dict[str, object] | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            category=category,
            action=action,
            status=status,
            details=details or {},
        )
        self._events[entry.id] = entry
        self._repository.append(entry)
        return entry

    def list_events(self, category: str | None = None, limit: int = 100) -> list[AuditLogEntry]:
        events = sorted(self._events.values(), key=lambda item: item.created_at, reverse=True)
        if category is not None:
            events = [event for event in events if event.category == category]
        return events[:limit]

    def summary(self) -> dict[str, object]:
        events = self.list_events(limit=500)
        return {
            "count": len(events),
            "error_count": sum(1 for event in events if event.status == "error"),
            "warning_count": sum(1 for event in events if event.status == "warning"),
            "latest": events[0] if events else None,
            "categories": sorted({event.category for event in events}),
        }

    def execution_metrics_summary(self) -> dict[str, object]:
        events = self.list_events(limit=1000)
        execution_events = [event for event in events if event.category == "execution"]
        cycle_events = [
            event
            for event in execution_events
            if event.action in {"preview_ok", "preview_error", "run_ok", "run_error", "run_partial"}
        ]
        risk_events = [event for event in events if event.category == "risk" and event.action == "violation"]
        total_cycles = len(cycle_events) + len(risk_events)
        exception_events = sum(1 for event in cycle_events if event.status == "error")
        return {
            "cycle_count": total_cycles,
            "execution_cycle_count": len(cycle_events),
            "risk_hit_count": len(risk_events),
            "exception_count": exception_events,
            "exception_rate": round(exception_events / total_cycles, 4) if total_cycles else 0.0,
            "risk_hit_rate": round(len(risk_events) / total_cycles, 4) if total_cycles else 0.0,
            "latest_execution_event": cycle_events[0] if cycle_events else None,
            "latest_risk_event": risk_events[0] if risk_events else None,
        }

    def clear(self) -> None:
        self._events = {}
        self._repository.save(self._events)

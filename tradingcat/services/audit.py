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

    def build_order_details(
        self,
        *,
        order_intent_id: str,
        broker_order_id: str | None = None,
        order_status: str | None = None,
        previous_order_status: str | None = None,
        authorization_context: dict[str, object] | None = None,
        reconciliation_source: str | None = None,
        extra: dict[str, object] | None = None,
    ) -> dict[str, object]:
        details: dict[str, object] = {"order_intent_id": order_intent_id}
        if broker_order_id:
            details["broker_order_id"] = broker_order_id
        if order_status:
            details["order_status"] = order_status
        if previous_order_status:
            details["previous_order_status"] = previous_order_status
        if reconciliation_source:
            details["reconciliation_source"] = reconciliation_source
        for key, value in (authorization_context or {}).items():
            if value is not None:
                details[key] = value
        if extra:
            details.update(extra)
        return details

    def list_events(
        self,
        category: str | None = None,
        limit: int = 100,
        order_intent_id: str | None = None,
    ) -> list[AuditLogEntry]:
        events = sorted(self._events.values(), key=lambda item: item.created_at, reverse=True)
        if category is not None:
            events = [event for event in events if event.category == category]
        if order_intent_id is not None:
            events = [event for event in events if event.details.get("order_intent_id") == order_intent_id]
        return events[:limit]

    def summary(self) -> dict[str, object]:
        events = self.list_events(limit=500)
        order_activity = self.order_activity_summary(limit=20)
        return {
            "count": len(events),
            "error_count": sum(1 for event in events if event.status == "error"),
            "warning_count": sum(1 for event in events if event.status == "warning"),
            "latest": events[0] if events else None,
            "categories": sorted({event.category for event in events}),
            "tracked_order_count": order_activity["order_count"],
            "order_transition_count": order_activity["transition_count"],
            "orders": order_activity["orders"],
        }

    def order_activity_summary(self, limit: int = 20) -> dict[str, object]:
        grouped: dict[str, dict[str, object]] = {}
        transition_count = 0
        events = sorted(self._events.values(), key=lambda item: item.created_at)
        for event in events:
            order_intent_id = event.details.get("order_intent_id")
            if not isinstance(order_intent_id, str) or not order_intent_id:
                continue
            item = grouped.setdefault(
                order_intent_id,
                {
                    "order_intent_id": order_intent_id,
                    "broker_order_id": None,
                    "authorization_mode": None,
                    "final_authorization_mode": None,
                    "approval_request_id": None,
                    "approval_status": None,
                    "external_source": None,
                    "reconciliation_sources": [],
                    "status_transitions": [],
                    "event_count": 0,
                    "latest_action": None,
                    "latest_event_at": None,
                },
            )
            item["event_count"] = int(item["event_count"]) + 1
            item["latest_action"] = event.action
            item["latest_event_at"] = event.created_at
            for key in (
                "broker_order_id",
                "authorization_mode",
                "final_authorization_mode",
                "approval_request_id",
                "approval_status",
                "external_source",
            ):
                value = event.details.get(key)
                if value not in (None, ""):
                    item[key] = value

            reconciliation_source = event.details.get("reconciliation_source")
            if isinstance(reconciliation_source, str) and reconciliation_source and reconciliation_source not in item["reconciliation_sources"]:
                item["reconciliation_sources"].append(reconciliation_source)

            previous_status = event.details.get("previous_order_status")
            current_status = event.details.get("order_status")
            if previous_status is not None or current_status is not None:
                transition_count += 1
                item["status_transitions"].append(
                    {
                        "action": event.action,
                        "from_status": previous_status,
                        "to_status": current_status,
                        "created_at": event.created_at,
                        "reconciliation_source": reconciliation_source,
                    }
                )

        orders = sorted(
            grouped.values(),
            key=lambda item: item["latest_event_at"] or 0,
            reverse=True,
        )
        return {
            "order_count": len(grouped),
            "transition_count": transition_count,
            "orders": orders[:limit],
        }

    def execution_metrics_summary(self) -> dict[str, object]:
        events = self.list_events(limit=1000)
        execution_events = [event for event in events if event.category == "execution"]
        cycle_events = [
            event
            for event in execution_events
            if event.action in {"preview_ok", "preview_error", "run_ok", "run_error", "run_partial", "fill_ok"}
        ]
        risk_events = [event for event in events if event.category == "risk" and event.action == "violation"]
        total_cycles = len(cycle_events) + len(risk_events)
        exception_events = sum(1 for event in cycle_events if event.status == "error")
        
        # TCA Metrics
        fills = [e for e in execution_events if e.action == "fill_ok"]
        total_slippage = 0.0
        total_latency = 0.0
        slippage_count = 0
        sentiment_impact: dict[str, float] = {}

        for fill in fills:
            details = fill.details
            slip = details.get("slippage_bps")
            lat = details.get("latency_sec")
            emo = details.get("emotional_tag")
            
            if isinstance(slip, (int, float)):
                total_slippage += slip
                slippage_count += 1
                if emo:
                    sentiment_impact[str(emo)] = sentiment_impact.get(str(emo), 0.0) + slip
            
            if isinstance(lat, (int, float)):
                total_latency += lat

        avg_slippage = total_slippage / slippage_count if slippage_count else 0.0
        avg_latency = total_latency / len(fills) if fills else 0.0

        return {
            "cycle_count": total_cycles,
            "execution_cycle_count": len(cycle_events),
            "risk_hit_count": len(risk_events),
            "exception_count": exception_events,
            "exception_rate": round(exception_events / total_cycles, 4) if total_cycles else 0.0,
            "risk_hit_rate": round(len(risk_events) / total_cycles, 4) if total_cycles else 0.0,
            "avg_slippage_bps": round(avg_slippage, 2),
            "avg_latency_sec": round(avg_latency, 3),
            "sentiment_impact": {k: round(v, 2) for k, v in sentiment_impact.items()},
            "latest_execution_event": cycle_events[0] if cycle_events else None,
            "latest_risk_event": risk_events[0] if risk_events else None,
        }

    def clear(self) -> None:
        self._events = {}
        self._repository.save(self._events)

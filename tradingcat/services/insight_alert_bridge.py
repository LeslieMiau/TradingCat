"""Bridge urgent insights to the AlertService so the operator sees them
in the existing alerts UI without having to open the insights tab.

Subscribes to ``EventType.INSIGHT`` on the shared EventBus. For each
event, it looks the full insight up in the store; if severity is
``URGENT``, it records an alert with category ``insight_urgent`` and
embeds enough context (kind, headline, subjects, confidence) for the
operator to triage. Non-urgent insights are silently ignored — the
dashboard feed is the right surface for them.

Failure mode: any exception during processing is logged and swallowed;
EventBus.publish never raises into producers.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from tradingcat.domain.models import InsightSeverity
from tradingcat.services.realtime import Event, EventBus, EventType


logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.alerts import AlertService


class InsightAlertBridge:
    def __init__(
        self,
        *,
        event_bus: EventBus,
        insight_store: "InsightStore",
        alerts: "AlertService",
    ) -> None:
        self._bus = event_bus
        self._store = insight_store
        self._alerts = alerts
        self._bus.subscribe(EventType.INSIGHT, self._on_insight)

    def _on_insight(self, event: Event) -> None:
        try:
            insight_id = event.data.get("insight_id")
            severity = event.data.get("severity")
            if not insight_id or severity != InsightSeverity.URGENT.value:
                return
            insight = self._store.get(insight_id)
            if insight is None:
                return
            self._alerts.record(
                severity="warning",
                category="insight_urgent",
                message=insight.headline,
                recovery_action="打开 /dashboard/insights 查看证据链;确认后点击已读或否决。",
                details={
                    "insight_id": insight.id,
                    "kind": insight.kind.value,
                    "subjects": ",".join(insight.subjects[:5]),
                    "confidence": float(insight.confidence),
                },
            )
        except Exception as exc:  # noqa: BLE001 — bridge must never raise into bus
            logger.warning("insight_alert_bridge: failed to record alert: %s", exc)

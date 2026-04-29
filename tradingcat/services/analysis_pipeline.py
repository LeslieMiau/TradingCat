"""Analysis Pipeline — orchestrates insight detection → alert emission.

Replaces the implicit EventBus INSIGHT→alert path (InsightAlertBridge)
with an explicit call chain. The underlying InsightEngine still runs
detectors and publishes INSIGHT events for other potential consumers,
but the alert path is now a direct, synchronous call.
"""
from __future__ import annotations

import logging
from datetime import date, datetime
from typing import TYPE_CHECKING

from tradingcat.domain.models import InsightSeverity

if TYPE_CHECKING:
    from tradingcat.services.alerts import AlertService
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.repositories.insight_store import InsightStore


logger = logging.getLogger(__name__)


class AnalysisPipelineService:
    """Orchestrates insight detection → classification → persistence → alerting.

    Delegates detector orchestration to InsightEngine, then explicitly
    routes URGENT insights to AlertService — no EventBus subscription needed.
    """

    def __init__(
        self,
        *,
        insight_engine: InsightEngine,
        alert_service: AlertService,
    ) -> None:
        self._engine = insight_engine
        self._alerts = alert_service

    # ── Public API ──────────────────────────────────────────────────────────

    def run(
        self,
        *,
        as_of: date | None = None,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> object:
        """Full pipeline: detect → record → emit alerts for URGENT insights.

        Returns the InsightEngineRunResult (produced insight IDs, counts).
        """
        result = self._engine.run(as_of=as_of, now=now, dry_run=dry_run)
        if not dry_run:
            for insight_id in result.produced:
                self._emit_alert_if_urgent(insight_id)
        return result

    def run_detectors(
        self,
        *,
        as_of: date | None = None,
        now: datetime | None = None,
        dry_run: bool = False,
    ) -> object:
        """Run detectors only (no alert emission). Compat alias."""
        return self._engine.run(as_of=as_of, now=now, dry_run=dry_run)

    def classify_severity(self, insight: object) -> InsightSeverity:
        """Review or override severity classification.

        Currently a pass-through — detectors already set severity.
        Override this method later for cross-detector re-classification.
        """
        return getattr(insight, "severity", InsightSeverity.NOTABLE)

    def record_insight(self, insight: object) -> None:
        """Persist a single insight to the store."""
        self._engine.store.upsert(insight)

    def emit_alert_if_actionable(self, insight_id: str) -> bool:
        """If the insight is URGENT, record an alert. Returns True if alerted."""
        insight = self._engine.store.get(insight_id)
        if insight is None:
            return False
        severity = self.classify_severity(insight)
        if severity != InsightSeverity.URGENT:
            return False
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
        return True

    # ── Internal ────────────────────────────────────────────────────────────

    def _emit_alert_if_urgent(self, insight_id: str) -> None:
        try:
            self.emit_alert_if_actionable(insight_id)
        except Exception as exc:
            logger.warning("analysis_pipeline: alert emission failed for %s: %s", insight_id, exc)

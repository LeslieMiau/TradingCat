from __future__ import annotations

from datetime import date, datetime, UTC, timedelta

from tradingcat.domain.models import OperationsJournalEntry, RecoveryAttempt
from tradingcat.repositories.state import OperationsJournalRepository, RecoveryAttemptRepository


class OperationsJournalService:
    def __init__(self, repository: OperationsJournalRepository) -> None:
        self._repository = repository
        self._entries: dict[str, OperationsJournalEntry] = repository.load()

    def record(self, readiness: dict[str, object]) -> OperationsJournalEntry:
        diagnostics = readiness.get("diagnostics", {}) if isinstance(readiness, dict) else {}
        preflight = readiness.get("preflight", {}) if isinstance(readiness, dict) else {}
        alerts = readiness.get("alerts", {}) if isinstance(readiness, dict) else {}
        compliance = readiness.get("compliance", {}) if isinstance(readiness, dict) else {}

        category = str(diagnostics.get("category", "ok")) if isinstance(diagnostics, dict) else "ok"
        severity = str(diagnostics.get("severity", "ok")) if isinstance(diagnostics, dict) else "ok"
        alert_count = int(alerts.get("count", 0)) if isinstance(alerts, dict) else 0
        checklist_pending = self._compliance_count(compliance, "pending")
        checklist_blocked = self._compliance_count(compliance, "blocked")
        ready = severity in {"ok", "info"} and alert_count == 0 and checklist_blocked == 0

        checks = preflight.get("checks", []) if isinstance(preflight, dict) else []
        all_ok = all(bool(c.get("ok", True)) for c in checks if isinstance(c, dict))
        if not all_ok:
            ready = False

        entry = OperationsJournalEntry(
            ready=ready,
            diagnostics_category=category,
            diagnostics_severity=severity,
            alert_count=alert_count,
            checklist_pending=checklist_pending,
            checklist_blocked=checklist_blocked,
            latest_report_dir=str(readiness.get("latest_report_dir")) if readiness.get("latest_report_dir") else None,
            notes={"readiness": readiness},
        )
        self._entries[entry.id] = entry
        self._repository.save(self._entries)
        return entry

    def list_entries(self) -> list[OperationsJournalEntry]:
        return sorted(self._entries.values(), key=lambda e: e.recorded_at, reverse=True)

    def summary(self) -> dict[str, object]:
        entries = self.list_entries()
        if not entries:
            return {
                "count": 0,
                "ready_count": 0,
                "latest": None,
                "ready_ratio": 0.0,
                "average_alert_count": 0.0,
            }
        return {
            "count": len(entries),
            "ready_count": sum(1 for e in entries if e.ready),
            "latest": entries[0],
            "ready_ratio": round(sum(1 for e in entries if e.ready) / len(entries), 4),
            "average_alert_count": round(sum(e.alert_count for e in entries) / len(entries), 4),
        }

    def acceptance_summary(self) -> dict[str, object]:
        entries = self.list_entries()
        total_days = len({e.recorded_at.date() for e in entries})
        ready_days = sum(1 for e in entries if e.ready)
        clean_cn_days = sum(1 for e in entries if e.checklist_blocked == 0)
        ready_weeks = ready_days // 7
        cn_manual_weeks = clean_cn_days // 7

        # Determine rollout recommendation
        if ready_weeks >= 8:
            recommended_stage = "100%"
        elif cn_manual_weeks >= 4:
            recommended_stage = "CN_manual_gate"
        elif ready_weeks >= 4:
            recommended_stage = "30%"
        elif ready_weeks >= 1:
            recommended_stage = "10%"
        else:
            recommended_stage = "hold"

        return {
            "total_days": total_days,
            "ready_days": ready_days,
            "clean_cn_days": clean_cn_days,
            "ready_weeks": ready_weeks,
            "cn_manual_weeks": cn_manual_weeks,
            "paper_trading": {
                "hk_us_passed": ready_weeks >= 4,
                "cn_passed": cn_manual_weeks >= 4,
            },
            "rollout": {
                "recommended_stage": recommended_stage,
            },
        }

    def acceptance_timeline(self, window_days: int = 30) -> dict[str, object]:
        entries = sorted(self.list_entries(), key=lambda entry: entry.recorded_at)
        recent = entries[-window_days:]
        points = [
            {
                "recorded_at": entry.recorded_at.isoformat(),
                "ready": entry.ready,
                "alert_count": entry.alert_count,
                "checklist_blocked": entry.checklist_blocked,
                "diagnostics_severity": entry.diagnostics_severity,
            }
            for entry in recent
        ]
        return {
            "window_days": window_days,
            "points": points,
            "ready_days": sum(1 for item in points if item["ready"]),
            "clean_cn_days": sum(1 for item in points if item["checklist_blocked"] == 0),
        }

    def rollout_readiness_timeline(self, window_days: int = 30) -> dict[str, object]:
        entries = self.list_entries()
        cutoff = datetime.now(UTC) - timedelta(days=window_days)
        recent = [e for e in entries if e.recorded_at >= cutoff]
        timeline = [
            {
                "recorded_at": e.recorded_at.isoformat(),
                "ready": e.ready,
                "alert_count": e.alert_count,
                "checklist_blocked": e.checklist_blocked,
                "diagnostics_severity": e.diagnostics_severity,
            }
            for e in sorted(recent, key=lambda e: e.recorded_at)
        ]
        ready_days = sum(1 for item in timeline if item["ready"] and item["alert_count"] == 0)
        clean_cn_days = sum(1 for item in timeline if item["checklist_blocked"] == 0)
        return {
            "window_days": window_days,
            "points": timeline,
            "ready_days": ready_days,
            "clean_cn_days": clean_cn_days,
        }

    def rollout_milestones(self) -> dict[str, object]:
        acceptance = self.acceptance_summary()
        rollout = acceptance.get("rollout", {}) if isinstance(acceptance, dict) else {}
        recommended_stage = str(rollout.get("recommended_stage", "hold"))
        ready_weeks = int(acceptance.get("ready_weeks", 0))
        cn_weeks = int(acceptance.get("cn_manual_weeks", 0))
        milestones = [
            {
                "stage": "10%",
                "status": "done" if ready_weeks >= 1 else "pending",
                "requirement": "At least one clean readiness day exists.",
                "progress_weeks": ready_weeks,
                "required_weeks": 1,
            },
            {
                "stage": "30%",
                "status": "done" if ready_weeks >= 4 else "pending",
                "requirement": "At least 4 clean readiness weeks.",
                "progress_weeks": ready_weeks,
                "required_weeks": 4,
            },
            {
                "stage": "100%",
                "status": "done" if ready_weeks >= 8 else "pending",
                "requirement": "At least 8 clean readiness weeks.",
                "progress_weeks": ready_weeks,
                "required_weeks": 8,
            },
            {
                "stage": "CN_manual_gate",
                "status": "done" if cn_weeks >= 4 else "pending",
                "requirement": "At least 4 clean CN manual weeks.",
                "progress_weeks": cn_weeks,
                "required_weeks": 4,
            },
        ]
        return {
            "current_recommendation": recommended_stage,
            "milestones": milestones,
            "next_pending_stage": next((item["stage"] for item in milestones if item["status"] == "pending"), None),
        }

    def rollout_summary(
        self,
        *,
        readiness: dict[str, object],
        compliance_summary: dict[str, object],
        alerts_summary: dict[str, object],
    ) -> dict[str, object]:
        acceptance = self.acceptance_summary()
        current_recommendation = str(acceptance.get("rollout", {}).get("recommended_stage", "hold"))
        next_stage = {
            "hold": "10%",
            "10%": "30%",
            "30%": "100%",
            "CN_manual_gate": "100%",
            "100%": None,
        }.get(current_recommendation)

        blockers: list[dict[str, object]] = []
        diagnostics = readiness.get("diagnostics", {}) if isinstance(readiness, dict) else {}
        if not bool(readiness.get("ready", False)):
            blockers.append(
                {
                    "category": str(diagnostics.get("category", "readiness_not_green")),
                    "detail": str(diagnostics.get("severity", "error")),
                    "actions": [str(item) for item in diagnostics.get("next_actions", [])],
                }
            )

        checklists = compliance_summary.get("checklists", []) if isinstance(compliance_summary, dict) else []
        pending_count = 0
        blocked_count = 0
        for checklist in checklists:
            if not isinstance(checklist, dict):
                continue
            counts = checklist.get("counts", {})
            if isinstance(counts, dict):
                pending_count += int(counts.get("pending", 0))
                blocked_count += int(counts.get("blocked", 0))
        if pending_count or blocked_count:
            blockers.append(
                {
                    "category": "compliance",
                    "detail": f"{pending_count} pending, {blocked_count} blocked checklist items",
                    "actions": ["Resolve blocked compliance items before raising rollout stage."],
                }
            )

        alert_count = int(alerts_summary.get("count", 0)) if isinstance(alerts_summary, dict) else 0
        if alert_count:
            blockers.append(
                {
                    "category": "alerts",
                    "detail": f"{alert_count} active alerts need review",
                    "actions": ["Clear broker, market-data, or reconciliation alerts before promotion."],
                }
            )

        return {
            "ready_for_rollout": not blockers,
            "current_recommendation": current_recommendation,
            "next_stage": next_stage,
            "remaining_gates": {
                "hk_us_paper_weeks": max(0, 6 - int(acceptance.get("ready_weeks", 0))),
                "cn_manual_weeks": max(0, 4 - int(acceptance.get("cn_manual_weeks", 0))),
            },
            "blockers": blockers,
        }

    def clear(self) -> None:
        self._entries = {}
        self._repository.save(self._entries)

    def _suffix_streak(self, entries: list[OperationsJournalEntry], predicate) -> int:
        streak = 0
        for entry in reversed(entries):
            if not predicate(entry):
                break
            streak += 1
        return streak

    def _qualified_dates(self, entries: list[OperationsJournalEntry], predicate) -> set[date]:
        return {entry.recorded_at.date() for entry in entries if predicate(entry)}

    def _compliance_count(self, compliance: dict[str, object], key: str) -> int:
        direct_key = f"{key}_count"
        if direct_key in compliance:
            return int(compliance.get(direct_key, 0))
        total = 0
        for checklist in compliance.get("checklists", []):
            if not isinstance(checklist, dict):
                continue
            counts = checklist.get("counts", {})
            if isinstance(counts, dict):
                total += int(counts.get(key, 0))
        return total


class RecoveryService:
    def __init__(self, repository: RecoveryAttemptRepository) -> None:
        self._repository = repository
        self._attempts = repository.load()

    def record(
        self,
        *,
        trigger: str,
        retries: int,
        before_healthy: bool,
        after_healthy: bool,
        changed: bool,
        detail: str | None,
        before_backend: str | None,
        after_backend: str | None,
    ) -> RecoveryAttempt:
        if after_healthy and not before_healthy:
            status = "recovered"
        elif not after_healthy:
            status = "failed"
        else:
            status = "unchanged"
        attempt = RecoveryAttempt(
            trigger=trigger,
            retries=retries,
            before_healthy=before_healthy,
            after_healthy=after_healthy,
            changed=changed,
            status=status,
            detail=detail,
            before_backend=before_backend,
            after_backend=after_backend,
        )
        self._attempts[attempt.id] = attempt
        self._repository.save(self._attempts)
        return attempt

    def list_attempts(self) -> list[RecoveryAttempt]:
        return sorted(self._attempts.values(), key=lambda item: item.attempted_at, reverse=True)

    def summary(self) -> dict[str, object]:
        attempts = self.list_attempts()
        if not attempts:
            return {
                "count": 0,
                "recovered_count": 0,
                "failed_count": 0,
                "latest": None,
            }
        return {
            "count": len(attempts),
            "recovered_count": sum(1 for attempt in attempts if attempt.status == "recovered"),
            "failed_count": sum(1 for attempt in attempts if attempt.status == "failed"),
            "latest": attempts[0],
        }

    def clear(self) -> None:
        self._attempts = {}
        self._repository.save(self._attempts)

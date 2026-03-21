from __future__ import annotations

from datetime import date, timedelta

from tradingcat.domain.models import OperationsJournalEntry, RecoveryAttempt
from tradingcat.repositories.state import OperationsJournalRepository, RecoveryAttemptRepository


class OperationsJournalService:
    def __init__(self, repository: OperationsJournalRepository) -> None:
        self._repository = repository
        self._entries = repository.load()

    def record(self, snapshot: dict) -> OperationsJournalEntry:
        checklists = snapshot.get("compliance", {}).get("checklists", [])
        first_checklist_counts = checklists[0].get("counts", {}) if checklists else {}
        entry = OperationsJournalEntry(
            ready=bool(snapshot.get("ready", False)),
            diagnostics_category=str(snapshot.get("diagnostics", {}).get("category", "unknown")),
            diagnostics_severity=str(snapshot.get("diagnostics", {}).get("severity", "info")),
            alert_count=int(snapshot.get("alerts", {}).get("count", 0)),
            checklist_pending=int(first_checklist_counts.get("pending", 0)),
            checklist_blocked=int(first_checklist_counts.get("blocked", 0)),
            latest_report_dir=snapshot.get("latest_report_dir"),
        )
        self._entries[entry.id] = entry
        self._repository.save(self._entries)
        return entry

    def list_entries(self) -> list[OperationsJournalEntry]:
        return sorted(self._entries.values(), key=lambda item: item.recorded_at, reverse=True)

    def summary(self) -> dict[str, object]:
        entries = self.list_entries()
        if not entries:
            return {
                "count": 0,
                "ready_ratio": 0.0,
                "average_alert_count": 0.0,
                "latest": None,
            }
        ready_count = sum(1 for entry in entries if entry.ready)
        total_alerts = sum(entry.alert_count for entry in entries)
        return {
            "count": len(entries),
            "ready_ratio": ready_count / len(entries),
            "average_alert_count": total_alerts / len(entries),
            "latest": entries[0],
        }

    def acceptance_summary(self) -> dict[str, object]:
        entries = self.list_entries()
        ready_dates = self._qualified_dates(entries, lambda e: e.ready and e.alert_count == 0)
        cn_clean_dates = self._qualified_dates(entries, lambda e: e.checklist_blocked == 0)
        ready_weeks = len(ready_dates) // 7
        cn_manual_weeks = len(cn_clean_dates) // 7
        hk_us_passed = ready_weeks >= 4
        cn_passed = cn_manual_weeks >= 4
        if ready_weeks >= 8:
            recommended_stage = "100%"
        elif ready_weeks >= 4:
            recommended_stage = "30%"
        elif ready_weeks >= 1:
            recommended_stage = "10%"
        else:
            recommended_stage = "hold"
        return {
            "paper_trading": {
                "hk_us_passed": hk_us_passed,
                "cn_passed": cn_passed,
            },
            "ready_weeks": ready_weeks,
            "cn_manual_weeks": cn_manual_weeks,
            "rollout": {
                "recommended_stage": recommended_stage,
            },
        }

    def rollout_summary(
        self,
        *,
        readiness: dict,
        compliance_summary: dict,
        alerts_summary: dict,
    ) -> dict[str, object]:
        acceptance = self.acceptance_summary()
        rollout = acceptance.get("rollout", {}) if isinstance(acceptance, dict) else {}
        recommended_stage = str(rollout.get("recommended_stage", "hold"))
        ready_weeks = int(acceptance.get("ready_weeks", 0))
        cn_weeks = int(acceptance.get("cn_manual_weeks", 0))

        blockers: list[str] = []
        if not readiness.get("ready", False):
            diag = readiness.get("diagnostics", {})
            for action in diag.get("next_actions", []):
                blockers.append(str(action))
        checklists = compliance_summary.get("checklists", [])
        for checklist in checklists:
            counts = checklist.get("counts", {})
            if int(counts.get("blocked", 0)) > 0:
                blockers.append(f"Checklist '{checklist.get('id', 'unknown')}' has {counts['blocked']} blocked item(s).")
        alert_count = int(alerts_summary.get("count", 0))
        if alert_count > 0:
            blockers.append(f"{alert_count} active alert(s).")

        stages = ["10%", "30%", "100%"]
        current_index = stages.index(recommended_stage) if recommended_stage in stages else -1
        next_stage = stages[current_index + 1] if current_index + 1 < len(stages) else None

        if ready_weeks < 4:
            remaining_hk_us = max(0, 4 - ready_weeks) + max(0, 4 - ready_weeks - cn_weeks)
        else:
            remaining_hk_us = max(0, 8 - ready_weeks)
        remaining_cn = max(0, 4 - cn_weeks)

        return {
            "ready_for_rollout": len(blockers) == 0 and recommended_stage != "hold",
            "current_recommendation": recommended_stage,
            "next_stage": next_stage,
            "remaining_gates": {
                "hk_us_paper_weeks": remaining_hk_us,
                "cn_manual_weeks": remaining_cn,
            },
            "blockers": blockers,
        }

    def acceptance_timeline(self, *, window_days: int = 30) -> dict[str, object]:
        return self.readiness_timeline(window_days=window_days)

    def readiness_timeline(self, *, window_days: int = 30) -> dict[str, object]:
        entries = self.list_entries()
        today = date.today()
        timeline: list[dict[str, object]] = []
        for offset in range(window_days):
            day = today - timedelta(days=window_days - 1 - offset)
            day_entries = [e for e in entries if e.recorded_at.date() == day]
            ready = any(e.ready for e in day_entries) if day_entries else False
            alert_count = sum(e.alert_count for e in day_entries)
            checklist_blocked = sum(e.checklist_blocked for e in day_entries)
            timeline.append(
                {
                    "date": day.isoformat(),
                    "ready": ready,
                    "alert_count": alert_count,
                    "checklist_blocked": checklist_blocked,
                    "entry_count": len(day_entries),
                }
            )
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

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

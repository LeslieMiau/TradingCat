"""ExecutionPolicyService — lightweight execution mode policy.

Replaces the overengineered rollout/acceptance gate system with a simple
policy that controls execution mode and allocation ratio.

Modes:
  - ``paper``: simulate only, no live orders
  - ``manual_live``: live orders require manual confirmation
  - ``live``: fully automated live execution
"""
from __future__ import annotations
from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import ExecutionPolicy


class ExecutionPolicyService:
    _MODE_ALLOCATION = {
        "paper": 0.0,
        "manual_live": 0.3,
        "live": 1.0,
    }

    def __init__(self, repository) -> None:
        self._repository = repository
        loaded = repository.load()
        self._policy = loaded or ExecutionPolicy()
        if loaded is None:
            self._repository.save(self._policy)

    @property
    def policy(self) -> ExecutionPolicy:
        return self._policy

    def summary(self) -> dict[str, object]:
        p = self._policy
        return {
            "mode": p.mode,
            "max_allocation_ratio": p.max_allocation_ratio,
            "manual_confirmation_required": p.manual_confirmation_required,
            "reason": p.reason,
            "updated_at": p.updated_at,
            # Compat fields for dashboard frontend (previously from rollout)
            "policy_stage": p.mode,
            "stage": p.mode,
            "allocation_ratio": p.max_allocation_ratio,
            "ready_for_live": p.mode == "live",
            "ready_for_rollout": True,
            "current_recommendation": p.mode,
            "blockers": [],
        }

    def set_mode(
        self,
        mode: str,
        *,
        reason: str | None = None,
    ) -> ExecutionPolicy:
        if mode not in self._MODE_ALLOCATION:
            raise ValueError(f"mode must be one of {list(self._MODE_ALLOCATION.keys())}")
        self._policy = ExecutionPolicy(
            mode=mode,
            max_allocation_ratio=self._MODE_ALLOCATION[mode],
            manual_confirmation_required=(mode == "manual_live"),
            reason=reason,
        )
        self._repository.save(self._policy)
        return self._policy

    def gate_readiness(self) -> dict[str, object]:
        """Gate-compatible readiness for execution_gate_summary()."""
        p = self._policy
        blockers: list[str] = []
        if p.mode == "paper":
            blockers.append("Execution mode is 'paper' — live execution not enabled.")
        elif p.mode == "manual_live":
            blockers.append("Execution mode is 'manual_live' — orders require manual confirmation.")
        return {
            "ready": p.mode == "live" or not blockers,
            "blockers": blockers,
            "mode": p.mode,
            "max_allocation_ratio": p.max_allocation_ratio,
        }

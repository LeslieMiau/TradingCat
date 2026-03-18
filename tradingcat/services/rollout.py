from __future__ import annotations

from tradingcat.domain.models import RolloutPolicy, RolloutPromotionAttempt
from tradingcat.repositories.state import RolloutPolicyRepository, RolloutPromotionRepository


class RolloutPolicyService:
    _STAGE_RATIOS = {
        "hold": 0.0,
        "10%": 0.1,
        "30%": 0.3,
        "100%": 1.0,
    }

    def __init__(self, repository: RolloutPolicyRepository) -> None:
        self._repository = repository
        loaded = repository.load()
        self._policy = loaded or RolloutPolicy()
        if loaded is None:
            self._repository.save(self._policy)

    def current(self) -> RolloutPolicy:
        return self._policy

    def summary(self) -> dict[str, object]:
        policy = self.current()
        return {
            "stage": policy.stage,
            "allocation_ratio": policy.allocation_ratio,
            "source": policy.source,
            "reason": policy.reason,
            "updated_at": policy.updated_at,
        }

    def set_policy(self, stage: str, *, reason: str | None = None, source: str = "manual") -> RolloutPolicy:
        if stage not in self._STAGE_RATIOS:
            raise ValueError("stage must be one of hold, 10%, 30%, 100%")
        if source not in {"default", "manual", "recommendation"}:
            raise ValueError("source must be one of default, manual, recommendation")
        self._policy = RolloutPolicy(
            stage=stage,
            allocation_ratio=self._STAGE_RATIOS[stage],
            source=source,
            reason=reason,
        )
        self._repository.save(self._policy)
        return self._policy

    def apply_recommendation(self, rollout_summary: dict[str, object]) -> RolloutPolicy:
        stage = str(rollout_summary.get("current_recommendation", "100%"))
        return self.set_policy(
            stage,
            reason="Applied from current rollout recommendation",
            source="recommendation",
        )


class RolloutPromotionService:
    def __init__(self, repository: RolloutPromotionRepository) -> None:
        self._repository = repository
        self._attempts = repository.load()

    def record(
        self,
        *,
        requested_stage: str,
        recommended_stage: str,
        current_stage: str,
        allowed: bool,
        reason: str | None = None,
        blocker: str | None = None,
    ) -> RolloutPromotionAttempt:
        attempt = RolloutPromotionAttempt(
            requested_stage=requested_stage,
            recommended_stage=recommended_stage,
            current_stage=current_stage,
            allowed=allowed,
            reason=reason,
            blocker=blocker,
        )
        self._attempts[attempt.id] = attempt
        self._repository.save(self._attempts)
        return attempt

    def list_attempts(self) -> list[RolloutPromotionAttempt]:
        return sorted(self._attempts.values(), key=lambda item: item.attempted_at, reverse=True)

    def summary(self) -> dict[str, object]:
        attempts = self.list_attempts()
        return {
            "count": len(attempts),
            "allowed_count": sum(1 for item in attempts if item.allowed),
            "blocked_count": sum(1 for item in attempts if not item.allowed),
            "latest": attempts[0] if attempts else None,
        }

    def clear(self) -> None:
        self._attempts = {}
        self._repository.save(self._attempts)

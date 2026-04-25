from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from tradingcat.config import LLMConfig


@dataclass(frozen=True, slots=True)
class LLMUsage:
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost: float
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    purpose: str = "research"

    @property
    def total_tokens(self) -> int:
        return max(0, self.tokens_in) + max(0, self.tokens_out)


@dataclass(frozen=True, slots=True)
class LLMBudgetDecision:
    allowed: bool
    reason: str = ""
    remaining_daily_tokens: int = 0
    remaining_monthly_cost: float = 0.0


class InMemoryLLMUsageLedger:
    def __init__(self) -> None:
        self._usage: list[LLMUsage] = []

    def append(self, usage: LLMUsage) -> None:
        self._usage.append(usage)

    def list_usage(self) -> list[LLMUsage]:
        return list(self._usage)


class LLMBudgetGate:
    """Deterministic advisory-only budget gate for future LLM calls."""

    def __init__(self, config: LLMConfig, ledger: InMemoryLLMUsageLedger | None = None) -> None:
        self._config = config
        self._ledger = ledger or InMemoryLLMUsageLedger()

    @property
    def ledger(self) -> InMemoryLLMUsageLedger:
        return self._ledger

    def check(
        self,
        *,
        provider: str,
        model: str,
        estimated_tokens: int,
        estimated_cost: float,
        now: datetime | None = None,
    ) -> LLMBudgetDecision:
        now = now or datetime.now(UTC)
        if not self._config.enabled:
            return LLMBudgetDecision(False, "llm_disabled")
        daily_used = self._daily_tokens(now.date())
        monthly_used = self._monthly_cost(now.date())
        remaining_tokens = max(0, self._config.daily_token_budget - daily_used)
        remaining_cost = max(0.0, self._config.monthly_cost_budget - monthly_used)
        if estimated_tokens > remaining_tokens:
            return LLMBudgetDecision(False, "daily_token_budget_exceeded", remaining_tokens, round(remaining_cost, 6))
        if estimated_cost > remaining_cost:
            return LLMBudgetDecision(False, "monthly_cost_budget_exceeded", remaining_tokens, round(remaining_cost, 6))
        return LLMBudgetDecision(True, "allowed", remaining_tokens - estimated_tokens, round(remaining_cost - estimated_cost, 6))

    def record(self, usage: LLMUsage) -> None:
        self._ledger.append(usage)

    def check_and_record(
        self,
        usage: LLMUsage,
    ) -> LLMBudgetDecision:
        decision = self.check(
            provider=usage.provider,
            model=usage.model,
            estimated_tokens=usage.total_tokens,
            estimated_cost=usage.cost,
            now=usage.created_at,
        )
        if decision.allowed:
            self.record(usage)
        return decision

    def _daily_tokens(self, target: date) -> int:
        return sum(usage.total_tokens for usage in self._ledger.list_usage() if usage.created_at.date() == target)

    def _monthly_cost(self, target: date) -> float:
        return sum(
            usage.cost
            for usage in self._ledger.list_usage()
            if usage.created_at.year == target.year and usage.created_at.month == target.month
        )

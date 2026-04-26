from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

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


def _usage_to_dict(u: LLMUsage) -> dict[str, Any]:
    return {
        "provider": u.provider,
        "model": u.model,
        "tokens_in": u.tokens_in,
        "tokens_out": u.tokens_out,
        "cost": u.cost,
        "created_at": u.created_at.isoformat(),
        "purpose": u.purpose,
    }


def _dict_to_usage(d: dict[str, Any]) -> LLMUsage:
    return LLMUsage(
        provider=d["provider"],
        model=d["model"],
        tokens_in=d["tokens_in"],
        tokens_out=d["tokens_out"],
        cost=d["cost"],
        created_at=datetime.fromisoformat(d["created_at"]),
        purpose=d.get("purpose", "research"),
    )


class InMemoryLLMUsageLedger:
    def __init__(self, persist_path: Path | None = None) -> None:
        self._usage: list[LLMUsage] = []
        self._persist_path = persist_path
        if persist_path is not None and persist_path.exists():
            self._load()

    def append(self, usage: LLMUsage) -> None:
        self._usage.append(usage)
        self._save()

    def list_usage(self) -> list[LLMUsage]:
        return list(self._usage)

    def _save(self) -> None:
        if self._persist_path is None:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        data = [_usage_to_dict(u) for u in self._usage]
        self._persist_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def _load(self) -> None:
        try:
            data = json.loads(self._persist_path.read_text(encoding="utf-8"))
            self._usage = [_dict_to_usage(d) for d in data if isinstance(d, dict)]
        except (json.JSONDecodeError, OSError) as exc:
            import logging

            logging.getLogger(__name__).warning("Failed to load LLM usage from %s: %s", self._persist_path, exc)
            self._usage = []


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

from __future__ import annotations

from tradingcat.adapters.llm.base import LLMMessage, LLMProviderError, LLMResponse
from tradingcat.services.llm_budget import LLMBudgetGate, LLMUsage


class FakeLLMProvider:
    provider = "fake"

    def __init__(self, budget: LLMBudgetGate, *, model: str = "fake-research", response_text: str = "ok") -> None:
        self.model = model
        self._budget = budget
        self._response_text = response_text

    def chat(self, messages: list[LLMMessage], *, purpose: str = "research") -> LLMResponse:
        tokens_in = _estimate_tokens(" ".join(message.content for message in messages))
        tokens_out = _estimate_tokens(self._response_text)
        usage = LLMUsage(
            provider=self.provider,
            model=self.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=0.0,
            purpose=purpose,
        )
        decision = self._budget.check_and_record(usage)
        if not decision.allowed:
            raise LLMProviderError(decision.reason)
        return LLMResponse(
            text=self._response_text,
            provider=self.provider,
            model=self.model,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost=0.0,
        )


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)

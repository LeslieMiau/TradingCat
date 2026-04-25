from __future__ import annotations

from typing import Any

import httpx

from tradingcat.adapters.llm.base import LLMMessage, LLMProviderError, LLMResponse
from tradingcat.adapters.llm.fake import _estimate_tokens
from tradingcat.services.llm_budget import LLMBudgetGate, LLMUsage


class OpenAICompatibleLLMProvider:
    """Small sync chat provider for OpenAI-compatible chat-completions APIs."""

    def __init__(
        self,
        budget: LLMBudgetGate,
        *,
        provider: str,
        model: str,
        api_key: str,
        base_url: str,
        cost_per_1k_tokens: float = 0.0,
        client: Any | None = None,
    ) -> None:
        self.provider = provider
        self.model = model
        self._budget = budget
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._cost_per_1k = max(0.0, float(cost_per_1k_tokens))
        self._client = client or httpx.Client(timeout=30.0)

    def chat(self, messages: list[LLMMessage], *, purpose: str = "research") -> LLMResponse:
        estimated_tokens = _estimate_tokens(" ".join(message.content for message in messages)) + 512
        estimated_cost = (estimated_tokens / 1000.0) * self._cost_per_1k
        decision = self._budget.check(
            provider=self.provider,
            model=self.model,
            estimated_tokens=estimated_tokens,
            estimated_cost=estimated_cost,
        )
        if not decision.allowed:
            raise LLMProviderError(decision.reason)

        response = self._client.post(
            f"{self._base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={
                "model": self.model,
                "messages": [{"role": message.role, "content": message.content} for message in messages],
                "temperature": 0.2,
            },
        )
        response.raise_for_status()
        payload = response.json()
        text = str(payload["choices"][0]["message"]["content"])
        usage_payload = payload.get("usage") or {}
        tokens_in = int(usage_payload.get("prompt_tokens") or _estimate_tokens(" ".join(m.content for m in messages)))
        tokens_out = int(usage_payload.get("completion_tokens") or _estimate_tokens(text))
        cost = ((tokens_in + tokens_out) / 1000.0) * self._cost_per_1k
        self._budget.record(
            LLMUsage(
                provider=self.provider,
                model=self.model,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                cost=cost,
                purpose=purpose,
            )
        )
        return LLMResponse(text=text, provider=self.provider, model=self.model, tokens_in=tokens_in, tokens_out=tokens_out, cost=cost)

from __future__ import annotations

import pytest

from tradingcat.adapters.llm import FakeLLMProvider, LLMMessage, LLMProviderError, OpenAICompatibleLLMProvider
from tradingcat.config import LLMConfig
from tradingcat.services.llm_budget import LLMBudgetGate


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeHttp:
    def __init__(self):
        self.calls = []

    def post(self, url, *, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResponse(
            {
                "choices": [{"message": {"content": "research summary"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            }
        )


def test_fake_llm_provider_records_usage_when_budget_allows():
    gate = LLMBudgetGate(LLMConfig(enabled=True, daily_token_budget=100, monthly_cost_budget=1))
    provider = FakeLLMProvider(gate, response_text="summary")

    response = provider.chat([LLMMessage(role="user", content="analyze")])

    assert response.text == "summary"
    assert response.provider == "fake"
    assert len(gate.ledger.list_usage()) == 1


def test_fake_llm_provider_raises_when_budget_denied():
    gate = LLMBudgetGate(LLMConfig(enabled=False))
    provider = FakeLLMProvider(gate)

    with pytest.raises(LLMProviderError, match="llm_disabled"):
        provider.chat([LLMMessage(role="user", content="analyze")])


def test_openai_compatible_provider_posts_chat_and_records_actual_usage():
    gate = LLMBudgetGate(LLMConfig(enabled=True, daily_token_budget=1000, monthly_cost_budget=1))
    http = _FakeHttp()
    provider = OpenAICompatibleLLMProvider(
        gate,
        provider="deepseek",
        model="deepseek-chat",
        api_key="secret",
        base_url="https://api.example.com/v1",
        cost_per_1k_tokens=0.01,
        client=http,
    )

    response = provider.chat([LLMMessage(role="user", content="hello")])

    assert response.text == "research summary"
    assert response.tokens_in == 10
    assert response.tokens_out == 5
    assert response.cost == 0.00015
    assert http.calls[0]["url"] == "https://api.example.com/v1/chat/completions"
    assert http.calls[0]["headers"] == {"Authorization": "Bearer secret"}
    assert http.calls[0]["json"]["model"] == "deepseek-chat"
    assert len(gate.ledger.list_usage()) == 1


def test_openai_compatible_provider_does_not_post_when_budget_denied():
    gate = LLMBudgetGate(LLMConfig(enabled=False))
    http = _FakeHttp()
    provider = OpenAICompatibleLLMProvider(
        gate,
        provider="qwen",
        model="qwen-plus",
        api_key="secret",
        base_url="https://api.example.com/v1",
        client=http,
    )

    with pytest.raises(LLMProviderError, match="llm_disabled"):
        provider.chat([LLMMessage(role="user", content="hello")])

    assert http.calls == []

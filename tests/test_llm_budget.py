from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.config import LLMConfig
from tradingcat.services.llm_budget import LLMBudgetGate, LLMUsage


def test_llm_budget_denies_when_disabled():
    gate = LLMBudgetGate(LLMConfig(enabled=False))

    decision = gate.check(provider="openai", model="gpt", estimated_tokens=100, estimated_cost=0.01)

    assert decision.allowed is False
    assert decision.reason == "llm_disabled"


def test_llm_budget_allows_and_records_usage():
    gate = LLMBudgetGate(LLMConfig(enabled=True, daily_token_budget=1000, monthly_cost_budget=1.0))
    usage = LLMUsage(
        provider="deepseek",
        model="chat",
        tokens_in=100,
        tokens_out=150,
        cost=0.05,
        created_at=datetime(2026, 4, 25, tzinfo=UTC),
    )

    decision = gate.check_and_record(usage)

    assert decision.allowed is True
    assert decision.remaining_daily_tokens == 750
    assert gate.ledger.list_usage() == [usage]


def test_llm_budget_blocks_daily_tokens_and_does_not_record():
    gate = LLMBudgetGate(LLMConfig(enabled=True, daily_token_budget=300, monthly_cost_budget=1.0))
    gate.record(
        LLMUsage(
            provider="qwen",
            model="plus",
            tokens_in=100,
            tokens_out=150,
            cost=0.01,
            created_at=datetime(2026, 4, 25, tzinfo=UTC),
        )
    )

    decision = gate.check_and_record(
        LLMUsage(
            provider="qwen",
            model="plus",
            tokens_in=100,
            tokens_out=100,
            cost=0.01,
            created_at=datetime(2026, 4, 25, tzinfo=UTC),
        )
    )

    assert decision.allowed is False
    assert decision.reason == "daily_token_budget_exceeded"
    assert len(gate.ledger.list_usage()) == 1


def test_llm_budget_blocks_monthly_cost():
    gate = LLMBudgetGate(LLMConfig(enabled=True, daily_token_budget=10_000, monthly_cost_budget=0.10))
    gate.record(
        LLMUsage(
            provider="openai",
            model="gpt",
            tokens_in=10,
            tokens_out=10,
            cost=0.08,
            created_at=datetime(2026, 4, 1, tzinfo=UTC),
        )
    )

    decision = gate.check(
        provider="openai",
        model="gpt",
        estimated_tokens=10,
        estimated_cost=0.03,
        now=datetime(2026, 4, 25, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.reason == "monthly_cost_budget_exceeded"


def test_llm_config_from_env():
    cfg = LLMConfig.from_env(
        {
            "TRADINGCAT_LLM_ENABLED": "true",
            "TRADINGCAT_LLM_PROVIDER": "DeepSeek",
            "TRADINGCAT_LLM_MODEL": "deepseek-chat",
            "TRADINGCAT_LLM_MAX_TOKENS": "4096",
            "TRADINGCAT_LLM_DAILY_TOKEN_BUDGET": "1234",
            "TRADINGCAT_LLM_MONTHLY_COST_BUDGET": "12.5",
        }
    )

    assert cfg.enabled is True
    assert cfg.provider == "deepseek"
    assert cfg.model == "deepseek-chat"
    assert cfg.max_tokens == 4096
    assert cfg.daily_token_budget == 1234
    assert cfg.monthly_cost_budget == 12.5


def test_in_memory_ledger_persists_and_restores(tmp_path):
    from pathlib import Path

    from tradingcat.services.llm_budget import InMemoryLLMUsageLedger

    persist_path = tmp_path / "llm_usage.json"
    ledger = InMemoryLLMUsageLedger(persist_path=persist_path)
    usage = LLMUsage(
        provider="deepseek",
        model="chat",
        tokens_in=50,
        tokens_out=30,
        cost=0.01,
        created_at=datetime(2026, 4, 25, tzinfo=UTC),
    )
    ledger.append(usage)

    ledger2 = InMemoryLLMUsageLedger(persist_path=persist_path)
    restored = ledger2.list_usage()

    assert len(restored) == 1
    assert restored[0].provider == "deepseek"
    assert restored[0].tokens_in == 50
    assert restored[0].tokens_out == 30
    assert restored[0].cost == 0.01


def test_in_memory_ledger_no_persist_path_does_not_write(tmp_path):
    from tradingcat.services.llm_budget import InMemoryLLMUsageLedger

    ledger = InMemoryLLMUsageLedger()
    usage = LLMUsage(provider="x", model="y", tokens_in=1, tokens_out=1, cost=0.0)
    ledger.append(usage)

    assert ledger.list_usage() == [usage]

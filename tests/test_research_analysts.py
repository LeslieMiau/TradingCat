from __future__ import annotations

from tradingcat.adapters.llm import FakeLLMProvider
from tradingcat.config import LLMConfig
from tradingcat.domain.models import OrderIntent, Signal
from tradingcat.services.llm_budget import LLMBudgetGate
from tradingcat.services.research_analysts import ResearchAnalystService


def test_research_analyst_returns_structured_advisory_output():
    gate = LLMBudgetGate(LLMConfig(enabled=True))
    provider = FakeLLMProvider(
        gate,
        response_text="\n".join(
            [
                "Market tone is constructive but not decisive.",
                "- Breadth improved",
                "- Risk: policy headlines remain noisy",
            ]
        ),
    )
    service = ResearchAnalystService(provider)

    output = service.analyze(
        "news",
        {"sources": ["eastmoney", "cls"], "items": [{"title": "policy support"}]},
        source_refs=["https://example.com/news"],
    )

    assert output.analyst_id == "news"
    assert output.summary == "Market tone is constructive but not decisive."
    assert output.bullets == ["Breadth improved", "Risk: policy headlines remain noisy"]
    assert output.risks == ["Risk: policy headlines remain noisy"]
    assert output.source_refs == ["https://example.com/news"]
    assert output.metadata["advisory_only"] is True
    assert len(gate.ledger.list_usage()) == 1


def test_research_analyst_output_is_not_signal_or_order_intent():
    gate = LLMBudgetGate(LLMConfig(enabled=True))
    service = ResearchAnalystService(FakeLLMProvider(gate, response_text="summary"))

    output = service.analyze("technical", {"sources": []})

    assert not isinstance(output, Signal)
    assert not isinstance(output, OrderIntent)
    assert output.metadata["advisory_only"] is True

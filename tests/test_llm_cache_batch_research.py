from __future__ import annotations

from pathlib import Path

from tradingcat.adapters.llm import FakeLLMProvider, LLMMessage
from tradingcat.config import LLMConfig
from tradingcat.domain.models import Instrument, Market
from tradingcat.domain.news import NewsItem
from tradingcat.services.batch_research import BatchResearchService
from tradingcat.services.llm_budget import LLMBudgetGate
from tradingcat.services.llm_cache import CachedLLMProvider, InMemoryLLMResponseCache
from tradingcat.services.research_analysts import ResearchAnalystService
from tradingcat.services.universe_screener import UniverseScreener


def test_cached_llm_provider_reuses_response_without_second_usage_record():
    gate = LLMBudgetGate(LLMConfig(enabled=True))
    cached = CachedLLMProvider(FakeLLMProvider(gate, response_text="cached summary"), InMemoryLLMResponseCache())
    messages = [LLMMessage(role="user", content="same prompt")]

    first = cached.chat(messages, purpose="analyst")
    second = cached.chat(messages, purpose="analyst")

    assert first == second
    assert len(gate.ledger.list_usage()) == 1


def test_batch_research_runs_screener_analyst_and_markdown():
    gate = LLMBudgetGate(LLMConfig(enabled=True))
    analyst = ResearchAnalystService(FakeLLMProvider(gate, response_text="Batch looks constructive.\n- Candidate quality improved"))
    service = BatchResearchService(screener=UniverseScreener(), analyst=analyst)
    instruments = [
        Instrument(symbol="600000", market=Market.CN, currency="CNY"),
        Instrument(symbol="300308", market=Market.CN, currency="CNY"),
    ]

    result = service.run(
        instruments,
        technical={"300308": {"trend_alignment": "bullish_alignment", "momentum_state": "positive_momentum"}},
        fundamentals={"300308": {"pe": 20, "pb": 2, "roe": 18, "revenue_growth": 30}},
        news=[NewsItem(source="cls", title="行业利好 300308", symbols=["300308"], relevance=1.0, quality_score=0.9)],
        limit=2,
    )

    assert result.candidates[0].instrument.symbol == "300308"
    assert result.analyst_outputs[0].metadata["advisory_only"] is True
    assert result.report_markdown is not None
    assert "Batch Research" in result.report_markdown
    assert len(gate.ledger.list_usage()) == 1


def test_batch_research_writes_report_when_path_requested(tmp_path):
    gate = LLMBudgetGate(LLMConfig(enabled=True))
    analyst = ResearchAnalystService(FakeLLMProvider(gate, response_text="summary"))
    service = BatchResearchService(screener=UniverseScreener(), analyst=analyst)
    report_path = tmp_path / "batch.md"

    result = service.run(
        [Instrument(symbol="600000", market=Market.CN, currency="CNY")],
        report_path=report_path,
    )

    assert result.report_path == report_path
    assert result.report_markdown is None
    assert Path(report_path).read_text(encoding="utf-8").startswith("# Batch Research")

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tradingcat.domain.models import Instrument
from tradingcat.domain.news import NewsItem
from tradingcat.services.report_export import ReportExportService
from tradingcat.services.research_analysts import AnalystOutput, ResearchAnalystService
from tradingcat.services.universe_screener import UniverseCandidate, UniverseScreener
from tradingcat.strategies.research_candidates import TechnicalFeatureSnapshot


@dataclass(frozen=True, slots=True)
class BatchResearchResult:
    candidates: list[UniverseCandidate]
    analyst_outputs: list[AnalystOutput]
    report_path: Path | None = None
    report_markdown: str | None = None


class BatchResearchService:
    """Lightweight advisory batch research orchestration."""

    def __init__(
        self,
        *,
        screener: UniverseScreener,
        analyst: ResearchAnalystService,
        exporter: ReportExportService | None = None,
    ) -> None:
        self._screener = screener
        self._analyst = analyst
        self._exporter = exporter or ReportExportService()

    def run(
        self,
        instruments: list[Instrument],
        *,
        technical: dict[str, TechnicalFeatureSnapshot | dict[str, Any]] | None = None,
        fundamentals: dict[str, dict[str, Any]] | None = None,
        news: list[NewsItem | dict[str, Any]] | None = None,
        limit: int = 10,
        report_path: Path | None = None,
    ) -> BatchResearchResult:
        candidates = self._screener.screen(
            instruments,
            technical=technical,
            fundamentals=fundamentals,
            news=news,
            limit=limit,
        )
        payload = {
            "candidate_count": len(candidates),
            "top_candidates": [candidate.as_dict() for candidate in candidates[:limit]],
            "news_count": len(news or []),
            "sources": ["universe_screener", "news_filter", "technical_features"],
        }
        analyst_output = self._analyst.analyze("batch_research", payload, source_refs=["batch_research"])
        normalized_news = [_coerce_news(item) for item in (news or [])]
        normalized_news = [item for item in normalized_news if item is not None]
        if report_path is not None:
            written = self._exporter.export_markdown(
                report_path,
                title="Batch Research",
                analysts=[analyst_output],
                candidates=candidates,
                news_items=normalized_news,
            )
            return BatchResearchResult(candidates=candidates, analyst_outputs=[analyst_output], report_path=written)
        markdown = self._exporter.render_markdown(
            title="Batch Research",
            analysts=[analyst_output],
            candidates=candidates,
            news_items=normalized_news,
        )
        return BatchResearchResult(candidates=candidates, analyst_outputs=[analyst_output], report_markdown=markdown)


def _coerce_news(raw: NewsItem | dict[str, Any]) -> NewsItem | None:
    if isinstance(raw, NewsItem):
        return raw
    try:
        return NewsItem.model_validate(raw)
    except Exception:
        return None

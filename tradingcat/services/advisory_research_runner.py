"""Daily advisory-research orchestration.

Runs the absorbed research pipeline (universe screener + analyst +
report exporter) once per day, files the resulting Markdown under a
configurable directory, and prunes reports older than the retention
window.

Design notes:

- Pure dependency-injection. No coupling to FastAPI, scheduler, or
  ``TradingCatApplication``. The app wires it; the scheduler calls it.
- Graceful degradation. With no configured news sources or no LLM
  provider, the runner still emits a useful report — universe candidates
  + technical reasons sections render, the analyst section turns into
  ``_暂无分析师输出。_``. Adding optional deps / API keys upgrades each
  section independently.
- Advisory only. The runner consumes data, produces a Markdown file.
  It never returns ``Signal`` / ``OrderIntent`` / approval objects.
- Idempotent per day. ``run_for(as_of)`` writes ``YYYY-MM-DD.md``;
  rerunning the same day overwrites in place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Callable, Iterable

from tradingcat.domain.models import Bar, Instrument
from tradingcat.domain.news import NewsItem
from tradingcat.services.report_export import ReportExportService
from tradingcat.services.research_analysts import (
    AnalystOutput,
    ResearchAnalystService,
)
from tradingcat.services.universe_screener import UniverseScreener
from tradingcat.strategies.research_candidates import compute_technical_features


logger = logging.getLogger(__name__)


InstrumentProvider = Callable[[], Iterable[Instrument]]
BarsProvider = Callable[[Instrument, date, date], list[Bar]]
NewsProvider = Callable[[], Iterable[NewsItem]]
FundamentalsProvider = Callable[[Iterable[Instrument]], dict[str, dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class AdvisoryRunResult:
    as_of: date
    output_path: Path
    instrument_count: int
    candidate_count: int
    news_count: int
    analyst_called: bool
    pruned_paths: list[Path]


class AdvisoryResearchRunner:
    """Filed daily advisory-research artefact producer."""

    def __init__(
        self,
        *,
        output_dir: Path,
        instrument_provider: InstrumentProvider,
        bars_provider: BarsProvider,
        news_provider: NewsProvider | None = None,
        fundamentals_provider: FundamentalsProvider | None = None,
        analyst: ResearchAnalystService | None = None,
        screener: UniverseScreener | None = None,
        exporter: ReportExportService | None = None,
        retention_days: int = 30,
        candidate_limit: int = 10,
        bars_lookback_days: int = 120,
    ) -> None:
        self._output_dir = output_dir
        self._instrument_provider = instrument_provider
        self._bars_provider = bars_provider
        self._news_provider = news_provider or (lambda: ())
        self._fundamentals_provider = fundamentals_provider or (lambda _: {})
        self._analyst = analyst
        self._screener = screener or UniverseScreener()
        self._exporter = exporter or ReportExportService()
        self._retention_days = max(1, int(retention_days))
        self._candidate_limit = max(1, int(candidate_limit))
        self._bars_lookback_days = max(20, int(bars_lookback_days))

    # ------------------------------------------------------------------ run

    def run_for(self, as_of: date) -> AdvisoryRunResult:
        """Generate the advisory report for ``as_of`` and prune old files."""

        instruments = list(self._instrument_provider() or [])
        if not instruments:
            logger.info("Advisory report: no instruments returned, writing empty report")
        technical = self._compute_technical(instruments, as_of)
        fundamentals = self._fundamentals_provider(instruments) if instruments else {}
        news_items = list(self._news_provider() or [])

        candidates = self._screener.screen(
            instruments,
            technical=technical,
            fundamentals=fundamentals,
            news=news_items,
            limit=self._candidate_limit,
        )

        analyst_outputs: list[AnalystOutput] = []
        analyst_called = False
        if self._analyst is not None:
            analyst_called = True
            payload = {
                "as_of": as_of.isoformat(),
                "candidate_count": len(candidates),
                "top_candidates": [c.as_dict() for c in candidates[:self._candidate_limit]],
                "news_count": len(news_items),
                "sources": ["universe_screener", "news_filter", "technical_features"],
            }
            try:
                analyst_outputs.append(
                    self._analyst.analyze(
                        "daily_advisory",
                        payload,
                        source_refs=["daily_advisory_runner"],
                    )
                )
            except Exception as exc:  # never propagate to scheduler
                logger.warning("Daily advisory analyst skipped: %s", exc)

        output_path = self._output_dir / f"{as_of.isoformat()}.md"
        self._exporter.export_markdown(
            output_path,
            title=f"每日研究 {as_of.isoformat()}",
            analysts=analyst_outputs,
            candidates=candidates,
            news_items=news_items,
        )

        pruned = self._prune_old(as_of)
        return AdvisoryRunResult(
            as_of=as_of,
            output_path=output_path,
            instrument_count=len(instruments),
            candidate_count=len(candidates),
            news_count=len(news_items),
            analyst_called=analyst_called,
            pruned_paths=pruned,
        )

    # ------------------------------------------------------------------ helpers

    def _compute_technical(
        self,
        instruments: list[Instrument],
        as_of: date,
    ) -> dict[str, Any]:
        start = as_of - timedelta(days=self._bars_lookback_days)
        snapshots: dict[str, Any] = {}
        for instrument in instruments:
            try:
                bars = self._bars_provider(instrument, start, as_of)
            except Exception as exc:
                logger.debug("Daily advisory bars fetch failed for %s: %s", instrument.symbol, exc)
                continue
            if not bars:
                continue
            try:
                snapshots[instrument.symbol] = compute_technical_features(bars)
            except Exception as exc:
                logger.debug(
                    "Daily advisory technical features failed for %s: %s",
                    instrument.symbol,
                    exc,
                )
        return snapshots

    def _prune_old(self, as_of: date) -> list[Path]:
        if not self._output_dir.exists():
            return []
        cutoff = as_of - timedelta(days=self._retention_days)
        pruned: list[Path] = []
        for path in self._output_dir.glob("*.md"):
            stem = path.stem  # YYYY-MM-DD
            try:
                file_date = date.fromisoformat(stem)
            except ValueError:
                continue
            if file_date < cutoff:
                try:
                    path.unlink()
                    pruned.append(path)
                except OSError as exc:
                    logger.debug("Failed to prune advisory report %s: %s", path, exc)
        return pruned

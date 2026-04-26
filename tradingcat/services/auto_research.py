"""Automated research pipeline — runs on schedule, generates reports.

Phase 3.3 of the architecture plan:
- Weekly: feature calculation → factor IC evaluation → strategy backtest → report
- Monthly: full research cycle including candidate factor screening
- Continuous: factor decay detection (IC insignificance for 4+ weeks)
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ResearchReport:
    generated_at: datetime = field(default_factory=datetime.now)
    period_start: date | None = None
    period_end: date | None = None
    factor_count: int = 0
    top_factors: list[dict[str, Any]] = field(default_factory=list)
    strategy_count: int = 0
    strategy_signals: list[dict[str, Any]] = field(default_factory=list)
    factor_decay_warnings: list[str] = field(default_factory=list)
    candidate_suggestions: list[str] = field(default_factory=list)
    summary: str = ""
    report_path: str | None = None


class AutoResearchPipeline:
    """Orchestrates the full research pipeline on a schedule.

    Designed to be called from the scheduler (or cron) — either weekly or
    monthly.  All outputs are written to ``data/research/`` as JSON.
    """

    def __init__(
        self,
        data_dir: str | Path = "data",
        feature_service: object | None = None,
        factor_service: object | None = None,
        backtest_service: object | None = None,
    ) -> None:
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._report_dir = self._data_dir / "research"
        self._report_dir.mkdir(parents=True, exist_ok=True)

        # Optional service references — when not provided, the pipeline
        # logs a warning and skips that step.
        self._feature_service = feature_service
        self._factor_service = factor_service
        self._backtest_service = backtest_service

        # Factor decay tracking
        self._decay_file = self._data_dir / "factor_decay.json"
        self._decay: dict[str, list[float]] = self._load_decay()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_weekly(self, as_of: date | None = None) -> ResearchReport:
        """Weekly research cycle: features → factors → backtests → report."""
        eval_date = as_of or date.today()
        period_start = eval_date - timedelta(days=7)
        report = ResearchReport(period_start=period_start, period_end=eval_date)

        self._run_features(report)
        self._run_factors(report)
        self._run_backtests(report)
        self._check_factor_decay(report)
        self._generate_summary(report)
        self._save_report(report)

        return report

    def run_monthly(self, as_of: date | None = None) -> ResearchReport:
        """Monthly cycle — same as weekly plus candidate screening."""
        report = self.run_weekly(as_of)
        self._screen_candidates(report)
        self._save_report(report)
        return report

    # ------------------------------------------------------------------
    # Pipeline steps
    # ------------------------------------------------------------------

    def _run_features(self, report: ResearchReport) -> None:
        if self._feature_service is None:
            logger.warning("Feature service not available — skipping feature step")
            return
        try:
            if hasattr(self._feature_service, "compute_all"):
                result = self._feature_service.compute_all()
                report.factor_count = len(result) if isinstance(result, dict) else 0
        except Exception:
            logger.exception("Feature computation failed")

    def _run_factors(self, report: ResearchReport) -> None:
        if self._factor_service is None:
            logger.warning("Factor service not available — skipping factor step")
            return
        try:
            if hasattr(self._factor_service, "compute_ic"):
                ic_result = self._factor_service.compute_ic()
                if isinstance(ic_result, dict):
                    for name, metrics in ic_result.items():
                        if isinstance(metrics, dict):
                            report.top_factors.append({
                                "factor": name,
                                "ic": metrics.get("ic", 0),
                                "icir": metrics.get("icir", 0),
                                "win_rate": metrics.get("win_rate", 0),
                            })
                            self._record_ic(name, float(metrics.get("ic", 0)))
        except Exception:
            logger.exception("Factor analysis failed")

    def _run_backtests(self, report: ResearchReport) -> None:
        if self._backtest_service is None:
            logger.warning("Backtest service not available — skipping backtest step")
            return
        try:
            if hasattr(self._backtest_service, "run_all"):
                results = self._backtest_service.run_all()
                if isinstance(results, dict):
                    for strategy_id, result in results.items():
                        if isinstance(result, dict):
                            report.strategy_signals.append({
                                "strategy": strategy_id,
                                "sharpe": result.get("sharpe", 0),
                                "total_return": result.get("total_return", 0),
                                "max_drawdown": result.get("max_drawdown", 0),
                            })
        except Exception:
            logger.exception("Backtest run failed")

    def _check_factor_decay(self, report: ResearchReport) -> None:
        """Flag factors whose IC has been near-zero for 4+ weeks."""
        for factor, ic_history in list(self._decay.items()):
            recent = ic_history[-8:]  # ~8 weeks
            if len(recent) >= 4:
                mean_ic = float(np.mean(np.abs(recent)))
                if mean_ic < 0.02:
                    report.factor_decay_warnings.append(
                        f"{factor}: mean |IC|={mean_ic:.4f} over {len(recent)} weeks"
                    )

    def _screen_candidates(self, report: ResearchReport) -> None:
        """Suggest new factors based on gaps in coverage."""
        existing = {f["factor"] for f in report.top_factors}
        candidates = [
            "momentum_6m", "volume_trend", "volatility_skew",
            "growth_consensus", "short_interest_ratio",
        ]
        report.candidate_suggestions = [
            c for c in candidates if c not in existing
        ]

    def _generate_summary(self, report: ResearchReport) -> None:
        parts = []
        if report.factor_count > 0:
            parts.append(f"Computed {report.factor_count} features")
        if report.top_factors:
            top = report.top_factors[:3]
            parts.append(
                f"Top factors: {', '.join(f['factor'] + ' (IC=' + f'{f["ic"]:.3f}' + ')' for f in top)}"
            )
        if report.strategy_signals:
            n_ok = sum(1 for s in report.strategy_signals if s.get("sharpe", 0) > 0.5)
            parts.append(f"{n_ok}/{len(report.strategy_signals)} strategies above Sharpe 0.5")
        if report.factor_decay_warnings:
            parts.append(f"{len(report.factor_decay_warnings)} factor(s) flagged for decay")
        report.summary = " | ".join(parts) if parts else "暂无可用数据"

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _record_ic(self, factor: str, ic: float) -> None:
        self._decay.setdefault(factor, []).append(ic)
        self._save_decay()

    def _load_decay(self) -> dict[str, list[float]]:
        if self._decay_file.exists():
            try:
                data = json.loads(self._decay_file.read_text())
                return {k: list(v) for k, v in data.items()}
            except Exception:
                logger.exception("Failed to load factor decay data")
        return {}

    def _save_decay(self) -> None:
        try:
            self._decay_file.write_text(json.dumps(self._decay, indent=2))
        except Exception:
            logger.exception("Failed to save factor decay data")

    def _save_report(self, report: ResearchReport) -> None:
        timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
        path = self._report_dir / f"research_report_{timestamp}.json"
        try:
            path.write_text(json.dumps({
                "generated_at": report.generated_at.isoformat(),
                "period_start": report.period_start.isoformat() if report.period_start else None,
                "period_end": report.period_end.isoformat() if report.period_end else None,
                "factor_count": report.factor_count,
                "top_factors": report.top_factors,
                "strategy_signals": report.strategy_signals,
                "factor_decay_warnings": report.factor_decay_warnings,
                "candidate_suggestions": report.candidate_suggestions,
                "summary": report.summary,
            }, indent=2))
            report.report_path = str(path)
            logger.info("Research report saved to %s", path)
        except Exception:
            logger.exception("Failed to save research report")

    def latest_report(self) -> dict[str, Any] | None:
        paths = sorted(self._report_dir.glob("research_report_*.json"))
        if not paths:
            return None
        try:
            return json.loads(paths[-1].read_text())
        except Exception:
            return None

    def factor_decay_status(self) -> dict[str, list[float]]:
        return dict(self._decay)

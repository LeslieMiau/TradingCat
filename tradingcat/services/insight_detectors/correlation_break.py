"""Detect when an instrument breaks its historical correlation with a benchmark.

Trigger:
- Symbol belongs to portfolio or watchlist
- 30-day rolling correlation with at least one same-market benchmark >= 0.5
- Today's return-difference (asset - benchmark) z-score (vs past 90 days) >= 2.0

Severity:
- |z| >= 3.0 OR opposite-sign return -> urgent
- |z| >= 2.0 same-sign -> notable
"""
from __future__ import annotations

import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev

from tradingcat.domain.models import (
    Bar,
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    Instrument,
    Market,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CorrelationBreakConfig:
    correlation_window: int = 30
    deviation_window: int = 90
    min_correlation: float = 0.5
    z_notable: float = 2.0
    z_urgent: float = 3.0
    expires_hours: int = 36


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for previous, current in zip(closes[:-1], closes[1:], strict=False):
        if previous and previous > 0:
            out.append((current / previous) - 1.0)
    return out


def _correlation(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) < 2 or len(xs) != len(ys):
        return None
    mean_x = mean(xs)
    mean_y = mean(ys)
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=False))
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x <= 0 or var_y <= 0:
        return None
    return num / math.sqrt(var_x * var_y)


def _zscore(sample: list[float], today: float) -> tuple[float, float, float] | None:
    """Return (z, mean, std) using past sample, or None if not enough data."""
    if len(sample) < 10:
        return None
    mu = mean(sample)
    sigma = pstdev(sample)
    if sigma <= 1e-12:
        return None
    return (today - mu) / sigma, mu, sigma


def _stable_id(symbol: str, benchmark: str, as_of: date) -> str:
    raw = f"correlation_break:{symbol}:{benchmark}:{as_of.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class CorrelationBreakDetector:
    """Pure-data detector. Takes pre-fetched bars; emits insights."""

    def __init__(self, config: CorrelationBreakConfig | None = None) -> None:
        self._config = config or CorrelationBreakConfig()

    @property
    def config(self) -> CorrelationBreakConfig:
        return self._config

    def required_lookback_days(self) -> int:
        return self._config.correlation_window + self._config.deviation_window + 5

    def detect(
        self,
        *,
        as_of: date,
        watchlist: list[Instrument],
        bars_by_symbol: dict[str, list[Bar]],
        benchmark_by_market: dict[Market, str],
        now: datetime | None = None,
    ) -> list[Insight]:
        triggered_at = now or datetime.now(timezone.utc)
        out: list[Insight] = []
        for instrument in watchlist:
            benchmark_symbol = benchmark_by_market.get(instrument.market)
            if not benchmark_symbol:
                continue
            insight = self._detect_one(
                instrument=instrument,
                benchmark_symbol=benchmark_symbol,
                bars_by_symbol=bars_by_symbol,
                as_of=as_of,
                triggered_at=triggered_at,
            )
            if insight is not None:
                out.append(insight)
        return out

    def _detect_one(
        self,
        *,
        instrument: Instrument,
        benchmark_symbol: str,
        bars_by_symbol: dict[str, list[Bar]],
        as_of: date,
        triggered_at: datetime,
    ) -> Insight | None:
        asset_bars = bars_by_symbol.get(instrument.symbol) or []
        bench_bars = bars_by_symbol.get(benchmark_symbol) or []
        asset_closes = [float(bar.close) for bar in sorted(asset_bars, key=lambda b: b.timestamp)]
        bench_closes = [float(bar.close) for bar in sorted(bench_bars, key=lambda b: b.timestamp)]
        if len(asset_closes) < self._config.correlation_window + 2:
            return None
        if len(bench_closes) < self._config.correlation_window + 2:
            return None

        asset_returns = _returns(asset_closes)
        bench_returns = _returns(bench_closes)
        usable = min(len(asset_returns), len(bench_returns))
        if usable < self._config.correlation_window + 1:
            return None
        asset_returns = asset_returns[-usable:]
        bench_returns = bench_returns[-usable:]

        corr_window = self._config.correlation_window
        rolling_corr = _correlation(
            asset_returns[-corr_window:],
            bench_returns[-corr_window:],
        )
        if rolling_corr is None or abs(rolling_corr) < self._config.min_correlation:
            return None

        # Build the return-difference series; today is the last entry, past
        # ``deviation_window`` entries form the historical sample.
        diff_series = [a - b for a, b in zip(asset_returns, bench_returns, strict=False)]
        if len(diff_series) < self._config.deviation_window + 1:
            return None
        sample = diff_series[-(self._config.deviation_window + 1) : -1]
        today_diff = diff_series[-1]
        z_result = _zscore(sample, today_diff)
        if z_result is None:
            return None
        z, mu, sigma = z_result
        if abs(z) < self._config.z_notable:
            return None

        today_asset_ret = asset_returns[-1]
        today_bench_ret = bench_returns[-1]
        opposite_sign = (today_asset_ret * today_bench_ret) < 0
        urgent = abs(z) >= self._config.z_urgent or opposite_sign
        severity = InsightSeverity.URGENT if urgent else InsightSeverity.NOTABLE
        confidence = min(1.0, abs(z) / self._config.z_urgent)
        if opposite_sign:
            confidence = min(1.0, confidence + 0.1)

        evidence = self._build_evidence(
            instrument=instrument,
            benchmark_symbol=benchmark_symbol,
            rolling_corr=rolling_corr,
            today_asset_ret=today_asset_ret,
            today_bench_ret=today_bench_ret,
            today_diff=today_diff,
            z=z,
            mu=mu,
            sigma=sigma,
            sample_size=len(sample),
            triggered_at=triggered_at,
        )

        direction = "反向" if opposite_sign else "同向幅度"
        headline = (
            f"{instrument.symbol} 与 {benchmark_symbol} 30 日相关性 {rolling_corr:.2f},"
            f"今日{direction}偏离 z={z:+.2f}"
        )
        return Insight(
            id=_stable_id(instrument.symbol, benchmark_symbol, as_of),
            kind=InsightKind.CORRELATION_BREAK,
            severity=severity,
            headline=headline,
            subjects=[instrument.symbol, benchmark_symbol],
            causal_chain=evidence,
            confidence=round(confidence, 4),
            triggered_at=triggered_at,
            expires_at=triggered_at + timedelta(hours=self._config.expires_hours),
        )

    def _build_evidence(
        self,
        *,
        instrument: Instrument,
        benchmark_symbol: str,
        rolling_corr: float,
        today_asset_ret: float,
        today_bench_ret: float,
        today_diff: float,
        z: float,
        mu: float,
        sigma: float,
        sample_size: int,
        triggered_at: datetime,
    ) -> list[InsightEvidence]:
        return [
            InsightEvidence(
                source=f"market_data:{instrument.symbol},{benchmark_symbol}",
                fact=(
                    f"{instrument.symbol} 与 {benchmark_symbol} 在过去 "
                    f"{self._config.correlation_window} 日的滚动相关性 = {rolling_corr:.3f}"
                ),
                value={
                    "rolling_correlation": round(rolling_corr, 4),
                    "window_days": self._config.correlation_window,
                    "min_correlation_threshold": self._config.min_correlation,
                },
                observed_at=triggered_at,
            ),
            InsightEvidence(
                source=f"market_data:{instrument.symbol}",
                fact=(
                    f"今日 {instrument.symbol} 收益 {today_asset_ret * 100:+.2f}%,"
                    f"{benchmark_symbol} 收益 {today_bench_ret * 100:+.2f}%,"
                    f"差值 {today_diff * 100:+.2f}%"
                ),
                value={
                    "asset_return": round(today_asset_ret, 6),
                    "benchmark_return": round(today_bench_ret, 6),
                    "diff": round(today_diff, 6),
                    "opposite_sign": (today_asset_ret * today_bench_ret) < 0,
                },
                observed_at=triggered_at,
            ),
            InsightEvidence(
                source="insight_engine:zscore",
                fact=(
                    f"差值 z-score = {z:+.2f}(过去 {sample_size} 日均值 "
                    f"{mu * 100:+.2f}%,标准差 {sigma * 100:.2f}%)"
                ),
                value={
                    "z_score": round(z, 4),
                    "sample_mean": round(mu, 6),
                    "sample_std": round(sigma, 6),
                    "sample_size": sample_size,
                    "z_notable": self._config.z_notable,
                    "z_urgent": self._config.z_urgent,
                },
                observed_at=triggered_at,
            ),
        ]

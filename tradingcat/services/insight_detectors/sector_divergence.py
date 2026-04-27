"""Detect when an instrument diverges from its sector peers.

Trigger:
- Symbol belongs to a sector with ≥2 instruments in the watchlist
- Sector itself moved ≥ ``min_sector_move_pct`` today (equal-weighted avg)
- Instrument's today return ≤ Nth percentile or ≥ (100-N)th percentile within sector
- Instrument has ≥ ``min_beta`` versus the equal-weighted sector return historically

Severity:
- ≤ urgent_percentile or ≥ (100-urgent_percentile) → urgent
- ≤ notable_percentile or ≥ (100-notable_percentile) → notable
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev

from tradingcat.domain.models import Bar, Insight, InsightEvidence, InsightKind, InsightSeverity, Instrument, Market

from .sector_map import SectorMap


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SectorDivergenceConfig:
    deviation_window: int = 60
    min_sector_move_pct: float = 2.0
    percentile_notable: float = 20.0
    percentile_urgent: float = 10.0
    min_beta: float = 0.7
    expires_hours: int = 36


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for previous, current in zip(closes[:-1], closes[1:], strict=False):
        if previous and previous > 0:
            out.append((current / previous) - 1.0)
    return out


def _beta(asset_returns: list[float], sector_returns: list[float]) -> float | None:
    """Compute beta of *asset_returns* vs *sector_returns* (same length)."""
    if len(asset_returns) < 10 or len(asset_returns) != len(sector_returns):
        return None
    m_a = mean(asset_returns)
    m_s = mean(sector_returns)
    cov = sum((a - m_a) * (s - m_s) for a, s in zip(asset_returns, sector_returns, strict=False))
    var_s = sum((s - m_s) ** 2 for s in sector_returns)
    if var_s <= 1e-12:
        return None
    return cov / var_s


def _percentile_rank(value: float, series: list[float]) -> float:
    """Return the percentile rank of *value* within *series* (0–100)."""
    if not series:
        return 50.0
    count_below = sum(1 for v in series if v < value)
    count_equal = sum(1 for v in series if v == value)
    return (count_below + 0.5 * count_equal) / len(series) * 100.0


def _stable_id(symbol: str, sector: str, as_of: date) -> str:
    raw = f"sector_divergence:{symbol}:{sector}:{as_of.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class SectorDivergenceDetector:
    """Emit insights when an instrument's return diverges from its sector peers."""

    def __init__(
        self,
        config: SectorDivergenceConfig | None = None,
        sector_map: SectorMap | None = None,
    ) -> None:
        self._config = config or SectorDivergenceConfig()
        self._sector_map = sector_map or SectorMap()

    @property
    def config(self) -> SectorDivergenceConfig:
        return self._config

    def required_lookback_days(self) -> int:
        return self._config.deviation_window + 10

    def detect(
        self,
        *,
        as_of: date,
        watchlist: list[Instrument],
        bars_by_symbol: dict[str, list[Bar]],
        benchmark_by_market: dict[Market, str] | None = None,  # noqa: ARG002 — unused, kept for protocol compat
        now: datetime | None = None,
    ) -> list[Insight]:
        triggered_at = now or datetime.now(timezone.utc)
        out: list[Insight] = []

        # Group watchlist by sector
        sector_groups = self._sector_map.group_by_sector(watchlist)
        # Pre-compute closes for all symbols we have bars for
        closes_by_symbol: dict[str, list[float]] = {}
        for sym, bars in bars_by_symbol.items():
            closes_by_symbol[sym] = [float(b.close) for b in sorted(bars, key=lambda x: x.timestamp)]

        for sector, members in sector_groups.items():
            if len(members) < 2:
                continue

            # Build returns for each member
            member_returns: dict[str, list[float]] = {}
            for inst in members:
                closes = closes_by_symbol.get(inst.symbol)
                if closes is None or len(closes) < 3:
                    continue
                rets = _returns(closes)
                if len(rets) < 2:
                    continue
                member_returns[inst.symbol] = rets

            if len(member_returns) < 2:
                continue

            # Equal-weighted sector return series (aligned by day count)
            min_len = min(len(r) for r in member_returns.values())
            aligned_rets: dict[str, list[float]] = {
                sym: r[-min_len:] for sym, r in member_returns.items()
            }
            sector_return_series: list[float] = []
            for i in range(min_len):
                day_sum = sum(aligned_rets[sym][i] for sym in aligned_rets)
                sector_return_series.append(day_sum / len(aligned_rets))

            # Today's sector return
            today_sector_ret = sector_return_series[-1]
            if abs(today_sector_ret * 100) < self._config.min_sector_move_pct:
                continue

            # Today's member returns
            today_member_rets: dict[str, float] = {
                sym: aligned_rets[sym][-1] for sym in aligned_rets
            }
            all_today_rets = list(today_member_rets.values())

            # Check each member for divergence
            for inst in members:
                sym = inst.symbol
                if sym not in today_member_rets:
                    continue
                today_ret = today_member_rets[sym]

                # Beta check
                beta_val = _beta(aligned_rets[sym], sector_return_series)
                if beta_val is None or abs(beta_val) < self._config.min_beta:
                    continue

                percentile = _percentile_rank(today_ret, all_today_rets)
                p_low = self._config.percentile_urgent
                p_notable = self._config.percentile_notable

                is_low = percentile <= p_low
                is_high = percentile >= 100 - p_low
                is_notable_low = percentile <= p_notable
                is_notable_high = percentile >= 100 - p_notable

                if not (is_notable_low or is_notable_high):
                    continue

                urgent = is_low or is_high
                direction = "落后" if is_notable_low else "领先"
                severity = InsightSeverity.URGENT if urgent else InsightSeverity.NOTABLE

                confidence = self._compute_confidence(percentile, beta_val, urgent)

                evidence = self._build_evidence(
                    symbol=sym,
                    sector=sector,
                    today_ret=today_ret,
                    today_sector_ret=today_sector_ret,
                    percentile=percentile,
                    members_count=len(members),
                    beta=beta_val,
                    aligned_rets=aligned_rets[sym],
                    sector_return_series=sector_return_series,
                    triggered_at=triggered_at,
                )

                headline = (
                    f"{sym} 在 {sector} 中{direction} "
                    f"(今日收益 {today_ret * 100:+.2f}%, "
                    f"行业 {today_sector_ret * 100:+.2f}%, "
                    f"百分位 {percentile:.0f})"
                )

                out.append(
                    Insight(
                        id=_stable_id(sym, sector, as_of),
                        kind=InsightKind.SECTOR_DIVERGENCE,
                        severity=severity,
                        headline=headline,
                        subjects=[sym, sector],
                        causal_chain=evidence,
                        confidence=round(confidence, 4),
                        triggered_at=triggered_at,
                        expires_at=triggered_at + timedelta(hours=self._config.expires_hours),
                    )
                )

        return out

    def _compute_confidence(
        self,
        percentile: float,
        beta: float,
        urgent: bool,
    ) -> float:
        """Combine percentile extremity + beta strength into confidence 0–1."""
        # How extreme: distance from 50th percentile, normalised to [0, 1]
        extremity = abs(percentile - 50.0) / 50.0  # 0 at 50th, 1 at 0th/100th
        # Beta strength: abs(beta) capped at 2.0, scaled to [0, 1]
        beta_strength = min(abs(beta) / 2.0, 1.0)
        c = 0.4 * extremity + 0.4 * beta_strength
        if urgent:
            c += 0.2
        return min(c, 1.0)

    def _build_evidence(
        self,
        *,
        symbol: str,
        sector: str,
        today_ret: float,
        today_sector_ret: float,
        percentile: float,
        members_count: int,
        beta: float,
        aligned_rets: list[float],
        sector_return_series: list[float],
        triggered_at: datetime,
    ) -> list[InsightEvidence]:
        # Evidence 1: sector context
        ev1 = InsightEvidence(
            source=f"sector_map:{sector}",
            fact=(
                f"{sector} 今日等权平均收益 {today_sector_ret * 100:+.2f}%"
                f"(共 {members_count} 只成分)"
            ),
            value={
                "sector": sector,
                "sector_return": round(today_sector_ret, 6),
                "members_count": members_count,
                "min_move_pct": self._config.min_sector_move_pct,
            },
            observed_at=triggered_at,
        )

        # Evidence 2: instrument percentile
        ev2 = InsightEvidence(
            source=f"market_data:{symbol}",
            fact=(
                f"{symbol} 今日收益 {today_ret * 100:+.2f}%, "
                f"在 {sector} 中位于第 {percentile:.1f} 百分位"
            ),
            value={
                "symbol": symbol,
                "asset_return": round(today_ret, 6),
                "percentile": round(percentile, 2),
                "percentile_notable": self._config.percentile_notable,
                "percentile_urgent": self._config.percentile_urgent,
            },
            observed_at=triggered_at,
        )

        # Evidence 3: historical beta
        ev3 = InsightEvidence(
            source="insight_engine:beta",
            fact=(
                f"{symbol} 对 {sector} 的过去 "
                f"{self._config.deviation_window} 日 beta = {beta:.3f}"
            ),
            value={
                "beta": round(beta, 4),
                "window_days": self._config.deviation_window,
                "min_beta": self._config.min_beta,
            },
            observed_at=triggered_at,
        )

        # Evidence 4: historical divergence frequency
        freq = self._historical_divergence_freq(
            aligned_rets, sector_return_series, percentile
        )
        ev4 = InsightEvidence(
            source="insight_engine:history",
            fact=(
                f"过去 {len(aligned_rets)} 日中, "
                f"{symbol} 处于 ±{self._config.percentile_notable:.0f}% 百分位之外的频率为 "
                f"{freq['ratio']:.1%}"
            ),
            value={
                "freq_ratio": round(freq["ratio"], 4),
                "freq_count": freq["count"],
                "total_days": freq["total"],
            },
            observed_at=triggered_at,
        )

        return [ev1, ev2, ev3, ev4]

    def _historical_divergence_freq(
        self,
        asset_rets: list[float],
        sector_rets: list[float],
        current_percentile: float,  # noqa: ARG002
    ) -> dict:
        """Count how often the asset fell in the outer percentile bands historically."""
        if len(asset_rets) < 2 or len(asset_rets) != len(sector_rets):
            return {"ratio": 0.0, "count": 0, "total": 0}
        total = len(asset_rets)
        diffs = [a - s for a, s in zip(asset_rets, sector_rets, strict=False)]
        if not diffs:
            return {"ratio": 0.0, "count": 0, "total": 0}
        mu = mean(diffs)
        sigma = pstdev(diffs) if len(diffs) > 1 else 1.0
        if sigma <= 1e-12:
            return {"ratio": 0.0, "count": 0, "total": total}
        count = sum(1 for d in diffs if abs((d - mu) / sigma) > 1.0)
        return {"ratio": count / total if total else 0.0, "count": count, "total": total}

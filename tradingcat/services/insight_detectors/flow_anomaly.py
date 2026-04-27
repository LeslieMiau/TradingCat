"""Detect anomalous market-level fund flow events.

v1 spec §3.3 simplification: per-stock and per-sector flow data require
premium feeds (Wind / Choice / Futu pro). v1 ships *market-level z-score*
of northbound (CN) and southbound (HK) flow series, with the user's own
holdings/watchlist for that market as the insight subjects.

When the upstream series has < ``min_history_days`` entries, the detector
silently returns no insights for that market — preserving the "graceful
degradation when data is missing" rule from spec §2.4.

Trigger:
- Series for a market has ≥ ``min_history_days`` past entries
- Today's z-score (vs past series) ≥ ``z_notable``
- z-score ≥ ``z_urgent`` → severity = urgent

Intended hookup at Round 4: bridge ``MarketSentimentHistoryRepository``
into a per-market series provider. Round 3 ships the detector + tests; the
engine integration uses any provider callable so existing tests stay pure.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import mean, pstdev

from tradingcat.domain.models import (
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    Instrument,
    Market,
)


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FlowAnomalyConfig:
    min_history_days: int = 30
    z_notable: float = 2.5
    z_urgent: float = 3.0
    expires_hours: int = 36


# Indicator key used for the stable Insight id and headline labelling.
# Future per-sector / per-stock variants can use distinct indicator keys.
INDICATOR_NORTHBOUND = "cn_northbound_net_5d_bn"
INDICATOR_SOUTHBOUND = "hk_southbound_net_5d_bn"


_MARKET_INDICATORS: dict[Market, str] = {
    Market.CN: INDICATOR_NORTHBOUND,
    Market.HK: INDICATOR_SOUTHBOUND,
}


def _zscore(sample: list[float], today: float) -> tuple[float, float, float] | None:
    if len(sample) < 10:
        return None
    mu = mean(sample)
    sigma = pstdev(sample)
    if sigma <= 1e-12:
        return None
    return (today - mu) / sigma, mu, sigma


def _stable_id(market: Market, indicator: str, as_of: date) -> str:
    raw = f"flow_anomaly:{market.value}:{indicator}:{as_of.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


class FlowAnomalyDetector:
    """Pure-data detector. Engine supplies pre-fetched flow series."""

    def __init__(self, config: FlowAnomalyConfig | None = None) -> None:
        self._config = config or FlowAnomalyConfig()

    @property
    def config(self) -> FlowAnomalyConfig:
        return self._config

    def detect(
        self,
        *,
        as_of: date,
        watchlist: list[Instrument],
        flow_series_by_market: dict[Market, list[float]],
        now: datetime | None = None,
    ) -> list[Insight]:
        triggered_at = now or datetime.now(timezone.utc)
        out: list[Insight] = []
        for market, indicator in _MARKET_INDICATORS.items():
            series = flow_series_by_market.get(market) or []
            insight = self._detect_one(
                market=market,
                indicator=indicator,
                series=series,
                watchlist=watchlist,
                as_of=as_of,
                triggered_at=triggered_at,
            )
            if insight is not None:
                out.append(insight)
        return out

    def _detect_one(
        self,
        *,
        market: Market,
        indicator: str,
        series: list[float],
        watchlist: list[Instrument],
        as_of: date,
        triggered_at: datetime,
    ) -> Insight | None:
        if len(series) < self._config.min_history_days + 1:
            return None
        sample = series[:-1][-self._config.min_history_days * 3 :]
        # Use up to 90 days of past readings; cap to avoid stale-regime noise.
        today = series[-1]
        z_result = _zscore(sample, today)
        if z_result is None:
            return None
        z, mu, sigma = z_result
        if abs(z) < self._config.z_notable:
            return None
        urgent = abs(z) >= self._config.z_urgent
        severity = InsightSeverity.URGENT if urgent else InsightSeverity.NOTABLE
        confidence = min(1.0, abs(z) / self._config.z_urgent)

        market_subjects = sorted(
            {inst.symbol for inst in watchlist if inst.market == market}
        )
        if not market_subjects:
            # No holdings/watchlist in that market — flow anomaly is not
            # actionable for the user; suppress per spec §1.2 ("knows your
            # holdings").
            return None

        evidence = self._build_evidence(
            market=market,
            indicator=indicator,
            today=today,
            mu=mu,
            sigma=sigma,
            z=z,
            sample_size=len(sample),
            triggered_at=triggered_at,
        )
        direction = "净流入" if today > 0 else "净流出"
        headline = (
            f"{market.value} 市场资金 {indicator} 当日{direction} "
            f"{today:+.1f},历史 z={z:+.2f},影响 {len(market_subjects)} 个持仓/关注"
        )
        return Insight(
            id=_stable_id(market, indicator, as_of),
            kind=InsightKind.FLOW_ANOMALY,
            severity=severity,
            headline=headline,
            subjects=[market.value, indicator, *market_subjects],
            causal_chain=evidence,
            confidence=round(confidence, 4),
            triggered_at=triggered_at,
            expires_at=triggered_at + timedelta(hours=self._config.expires_hours),
        )

    def _build_evidence(
        self,
        *,
        market: Market,
        indicator: str,
        today: float,
        mu: float,
        sigma: float,
        z: float,
        sample_size: int,
        triggered_at: datetime,
    ) -> list[InsightEvidence]:
        return [
            InsightEvidence(
                source=f"sentiment_history:{market.value}:{indicator}",
                fact=(
                    f"{market.value} {indicator} 今日 = {today:+.2f},"
                    f"过去 {sample_size} 日均值 {mu:+.2f},标准差 {sigma:.2f}"
                ),
                value={
                    "today": round(today, 4),
                    "sample_mean": round(mu, 4),
                    "sample_std": round(sigma, 4),
                    "sample_size": sample_size,
                },
                observed_at=triggered_at,
            ),
            InsightEvidence(
                source="insight_engine:zscore",
                fact=(
                    f"z-score = {z:+.2f}(阈值:notable ≥ {self._config.z_notable}, "
                    f"urgent ≥ {self._config.z_urgent})"
                ),
                value={
                    "z_score": round(z, 4),
                    "z_notable": self._config.z_notable,
                    "z_urgent": self._config.z_urgent,
                },
                observed_at=triggered_at,
            ),
            InsightEvidence(
                source="insight_engine:scope",
                fact=(
                    "v1 范围:市场级流向异常,subjects 限定为该市场的持仓/关注。"
                    "per-sector/per-stock 流向需要 Wind/Choice 等付费源,留给 v2。"
                ),
                value={
                    "scope": "market_level",
                    "v2_planned": ["per_sector", "per_stock"],
                },
                observed_at=triggered_at,
            ),
        ]

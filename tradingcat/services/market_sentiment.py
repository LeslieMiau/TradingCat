"""Sentiment rollup service.

Sits alongside `MarketAwarenessService`. Pulls volatility / fund-flow / fear-
greed observations from external adapters, classifies each into a bucket, and
aggregates into per-market + composite scores. It never raises: per spec §4
(Graceful degradation), any fetcher failure downgrades the indicator and
leaves the remaining aggregation path intact.

Round 1: US view (VIX + VXN + CNN Fear & Greed).
Round 2: CN view (turnover + northbound + margin via eastmoney_http).
Round 3: HK view (^HSIV / realized-vol fallback + southbound) + composite risk switch.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradingcat.adapters.sentiment_sources.cn_market_flows import (
    CNMarketFlowsClient,
    CNMarginReading,
    CNNorthboundReading,
    CNTurnoverReading,
)
from tradingcat.adapters.sentiment_sources.cnn_fear_greed import (
    CNNFearGreedClient,
    CNNFearGreedReading,
)
from tradingcat.adapters.sentiment_sources.hk_southbound import (
    HKSouthboundClient,
    HKSouthboundReading,
)
from tradingcat.config import AppConfig, MarketSentimentConfig
from tradingcat.domain.models import AssetClass, Instrument, Market
from tradingcat.domain.sentiment import (
    MarketSentimentDataQuality,
    MarketSentimentIndicator,
    MarketSentimentSnapshot,
    MarketSentimentView,
    RiskSwitch,
    SentimentStatus,
)
from tradingcat.services.market_data import MarketDataService


logger = logging.getLogger(__name__)


# Per-indicator score contributions (spec §5 "分桶阈值表").
# Kept as module-level constants so tests can assert against exact wiring.
_VIX_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    # (upper_inclusive, status, score)
    (13.0, SentimentStatus.CALM, +0.6),
    (18.0, SentimentStatus.NEUTRAL, +0.2),
    (25.0, SentimentStatus.ELEVATED, -0.2),
    (35.0, SentimentStatus.STRESS, -0.5),
    (None, SentimentStatus.EXTREME_FEAR, -0.8),  # >35 treated as extreme panic
)

_VXN_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    (18.0, SentimentStatus.CALM, +0.5),
    (24.0, SentimentStatus.NEUTRAL, +0.1),
    (32.0, SentimentStatus.ELEVATED, -0.2),
    (None, SentimentStatus.STRESS, -0.5),
)

# CNN F&G is a CONTRARIAN signal: extreme greed → sell; extreme fear → buy.
_CNN_BUCKETS: tuple[tuple[float, SentimentStatus, float], ...] = (
    # (upper_inclusive, status, score)
    (24.0, SentimentStatus.EXTREME_FEAR, +0.6),
    (44.0, SentimentStatus.NEUTRAL, +0.2),   # rated "fear" but small positive lean
    (55.0, SentimentStatus.NEUTRAL, 0.0),
    (75.0, SentimentStatus.ELEVATED, -0.3),  # rated "greed"
    (100.0, SentimentStatus.EXTREME_GREED, -0.6),
)


# HK — Hang Seng Implied Volatility (^HSIV) or realized-vol fallback.
_HSIV_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    (16.0, SentimentStatus.CALM, +0.5),
    (22.0, SentimentStatus.NEUTRAL, +0.1),
    (30.0, SentimentStatus.ELEVATED, -0.2),
    (None, SentimentStatus.STRESS, -0.5),
)


# CN A-share indicators (spec §5 "分桶阈值表" — CN section).
_CN_TURNOVER_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    # Cross-sectional median turnover rate (%).  Higher = more retail-driven
    # speculative activity → risk-negative (overheated).
    (1.5, SentimentStatus.CALM, +0.2),
    (3.0, SentimentStatus.NEUTRAL, 0.0),
    (5.0, SentimentStatus.ELEVATED, -0.2),
    (None, SentimentStatus.STRESS, -0.5),
)

_CN_NORTHBOUND_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    # 5-day net in CNY billions.  Positive = foreign inflow (bullish signal).
    # The bucket table is reversed: we iterate from most-bullish to most-bearish.
    # NOTE: the spec says > +20 → +0.5, -20..+20 → 0, < -20 → -0.5.
    # We cannot reuse _bucket_for_value directly because the ordering is
    # inverted (high value = good).  Handled in _classify_northbound().
)

_CN_MARGIN_BUCKETS: tuple[tuple[float | None, SentimentStatus, float], ...] = (
    # MoM % change.  Rising margin ≈ leveraged speculation → slightly risk-neg.
    # Falling margin ≈ de-leveraging → slightly risk-positive (mean-reversion).
    # Again ordering is inverted (high = bad); handled in _classify_margin().
)


def _classify_northbound(net_5d_bn: float) -> tuple[SentimentStatus, float]:
    """Map northbound 5d net flow (CNY bn) to (status, score)."""
    if net_5d_bn > 20.0:
        return SentimentStatus.CALM, +0.5
    if net_5d_bn >= -20.0:
        return SentimentStatus.NEUTRAL, 0.0
    return SentimentStatus.STRESS, -0.5


def _classify_margin(mom_pct: float) -> tuple[SentimentStatus, float]:
    """Map margin balance MoM % change to (status, score)."""
    if mom_pct > 5.0:
        return SentimentStatus.ELEVATED, -0.2
    if mom_pct >= -5.0:
        return SentimentStatus.NEUTRAL, 0.0
    return SentimentStatus.CALM, +0.3


def _classify_southbound(net_5d_hkd_bn: float) -> tuple[SentimentStatus, float]:
    """Map southbound 5d net flow (HKD bn) to (status, score).

    Positive = mainland buying HK stocks (bullish for HK).
    Ordering is inverted (high value = good), same pattern as northbound.
    """
    if net_5d_hkd_bn > 10.0:
        return SentimentStatus.CALM, +0.5
    if net_5d_hkd_bn >= -10.0:
        return SentimentStatus.NEUTRAL, 0.0
    return SentimentStatus.STRESS, -0.5


def _bucket_for_value(
    value: float,
    buckets: tuple[tuple[float | None, SentimentStatus, float], ...],
) -> tuple[SentimentStatus, float]:
    """Return (status, per-indicator score) for the first bucket matching `value`."""

    for upper, status, score in buckets:
        if upper is None or value <= upper:
            return status, score
    # unreachable — final bucket has upper=None
    last = buckets[-1]
    return last[1], last[2]


@dataclass(slots=True)
class _ViewMeta:
    """Non-payload accounting output from each per-market view builder."""

    sources_failed: list[str]
    stale_sources: list[str]
    adapter_limitations: list[str]
    blockers: list[str]
    any_populated: bool


class MarketSentimentService:
    """Aggregate external sentiment sources into a per-market + composite view.

    Dependencies are injected so tests can swap in `Static*Client` fakes.
    """

    def __init__(
        self,
        config: AppConfig,
        market_data: MarketDataService,
        *,
        cnn_client: CNNFearGreedClient | None = None,
        cn_flows_client: CNMarketFlowsClient | None = None,
        hk_flows_client: HKSouthboundClient | None = None,
    ) -> None:
        self._app_config = config
        self._config: MarketSentimentConfig = config.market_sentiment
        self._market_data = market_data
        self._cnn_client = cnn_client
        self._cn_flows_client = cn_flows_client
        self._hk_flows_client = hk_flows_client
        if self._config.enabled:
            self._seed_volatility_instruments()

    # ------------------------------------------------------------------ public

    def snapshot(self, as_of: date | None = None) -> MarketSentimentSnapshot:
        """Build a sentiment snapshot. Never raises."""

        evaluation_date = as_of or date.today()
        if not self._config.enabled:
            return MarketSentimentSnapshot(
                as_of=evaluation_date,
                views=[
                    self._empty_view(Market.US),
                    self._empty_view(Market.HK),
                    self._empty_view(Market.CN),
                ],
                composite_score=0.0,
                risk_switch=RiskSwitch.UNKNOWN,
                data_quality=MarketSentimentDataQuality(
                    complete=False,
                    degraded=True,
                    adapter_limitations=["market_sentiment_disabled"],
                ),
            )

        try:
            us_view, us_meta = self._build_us_view(evaluation_date)
        except Exception as exc:  # noqa: BLE001 — defense in depth
            logger.exception("market sentiment US view failure: %s", exc)
            us_view = self._empty_view(Market.US)
            us_meta = _ViewMeta(
                sources_failed=["us_sentiment"],
                stale_sources=[],
                adapter_limitations=["us_view_exception"],
                blockers=[],
                any_populated=False,
            )

        # HK view — wired in Round 3.
        try:
            hk_view, hk_meta = self._build_hk_view(evaluation_date)
        except Exception as exc:  # noqa: BLE001 — defense in depth
            logger.exception("market sentiment HK view failure: %s", exc)
            hk_view = self._empty_view(Market.HK)
            hk_meta = _ViewMeta(
                sources_failed=["hk_sentiment"],
                stale_sources=[],
                adapter_limitations=["hk_view_exception"],
                blockers=[],
                any_populated=False,
            )

        # CN view — wired in Round 2.
        try:
            cn_view, cn_meta = self._build_cn_view()
        except Exception as exc:  # noqa: BLE001 — defense in depth
            logger.exception("market sentiment CN view failure: %s", exc)
            cn_view = self._empty_view(Market.CN)
            cn_meta = _ViewMeta(
                sources_failed=["cn_sentiment"],
                stale_sources=[],
                adapter_limitations=["cn_view_exception"],
                blockers=[],
                any_populated=False,
            )

        views = [us_view, hk_view, cn_view]
        composite_score = self._compute_composite_score(views)
        risk_switch = self._classify_risk_switch(composite_score, us_view, views)

        data_quality = self._build_data_quality([us_meta, hk_meta, cn_meta], views)

        return MarketSentimentSnapshot(
            as_of=evaluation_date,
            views=views,
            composite_score=composite_score,
            risk_switch=risk_switch,
            data_quality=data_quality,
        )

    # ------------------------------------------------------------------ US view

    def _build_us_view(self, as_of: date) -> tuple[MarketSentimentView, _ViewMeta]:
        indicators: list[MarketSentimentIndicator] = []
        meta = _ViewMeta(
            sources_failed=[],
            stale_sources=[],
            adapter_limitations=[],
            blockers=[],
            any_populated=False,
        )

        vix_indicator = self._fetch_volatility_indicator(
            symbol=self._config.us_vix_symbol,
            key="us_vix",
            label="CBOE VIX",
            market=Market.US,
            buckets=_VIX_BUCKETS,
            as_of=as_of,
            meta=meta,
        )
        indicators.append(vix_indicator)

        vxn_indicator = self._fetch_volatility_indicator(
            symbol=self._config.us_vxn_symbol,
            key="us_vxn",
            label="CBOE VXN (Nasdaq Vol)",
            market=Market.US,
            buckets=_VXN_BUCKETS,
            as_of=as_of,
            meta=meta,
        )
        indicators.append(vxn_indicator)

        cnn_indicator = self._fetch_cnn_indicator(meta=meta)
        indicators.append(cnn_indicator)

        score = self._aggregate_us_score(vix_indicator, vxn_indicator, cnn_indicator)
        status = self._classify_market_status(score, indicators)

        notes: list[str] = []
        if vix_indicator.stale and not meta.any_populated:
            notes.append("US sentiment unavailable; downstream scoring is neutralised.")

        view = MarketSentimentView(
            market=Market.US,
            score=score,
            status=status,
            indicators=indicators,
            notes=notes,
        )
        return view, meta

    def _fetch_volatility_indicator(
        self,
        *,
        symbol: str,
        key: str,
        label: str,
        market: Market,
        buckets: tuple[tuple[float | None, SentimentStatus, float], ...],
        as_of: date,
        meta: _ViewMeta,
    ) -> MarketSentimentIndicator:
        start = as_of - timedelta(days=60)
        value: float | None = None
        value_ts: datetime | None = None
        stale = False
        try:
            history = self._market_data.ensure_history([symbol], start, as_of)
            bars = history.get(symbol) or []
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: %s ensure_history failed: %s", symbol, exc)
            bars = []
            meta.adapter_limitations.append(f"{key}_adapter_error")

        if bars:
            latest = max(bars, key=lambda bar: bar.timestamp)
            value = float(latest.close)
            value_ts = latest.timestamp
            stale_cutoff = as_of - timedelta(days=self._config.vol_stale_after_days)
            if latest.timestamp.date() < stale_cutoff:
                stale = True
                meta.stale_sources.append(key)
            else:
                meta.any_populated = True
        else:
            stale = True
            meta.sources_failed.append(key)

        if value is None:
            return MarketSentimentIndicator(
                key=key,
                label=label,
                market=market.value,
                value=None,
                unit="%",
                status=SentimentStatus.UNKNOWN,
                score=0.0,
                as_of_ts=None,
                source="yfinance",
                stale=True,
                notes=["Source returned no bars"],
            )

        status, score = _bucket_for_value(value, buckets)
        return MarketSentimentIndicator(
            key=key,
            label=label,
            market=market.value,
            value=round(value, 4),
            unit="%",
            status=status,
            score=round(score, 4),
            as_of_ts=value_ts,
            source="yfinance",
            stale=stale,
            notes=["Stale reading"] if stale else [],
        )

    def _fetch_cnn_indicator(self, *, meta: _ViewMeta) -> MarketSentimentIndicator:
        key = "us_cnn_fng"
        label = "CNN Fear & Greed"
        if not self._config.cnn_enabled:
            meta.adapter_limitations.append("cnn_fear_greed_disabled")
            return MarketSentimentIndicator(
                key=key,
                label=label,
                market=Market.US.value,
                value=None,
                status=SentimentStatus.UNKNOWN,
                score=0.0,
                source="cnn",
                stale=True,
                notes=["CNN Fear & Greed disabled via config"],
            )
        if self._cnn_client is None:
            meta.adapter_limitations.append("cnn_client_missing")
            return MarketSentimentIndicator(
                key=key,
                label=label,
                market=Market.US.value,
                value=None,
                status=SentimentStatus.UNKNOWN,
                score=0.0,
                source="cnn",
                stale=True,
                notes=["CNN client not wired"],
            )

        reading: CNNFearGreedReading | None
        try:
            reading = self._cnn_client.fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: CNN F&G fetch raised: %s", exc)
            reading = None
            meta.adapter_limitations.append("cnn_fetch_exception")

        if reading is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key,
                label=label,
                market=Market.US.value,
                value=None,
                status=SentimentStatus.UNKNOWN,
                score=0.0,
                source="cnn",
                stale=True,
                notes=["Upstream returned None"],
            )

        status, score = _bucket_for_value(reading.value, _CNN_BUCKETS)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key,
            label=label,
            market=Market.US.value,
            value=round(reading.value, 4),
            unit="score_0_100",
            status=status,
            score=round(score, 4),
            as_of_ts=reading.fetched_at,
            source="cnn",
            stale=False,
            notes=[f"CNN rating: {reading.rating}"],
        )

    @staticmethod
    def _aggregate_us_score(
        vix: MarketSentimentIndicator,
        vxn: MarketSentimentIndicator,
        cnn: MarketSentimentIndicator,
    ) -> float:
        weighted = 0.0
        total_weight = 0.0
        for weight, indicator in (
            (0.50, vix),
            (0.25, vxn),
            (0.25, cnn),
        ):
            if indicator.value is None or indicator.status == SentimentStatus.UNKNOWN:
                continue
            weighted += weight * indicator.score
            total_weight += weight
        if total_weight == 0.0:
            return 0.0
        return round(max(-1.0, min(1.0, weighted / total_weight)), 4)

    # ------------------------------------------------------------------ CN view

    def _build_cn_view(self) -> tuple[MarketSentimentView, _ViewMeta]:
        """Build the A-share sentiment view from turnover/northbound/margin."""

        indicators: list[MarketSentimentIndicator] = []
        meta = _ViewMeta(
            sources_failed=[],
            stale_sources=[],
            adapter_limitations=[],
            blockers=[],
            any_populated=False,
        )

        if self._config.cn_backend == "disabled":
            meta.adapter_limitations.append("cn_sentiment_disabled")
            return self._empty_view(Market.CN), meta

        if self._cn_flows_client is None:
            meta.adapter_limitations.append("cn_flows_client_missing")
            return self._empty_view(Market.CN), meta

        turnover_ind = self._fetch_cn_turnover_indicator(meta)
        indicators.append(turnover_ind)

        northbound_ind = self._fetch_cn_northbound_indicator(meta)
        indicators.append(northbound_ind)

        margin_ind = self._fetch_cn_margin_indicator(meta)
        indicators.append(margin_ind)

        score = self._aggregate_cn_score(turnover_ind, northbound_ind, margin_ind)
        status = self._classify_market_status(score, indicators)

        notes: list[str] = []
        if not meta.any_populated:
            notes.append("CN sentiment unavailable; downstream scoring is neutralised.")

        view = MarketSentimentView(
            market=Market.CN,
            score=score,
            status=status,
            indicators=indicators,
            notes=notes,
        )
        return view, meta

    def _fetch_cn_turnover_indicator(self, meta: _ViewMeta) -> MarketSentimentIndicator:
        key = "cn_turnover"
        label = "A-share median turnover"
        reading: CNTurnoverReading | None = None
        try:
            reading = self._cn_flows_client.fetch_turnover()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: CN turnover fetch raised: %s", exc)
            meta.adapter_limitations.append("cn_turnover_exception")

        if reading is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.CN.value,
                value=None, unit="%", status=SentimentStatus.UNKNOWN,
                score=0.0, source="eastmoney", stale=True,
                notes=["Turnover source unavailable"],
            )

        status, score = _bucket_for_value(reading.median_pct, _CN_TURNOVER_BUCKETS)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key, label=label, market=Market.CN.value,
            value=round(reading.median_pct, 4), unit="%",
            status=status, score=round(score, 4),
            as_of_ts=reading.fetched_at, source="eastmoney", stale=False,
            notes=[f"Sample: {reading.sample_size} stocks"],
        )

    def _fetch_cn_northbound_indicator(self, meta: _ViewMeta) -> MarketSentimentIndicator:
        key = "cn_northbound"
        label = "Northbound 5d net"
        reading: CNNorthboundReading | None = None
        try:
            reading = self._cn_flows_client.fetch_northbound()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: CN northbound fetch raised: %s", exc)
            meta.adapter_limitations.append("cn_northbound_exception")

        if reading is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.CN.value,
                value=None, unit="CNY_bn", status=SentimentStatus.UNKNOWN,
                score=0.0, source="eastmoney", stale=True,
                notes=["Northbound source unavailable"],
            )

        status, score = _classify_northbound(reading.net_5d_bn)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key, label=label, market=Market.CN.value,
            value=round(reading.net_5d_bn, 4), unit="CNY_bn",
            status=status, score=round(score, 4),
            as_of_ts=reading.fetched_at, source="eastmoney", stale=False,
            notes=[f"5d window: {self._config.cn_northbound_window_days}d"],
        )

    def _fetch_cn_margin_indicator(self, meta: _ViewMeta) -> MarketSentimentIndicator:
        key = "cn_margin"
        label = "Margin balance MoM"
        reading: CNMarginReading | None = None
        try:
            reading = self._cn_flows_client.fetch_margin_balance()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: CN margin fetch raised: %s", exc)
            meta.adapter_limitations.append("cn_margin_exception")

        if reading is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.CN.value,
                value=None, unit="%_mom", status=SentimentStatus.UNKNOWN,
                score=0.0, source="eastmoney", stale=True,
                notes=["Margin source unavailable"],
            )

        status, score = _classify_margin(reading.mom_pct)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key, label=label, market=Market.CN.value,
            value=round(reading.mom_pct, 4), unit="%_mom",
            status=status, score=round(score, 4),
            as_of_ts=reading.fetched_at, source="eastmoney", stale=False,
            notes=[],
        )

    @staticmethod
    def _aggregate_cn_score(
        turnover: MarketSentimentIndicator,
        northbound: MarketSentimentIndicator,
        margin: MarketSentimentIndicator,
    ) -> float:
        """Weight: 0.4 turnover + 0.4 northbound + 0.2 margin."""
        weighted = 0.0
        total_weight = 0.0
        for weight, indicator in (
            (0.40, turnover),
            (0.40, northbound),
            (0.20, margin),
        ):
            if indicator.value is None or indicator.status == SentimentStatus.UNKNOWN:
                continue
            weighted += weight * indicator.score
            total_weight += weight
        if total_weight == 0.0:
            return 0.0
        return round(max(-1.0, min(1.0, weighted / total_weight)), 4)

    # ------------------------------------------------------------------ HK view

    def _build_hk_view(self, as_of: date) -> tuple[MarketSentimentView, _ViewMeta]:
        """Build HK sentiment from HSIV (preferred) or realized-vol fallback."""

        indicators: list[MarketSentimentIndicator] = []
        meta = _ViewMeta(
            sources_failed=[],
            stale_sources=[],
            adapter_limitations=[],
            blockers=[],
            any_populated=False,
        )

        vol_indicator = self._fetch_hk_vol_indicator(as_of, meta)
        indicators.append(vol_indicator)

        # Southbound — behind feature flag; returns UNKNOWN stub when disabled.
        sb_indicator = self._fetch_hk_southbound_indicator(meta)
        if sb_indicator is not None:
            indicators.append(sb_indicator)

        score = self._aggregate_hk_score(vol_indicator, sb_indicator)
        status = self._classify_market_status(score, indicators)

        notes: list[str] = []
        if not meta.any_populated:
            notes.append("HK sentiment unavailable; downstream scoring is neutralised.")

        view = MarketSentimentView(
            market=Market.HK,
            score=score,
            status=status,
            indicators=indicators,
            notes=notes,
        )
        return view, meta

    def _fetch_hk_vol_indicator(
        self, as_of: date, meta: _ViewMeta
    ) -> MarketSentimentIndicator:
        """Try ^HSIV first; fall back to 20d realized vol from fallback symbols."""

        key = "hk_vol"
        label = "HK Volatility"
        hsiv_symbol = self._config.hk_hsiv_symbol

        # Primary: try ^HSIV via yfinance.
        hsiv_ind = self._fetch_volatility_indicator(
            symbol=hsiv_symbol,
            key=key,
            label=label,
            market=Market.HK,
            buckets=_HSIV_BUCKETS,
            as_of=as_of,
            meta=meta,
        )
        if hsiv_ind.value is not None:
            hsiv_ind = MarketSentimentIndicator(
                key=hsiv_ind.key,
                label=hsiv_ind.label,
                market=hsiv_ind.market,
                value=hsiv_ind.value,
                unit=hsiv_ind.unit,
                status=hsiv_ind.status,
                score=hsiv_ind.score,
                as_of_ts=hsiv_ind.as_of_ts,
                source="yfinance",
                stale=hsiv_ind.stale,
                notes=hsiv_ind.notes,
            )
            return hsiv_ind

        # Fallback: compute 20d annualized realized vol from fallback symbols.
        meta.adapter_limitations.append("hsiv_unavailable_using_realized_vol_fallback")
        realized_vol = self._compute_realized_vol(as_of, meta)

        if realized_vol is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.HK.value,
                value=None, unit="%", status=SentimentStatus.UNKNOWN,
                score=0.0, source="realized_vol_fallback", stale=True,
                notes=["Both HSIV and realized-vol fallback unavailable"],
            )

        status, score = _bucket_for_value(realized_vol, _HSIV_BUCKETS)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key, label=label, market=Market.HK.value,
            value=round(realized_vol, 4), unit="%",
            status=status, score=round(score, 4),
            as_of_ts=None, source="realized_vol_fallback", stale=False,
            notes=[f"Realized vol from {', '.join(self._config.hk_fallback_symbols)}"],
        )

    def _compute_realized_vol(
        self, as_of: date, meta: _ViewMeta
    ) -> float | None:
        """20-day annualized realized vol from HK fallback symbols (e.g. 0700, 2800)."""

        symbols = self._config.hk_fallback_symbols
        if not symbols:
            return None

        start = as_of - timedelta(days=60)
        try:
            histories = self._market_data.ensure_history(symbols, start, as_of)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: HK fallback history failed: %s", exc)
            meta.adapter_limitations.append("hk_fallback_history_error")
            return None

        all_vols: list[float] = []
        for symbol in symbols:
            bars = histories.get(symbol) or []
            if len(bars) < 21:
                continue
            sorted_bars = sorted(bars, key=lambda b: b.timestamp)
            recent = sorted_bars[-21:]  # 21 bars → 20 returns
            returns: list[float] = []
            for i in range(1, len(recent)):
                prev_close = recent[i - 1].close
                if prev_close > 0:
                    returns.append((recent[i].close - prev_close) / prev_close)
            if len(returns) < 10:
                continue
            mean_r = sum(returns) / len(returns)
            var = sum((r - mean_r) ** 2 for r in returns) / len(returns)
            daily_vol = math.sqrt(var)
            annual_vol = daily_vol * math.sqrt(252) * 100  # annualized, in %
            all_vols.append(annual_vol)

        if not all_vols:
            return None
        return sum(all_vols) / len(all_vols)

    def _fetch_hk_southbound_indicator(
        self, meta: _ViewMeta
    ) -> MarketSentimentIndicator | None:
        """Southbound indicator — behind feature flag, returns None when disabled."""

        key = "hk_southbound"
        label = "HK Southbound 5d net"

        if not self._config.hk_southbound_enabled:
            meta.adapter_limitations.append("hk_southbound_disabled")
            return None

        if self._hk_flows_client is None:
            meta.adapter_limitations.append("hk_southbound_client_missing")
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.HK.value,
                value=None, unit="HKD_bn", status=SentimentStatus.UNKNOWN,
                score=0.0, source="eastmoney", stale=True,
                notes=["Southbound client not wired"],
            )

        reading: HKSouthboundReading | None = None
        try:
            reading = self._hk_flows_client.fetch()
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: HK southbound fetch raised: %s", exc)
            meta.adapter_limitations.append("hk_southbound_exception")

        if reading is None:
            meta.sources_failed.append(key)
            return MarketSentimentIndicator(
                key=key, label=label, market=Market.HK.value,
                value=None, unit="HKD_bn", status=SentimentStatus.UNKNOWN,
                score=0.0, source="eastmoney", stale=True,
                notes=["Southbound source unavailable"],
            )

        status, score = _classify_southbound(reading.net_5d_hkd_bn)
        meta.any_populated = True
        return MarketSentimentIndicator(
            key=key, label=label, market=Market.HK.value,
            value=round(reading.net_5d_hkd_bn, 4), unit="HKD_bn",
            status=status, score=round(score, 4),
            as_of_ts=reading.fetched_at, source="eastmoney", stale=False,
            notes=[f"5d window"],
        )

    @staticmethod
    def _aggregate_hk_score(
        vol: MarketSentimentIndicator,
        southbound: MarketSentimentIndicator | None,
    ) -> float:
        """Weight: 0.7*vol + 0.3*southbound (or 1.0*vol if southbound absent)."""

        weighted = 0.0
        total_weight = 0.0

        if vol.value is not None and vol.status != SentimentStatus.UNKNOWN:
            vol_weight = 0.7 if (southbound is not None and southbound.value is not None) else 1.0
            weighted += vol_weight * vol.score
            total_weight += vol_weight

        if (
            southbound is not None
            and southbound.value is not None
            and southbound.status != SentimentStatus.UNKNOWN
        ):
            weighted += 0.3 * southbound.score
            total_weight += 0.3

        if total_weight == 0.0:
            return 0.0
        return round(max(-1.0, min(1.0, weighted / total_weight)), 4)

    @staticmethod
    def _classify_market_status(
        score: float, indicators: list[MarketSentimentIndicator]
    ) -> SentimentStatus:
        populated = [
            ind for ind in indicators if ind.status != SentimentStatus.UNKNOWN
        ]
        if not populated:
            return SentimentStatus.UNKNOWN
        # Only escalate the market-level status from indicators that represent
        # genuine danger signals (negative score). Contrarian indicators like
        # CNN EXTREME_FEAR (positive score = contrarian buy signal) must NOT
        # propagate their label to the market view, otherwise the two-market
        # STRESS override would fire incorrectly.
        danger_statuses = {
            ind.status
            for ind in populated
            if ind.score < 0
            and ind.status
            in {
                SentimentStatus.EXTREME_FEAR,
                SentimentStatus.STRESS,
                SentimentStatus.EXTREME_GREED,
                SentimentStatus.ELEVATED,
            }
        }
        priorities = [
            SentimentStatus.EXTREME_FEAR,
            SentimentStatus.STRESS,
            SentimentStatus.EXTREME_GREED,
            SentimentStatus.ELEVATED,
        ]
        for priority in priorities:
            if priority in danger_statuses:
                return priority
        if score >= 0.2:
            return SentimentStatus.CALM
        if score <= -0.2:
            return SentimentStatus.ELEVATED
        return SentimentStatus.NEUTRAL

    # ------------------------------------------------------------------ composite

    def _compute_composite_score(self, views: list[MarketSentimentView]) -> float:
        weights_by_market = {
            Market.US: self._config.composite_weight_us,
            Market.CN: self._config.composite_weight_cn,
            Market.HK: self._config.composite_weight_hk,
        }
        total_weight = 0.0
        weighted = 0.0
        for view in views:
            if view.status == SentimentStatus.UNKNOWN:
                continue
            weight = weights_by_market.get(view.market, 0.0)
            if weight <= 0:
                continue
            weighted += weight * view.score
            total_weight += weight
        if total_weight == 0.0:
            return 0.0
        return round(max(-1.0, min(1.0, weighted / total_weight)), 4)

    def _classify_risk_switch(
        self,
        composite_score: float,
        us_view: MarketSentimentView,
        all_views: list[MarketSentimentView],
    ) -> RiskSwitch:
        us_status = us_view.status
        if us_status == SentimentStatus.UNKNOWN:
            # Need at least US to make a switch call.
            active_views = [v for v in all_views if v.status != SentimentStatus.UNKNOWN]
            if not active_views:
                return RiskSwitch.UNKNOWN

        # Overrides: VIX > 30 OR CNN F&G < 10 force at-least-WATCH.
        force_watch = False
        vix = next((ind for ind in us_view.indicators if ind.key == "us_vix"), None)
        if vix is not None and vix.value is not None and vix.value > 30:
            force_watch = True
        cnn = next((ind for ind in us_view.indicators if ind.key == "us_cnn_fng"), None)
        if cnn is not None and cnn.value is not None and cnn.value < 10:
            force_watch = True

        on_threshold = self._config.risk_switch_on_threshold
        off_threshold = self._config.risk_switch_off_threshold

        base: RiskSwitch
        if composite_score >= on_threshold:
            base = RiskSwitch.ON
        elif composite_score <= off_threshold:
            base = RiskSwitch.OFF
        else:
            base = RiskSwitch.WATCH

        if force_watch and base == RiskSwitch.ON:
            base = RiskSwitch.WATCH

        # Two-market STRESS override: if >= 2 populated markets are in STRESS
        # (or worse), force OFF regardless of composite score.
        stress_count = sum(
            1
            for v in all_views
            if v.status in {SentimentStatus.STRESS, SentimentStatus.EXTREME_FEAR}
            and v.status != SentimentStatus.UNKNOWN
        )
        if stress_count >= 2:
            return RiskSwitch.OFF

        return base

    # ------------------------------------------------------------------ helpers

    def _empty_view(self, market: Market) -> MarketSentimentView:
        return MarketSentimentView(
            market=market,
            score=0.0,
            status=SentimentStatus.UNKNOWN,
            indicators=[],
            notes=[],
        )

    def _build_data_quality(
        self,
        metas: list[_ViewMeta],
        views: list[MarketSentimentView],
    ) -> MarketSentimentDataQuality:
        sources_failed: list[str] = []
        stale_sources: list[str] = []
        adapter_limitations: list[str] = []
        blockers: list[str] = []
        any_populated = False
        for meta in metas:
            sources_failed.extend(meta.sources_failed)
            stale_sources.extend(meta.stale_sources)
            adapter_limitations.extend(meta.adapter_limitations)
            blockers.extend(meta.blockers)
            any_populated = any_populated or meta.any_populated
        any_active_view = any(
            view.status != SentimentStatus.UNKNOWN for view in views
        )
        complete = any_active_view and not sources_failed and not stale_sources
        degraded = not any_active_view or bool(sources_failed) or bool(stale_sources)
        fallback_driven = bool(stale_sources) and any_active_view
        return MarketSentimentDataQuality(
            complete=complete,
            degraded=degraded,
            fallback_driven=fallback_driven,
            sources_failed=sorted(set(sources_failed)),
            stale_sources=sorted(set(stale_sources)),
            adapter_limitations=sorted(set(adapter_limitations)),
            blockers=sorted(set(blockers)),
        )

    def _seed_volatility_instruments(self) -> None:
        """Ensure ^VIX, ^VXN, ^HSIV are in the instrument catalog so `ensure_history` can resolve them."""

        instruments = [
            Instrument(
                symbol=self._config.us_vix_symbol,
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="CBOE Volatility Index",
                tradable=False,
                liquidity_bucket="high",
                tags=["sentiment", "volatility_index"],
            ),
            Instrument(
                symbol=self._config.us_vxn_symbol,
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="CBOE Nasdaq Volatility Index",
                tradable=False,
                liquidity_bucket="high",
                tags=["sentiment", "volatility_index"],
            ),
            Instrument(
                symbol=self._config.hk_hsiv_symbol,
                market=Market.HK,
                asset_class=AssetClass.ETF,
                currency="HKD",
                name="Hang Seng Implied Volatility",
                tradable=False,
                liquidity_bucket="high",
                tags=["sentiment", "volatility_index"],
            ),
        ]
        try:
            self._market_data.upsert_instruments(instruments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: failed to seed volatility instruments: %s", exc)

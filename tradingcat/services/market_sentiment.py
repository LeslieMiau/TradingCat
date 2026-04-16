"""Sentiment rollup service.

Sits alongside `MarketAwarenessService`. Pulls volatility / fund-flow / fear-
greed observations from external adapters, classifies each into a bucket, and
aggregates into per-market + composite scores. It never raises: per spec §4
(Graceful degradation), any fetcher failure downgrades the indicator and
leaves the remaining aggregation path intact.

Round 1 scope: **US view only** (VIX + VXN + CNN Fear & Greed). HK/CN views
are placeholders (score=0, status=UNKNOWN) so the Pydantic payload shape stays
stable across rounds — Round 2 wires `_cn_view` and Round 3 wires `_hk_view`
without further API changes.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from tradingcat.adapters.sentiment_sources.cnn_fear_greed import (
    CNNFearGreedClient,
    CNNFearGreedReading,
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

    Dependencies are injected so tests can swap in `Static*Client` fakes. The
    CNN client is the only external fetcher wired in Round 1.
    """

    def __init__(
        self,
        config: AppConfig,
        market_data: MarketDataService,
        *,
        cnn_client: CNNFearGreedClient | None = None,
        cn_flows_client: Any = None,  # Round 2
        hk_flows_client: Any = None,  # Round 3
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

        # Round 1 stubs — replaced in later rounds.
        hk_view = self._empty_view(Market.HK)
        hk_meta = _ViewMeta(
            sources_failed=[],
            stale_sources=[],
            adapter_limitations=["hk_sentiment_not_implemented"],
            blockers=[],
            any_populated=False,
        )
        cn_view = self._empty_view(Market.CN)
        cn_meta = _ViewMeta(
            sources_failed=[],
            stale_sources=[],
            adapter_limitations=["cn_sentiment_not_implemented"],
            blockers=[],
            any_populated=False,
        )

        views = [us_view, hk_view, cn_view]
        composite_score = self._compute_composite_score(views)
        risk_switch = self._classify_risk_switch(composite_score, us_view)

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

    @staticmethod
    def _classify_market_status(
        score: float, indicators: list[MarketSentimentIndicator]
    ) -> SentimentStatus:
        populated = [
            ind for ind in indicators if ind.status != SentimentStatus.UNKNOWN
        ]
        if not populated:
            return SentimentStatus.UNKNOWN
        # Status precedence: if any indicator is in stress/extreme fear, surface it.
        priorities = [
            SentimentStatus.EXTREME_FEAR,
            SentimentStatus.STRESS,
            SentimentStatus.EXTREME_GREED,
            SentimentStatus.ELEVATED,
        ]
        statuses = {ind.status for ind in populated}
        for priority in priorities:
            if priority in statuses:
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
    ) -> RiskSwitch:
        us_score = us_view.score
        us_status = us_view.status
        if us_status == SentimentStatus.UNKNOWN:
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
            return RiskSwitch.WATCH

        # Two-market STRESS override is Round 3 territory; no-op here.
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
        """Ensure ^VIX and ^VXN are in the instrument catalog so `ensure_history` can resolve them."""

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
        ]
        try:
            self._market_data.upsert_instruments(instruments)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sentiment: failed to seed volatility instruments: %s", exc)

"""Domain models for the market sentiment layer.

Sentiment indicators are read-only observations about macro/flow state that
sit ALONGSIDE the existing `MarketAwarenessService` weighted regime score —
they never feed the weighted formula. They surface on their own panel and may
enrich `MarketAwarenessActionItem` text / dedup tags.

Kept out of `tradingcat/domain/models.py` so this feature can evolve without
inflating the already-large shared models module.
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field

from tradingcat.domain.models import Market


class SentimentStatus(str, Enum):
    """Bucket classification shared by every indicator."""

    CALM = "calm"
    NEUTRAL = "neutral"
    ELEVATED = "elevated"
    STRESS = "stress"
    EXTREME_FEAR = "extreme_fear"
    EXTREME_GREED = "extreme_greed"
    UNKNOWN = "unknown"


class RiskSwitch(str, Enum):
    """Cross-market aggregate posture derived from per-market sentiment scores."""

    ON = "on"
    WATCH = "watch"
    OFF = "off"
    UNKNOWN = "unknown"


class MarketSentimentIndicator(BaseModel):
    """A single indicator reading (e.g. VIX close, CNN Fear & Greed score)."""

    key: str
    label: str
    market: str = "overall"
    value: float | None = None
    unit: str | None = None
    status: SentimentStatus = SentimentStatus.UNKNOWN
    score: float = 0.0  # per-indicator score contribution in [-1, +1]
    as_of_ts: datetime | None = None
    source: str = "unknown"
    stale: bool = False
    notes: list[str] = Field(default_factory=list)


class MarketSentimentDataQuality(BaseModel):
    """Mirrors `MarketAwarenessDataQuality` shape for the sentiment layer."""

    complete: bool = True
    degraded: bool = False
    fallback_driven: bool = False
    sources_failed: list[str] = Field(default_factory=list)
    stale_sources: list[str] = Field(default_factory=list)
    adapter_limitations: list[str] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)


class MarketSentimentView(BaseModel):
    """Per-market rollup: the indicators for that market + the market's score/status."""

    market: Market
    score: float = 0.0  # weighted sum of indicator scores, clamped to [-1, +1]
    status: SentimentStatus = SentimentStatus.UNKNOWN
    indicators: list[MarketSentimentIndicator] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class MarketSentimentSnapshot(BaseModel):
    """Top-level sentiment observation for a given evaluation date."""

    as_of: date
    views: list[MarketSentimentView] = Field(default_factory=list)
    composite_score: float = 0.0
    risk_switch: RiskSwitch = RiskSwitch.UNKNOWN
    data_quality: MarketSentimentDataQuality = Field(default_factory=MarketSentimentDataQuality)

    def view_for(self, market: Market) -> MarketSentimentView | None:
        for view in self.views:
            if view.market == market:
                return view
        return None

    def indicator(self, market: Market, key: str) -> MarketSentimentIndicator | None:
        view = self.view_for(market)
        if view is None:
            return None
        for indicator in view.indicators:
            if indicator.key == key:
                return indicator
        return None

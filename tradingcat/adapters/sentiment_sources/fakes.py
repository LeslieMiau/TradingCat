"""Deterministic test doubles for sentiment source clients.

Used by unit + integration tests so no real HTTP is hit. Each fake mirrors the
public API of its production counterpart (`fetch()` signature + return type)
and either returns a pre-configured value or raises a pre-configured error.

Kept in production tree (not under tests/) so both tests/ and dev consoles can
import them without relocating during harness rounds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from tradingcat.adapters.sentiment_sources.cnn_fear_greed import CNNFearGreedReading
from tradingcat.adapters.sentiment_sources.cn_market_flows import (
    CNMarginReading,
    CNNorthboundReading,
    CNTurnoverReading,
)


@dataclass(slots=True)
class StaticCNNFearGreedClient:
    """Returns a fixed reading; optionally raises or returns None."""

    reading: CNNFearGreedReading | None = None
    raise_on_fetch: bool = False

    def fetch(self) -> CNNFearGreedReading | None:
        if self.raise_on_fetch:
            raise RuntimeError("static CNN client configured to raise")
        return self.reading


def make_cnn_reading(value: float, rating: str | None = None) -> CNNFearGreedReading:
    """Convenience builder for test readings."""

    resolved_rating = rating or _rating_for_value(value)
    return CNNFearGreedReading(
        value=float(value),
        rating=resolved_rating,
        fetched_at=datetime.now(UTC),
    )


def _rating_for_value(value: float) -> str:
    if value <= 24:
        return "extreme_fear"
    if value <= 44:
        return "fear"
    if value <= 55:
        return "neutral"
    if value <= 75:
        return "greed"
    return "extreme_greed"


# ---------------------------------------------------------------------- CN flows


@dataclass(slots=True)
class StaticCNMarketFlowsClient:
    """Returns pre-configured readings for turnover/northbound/margin.

    Each method has its own value + raise flag so tests can selectively fail
    individual sources.
    """

    turnover: CNTurnoverReading | None = None
    northbound: CNNorthboundReading | None = None
    margin: CNMarginReading | None = None
    raise_on_turnover: bool = False
    raise_on_northbound: bool = False
    raise_on_margin: bool = False

    def fetch_turnover(self) -> CNTurnoverReading | None:
        if self.raise_on_turnover:
            raise RuntimeError("static CN client: turnover boom")
        return self.turnover

    def fetch_northbound(self) -> CNNorthboundReading | None:
        if self.raise_on_northbound:
            raise RuntimeError("static CN client: northbound boom")
        return self.northbound

    def fetch_margin_balance(self) -> CNMarginReading | None:
        if self.raise_on_margin:
            raise RuntimeError("static CN client: margin boom")
        return self.margin


def make_cn_turnover_reading(
    median_pct: float, sample_size: int = 500
) -> CNTurnoverReading:
    """Convenience builder for test turnover readings."""
    return CNTurnoverReading(
        median_pct=float(median_pct),
        sample_size=sample_size,
        fetched_at=datetime.now(UTC),
    )


def make_cn_northbound_reading(net_5d_bn: float) -> CNNorthboundReading:
    """Convenience builder for test northbound readings."""
    return CNNorthboundReading(
        net_5d_bn=float(net_5d_bn),
        fetched_at=datetime.now(UTC),
    )


def make_cn_margin_reading(mom_pct: float) -> CNMarginReading:
    """Convenience builder for test margin readings."""
    return CNMarginReading(
        mom_pct=float(mom_pct),
        fetched_at=datetime.now(UTC),
    )

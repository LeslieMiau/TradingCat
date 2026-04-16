"""Deterministic test doubles for sentiment source clients.

Used by unit + integration tests so no real HTTP is hit. Each fake mirrors the
public API of its production counterpart (`fetch()` signature + return type)
and either returns a pre-configured value or raises a pre-configured error.

Kept in production tree (not under tests/) so both tests/ and dev consoles can
import them without relocating during harness rounds.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from tradingcat.adapters.sentiment_sources.cnn_fear_greed import CNNFearGreedReading


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

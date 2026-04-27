"""Detectors that turn raw market data into Insight events.

Each detector exposes ``detect(as_of, watchlist) -> list[Insight]`` and is
free to inject any service it needs (market data, awareness, sentiment).

Round 1 ships ``correlation_break``. ``sector_divergence`` (Round 2) and
``flow_anomaly`` (Round 3) follow the same shape.
"""
from tradingcat.services.insight_detectors.correlation_break import (
    CorrelationBreakDetector,
)
from tradingcat.services.insight_detectors.sector_divergence import (
    SectorDivergenceDetector,
)


__all__ = ["CorrelationBreakDetector", "SectorDivergenceDetector"]

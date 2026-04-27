"""Detectors that turn raw market data / news into Insight events.

Each detector exposes ``detect(...)`` returning ``list[Insight]`` and is
free to inject any service it needs (market data, awareness, sentiment,
news observation).

v1 ships:
- ``correlation_break``  (Round 1)
- ``sector_divergence``  (Round 2)
- ``flow_anomaly``       (Round 3)
- ``news_driven``        (post-v1 bonus — promoted from v2 backlog)
"""
from tradingcat.services.insight_detectors.correlation_break import (
    CorrelationBreakDetector,
)
from tradingcat.services.insight_detectors.flow_anomaly import (
    FlowAnomalyDetector,
)
from tradingcat.services.insight_detectors.news_driven import (
    NewsDrivenDetector,
)
from tradingcat.services.insight_detectors.sector_divergence import (
    SectorDivergenceDetector,
)


__all__ = [
    "CorrelationBreakDetector",
    "FlowAnomalyDetector",
    "NewsDrivenDetector",
    "SectorDivergenceDetector",
]

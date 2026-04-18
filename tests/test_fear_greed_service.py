from tradingcat.domain.models import (
    MarketAwarenessAshareIndices,
    MarketAwarenessNewsObservation,
    MarketAwarenessSignalStatus,
)
from tradingcat.services.fear_greed import FearGreedToolService


def test_fear_greed_tool_maps_constructive_fear_and_mixed_states():
    service = FearGreedToolService()

    constructive = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=0.55, tone=MarketAwarenessSignalStatus.SUPPORTIVE, explanation="indices strong"),
        news_observation=MarketAwarenessNewsObservation(score=0.3, tone=MarketAwarenessSignalStatus.SUPPORTIVE, explanation="news supportive"),
        cross_asset_score=0.25,
    )
    fearful = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=-0.6, tone=MarketAwarenessSignalStatus.WARNING, explanation="indices weak"),
        news_observation=MarketAwarenessNewsObservation(score=-0.4, tone=MarketAwarenessSignalStatus.WARNING, explanation="news weak"),
        cross_asset_score=-0.35,
    )
    mixed = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=0.05, tone=MarketAwarenessSignalStatus.MIXED, explanation="indices mixed"),
        news_observation=MarketAwarenessNewsObservation(score=-0.05, tone=MarketAwarenessSignalStatus.MIXED, explanation="news mixed"),
        cross_asset_score=0.0,
    )

    assert constructive.band == "constructive"
    assert fearful.band == "fear"
    assert mixed.band == "neutral"
    assert len(constructive.contributors) == 3
    assert "Score" in constructive.explanation

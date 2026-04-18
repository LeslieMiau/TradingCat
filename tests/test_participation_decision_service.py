from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    MarketAwarenessAshareIndices,
    MarketAwarenessFearGreed,
    MarketAwarenessNewsObservation,
    MarketAwarenessSentimentBand,
    MarketAwarenessSignalStatus,
    MarketAwarenessVolumePrice,
)
from tradingcat.services.participation_decision import ParticipationDecisionService


def test_participation_decision_service_covers_participate_selective_wait_and_avoid():
    service = ParticipationDecisionService(AppConfig())

    participate = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=0.8, tone=MarketAwarenessSignalStatus.SUPPORTIVE),
        news_observation=MarketAwarenessNewsObservation(score=0.3, tone=MarketAwarenessSignalStatus.SUPPORTIVE),
        fear_greed=MarketAwarenessFearGreed(score=0.35, band=MarketAwarenessSentimentBand.CONSTRUCTIVE),
        volume_price=MarketAwarenessVolumePrice(score=0.45, state="price_up_volume_up"),
    )
    selective = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=0.35, tone=MarketAwarenessSignalStatus.SUPPORTIVE),
        news_observation=MarketAwarenessNewsObservation(score=0.1, tone=MarketAwarenessSignalStatus.MIXED),
        fear_greed=MarketAwarenessFearGreed(score=0.15, band=MarketAwarenessSentimentBand.CONSTRUCTIVE),
        volume_price=MarketAwarenessVolumePrice(score=0.2, state="repair"),
    )
    wait = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=0.15, tone=MarketAwarenessSignalStatus.MIXED),
        news_observation=MarketAwarenessNewsObservation(score=0.0, tone=MarketAwarenessSignalStatus.MIXED),
        fear_greed=MarketAwarenessFearGreed(score=0.05, band=MarketAwarenessSentimentBand.NEUTRAL),
        volume_price=MarketAwarenessVolumePrice(score=0.05, state="divergence"),
    )
    avoid = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(score=-0.5, tone=MarketAwarenessSignalStatus.WARNING),
        news_observation=MarketAwarenessNewsObservation(score=-0.2, tone=MarketAwarenessSignalStatus.WARNING),
        fear_greed=MarketAwarenessFearGreed(score=-0.3, band=MarketAwarenessSentimentBand.FEAR),
        volume_price=MarketAwarenessVolumePrice(score=-0.35, state="price_down_volume_up"),
    )

    assert participate.decision == "participate"
    assert selective.decision == "selective"
    assert wait.decision == "wait"
    assert avoid.decision == "avoid"
    assert participate.reasons
    assert avoid.reasons


def test_participation_decision_service_caps_degraded_inputs_to_wait():
    service = ParticipationDecisionService(AppConfig())

    degraded = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(
            score=0.8,
            tone=MarketAwarenessSignalStatus.SUPPORTIVE,
            degraded=True,
            blockers=["missing SZ399006"],
        ),
        news_observation=MarketAwarenessNewsObservation(
            score=0.25,
            tone=MarketAwarenessSignalStatus.SUPPORTIVE,
            degraded=True,
            blockers=["macro feed offline"],
        ),
        fear_greed=MarketAwarenessFearGreed(score=0.3, band=MarketAwarenessSentimentBand.CONSTRUCTIVE),
        volume_price=MarketAwarenessVolumePrice(score=0.4, state="price_up_volume_up"),
    )

    assert degraded.decision == "wait"
    assert degraded.confidence == "low"
    assert len(degraded.blockers) == 2
    assert any("capped at wait" in reason for reason in degraded.reasons)


def test_participation_decision_service_keeps_degraded_avoid_reason_consistent():
    service = ParticipationDecisionService(AppConfig())

    degraded = service.observe(
        a_share_indices=MarketAwarenessAshareIndices(
            score=-0.45,
            tone=MarketAwarenessSignalStatus.WARNING,
            degraded=True,
            blockers=["missing SH000001"],
        ),
        news_observation=MarketAwarenessNewsObservation(
            score=-0.2,
            tone=MarketAwarenessSignalStatus.WARNING,
            degraded=True,
            blockers=["macro feed offline"],
        ),
        fear_greed=MarketAwarenessFearGreed(score=-0.25, band=MarketAwarenessSentimentBand.FEAR),
        volume_price=MarketAwarenessVolumePrice(score=-0.3, state="price_down_volume_up"),
    )

    assert degraded.decision == "avoid"
    assert any("decision stays avoid" in reason for reason in degraded.reasons)
    assert not any("capped at wait" in reason for reason in degraded.reasons)

from __future__ import annotations

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    MarketAwarenessAshareIndices,
    MarketAwarenessConfidence,
    MarketAwarenessFearGreed,
    MarketAwarenessNewsObservation,
    MarketAwarenessParticipation,
    MarketAwarenessParticipationDecision,
    MarketAwarenessVolumePrice,
)


class ParticipationDecisionService:
    def __init__(self, config: AppConfig) -> None:
        self._config = config.market_awareness

    def observe(
        self,
        *,
        a_share_indices: MarketAwarenessAshareIndices,
        news_observation: MarketAwarenessNewsObservation,
        fear_greed: MarketAwarenessFearGreed,
        volume_price: MarketAwarenessVolumePrice,
    ) -> MarketAwarenessParticipation:
        blockers = list(news_observation.blockers) + list(a_share_indices.blockers)
        degraded = news_observation.degraded or a_share_indices.degraded
        probability = self._probability(
            a_share_score=a_share_indices.score,
            news_score=news_observation.score,
            fear_greed_score=fear_greed.score,
            volume_price_score=volume_price.score,
        )
        odds = self._odds(
            a_share_score=a_share_indices.score,
            volume_price_score=volume_price.score,
            fear_greed_score=fear_greed.score,
        )
        confidence = self._confidence(degraded, blockers, probability, odds)
        decision = self._decision(probability, odds, degraded)
        reasons = self._reasons(
            decision=decision,
            probability=probability,
            odds=odds,
            fear_greed=fear_greed,
            volume_price=volume_price,
        )
        if degraded:
            reasons.append(
                "Observation quality degraded, so participation is capped at wait."
                if decision == MarketAwarenessParticipationDecision.WAIT
                else "Observation quality degraded and the setup is still too weak, so the decision stays avoid."
            )
        return MarketAwarenessParticipation(
            decision=decision,
            probability=probability,
            odds=odds,
            confidence=confidence,
            reasons=reasons,
            blockers=blockers,
        )

    def _probability(
        self,
        *,
        a_share_score: float,
        news_score: float,
        fear_greed_score: float,
        volume_price_score: float,
    ) -> float:
        raw = 0.5 + (a_share_score * 0.2) + (news_score * 0.1) + (fear_greed_score * 0.1) + (volume_price_score * 0.15)
        return round(min(max(raw, 0.05), 0.95), 4)

    def _odds(
        self,
        *,
        a_share_score: float,
        volume_price_score: float,
        fear_greed_score: float,
    ) -> float:
        raw = 1.0 + (a_share_score * 0.7) + (volume_price_score * 0.6) + (fear_greed_score * 0.35)
        return round(min(max(raw, 0.5), 3.0), 4)

    def _decision(
        self,
        probability: float,
        odds: float,
        degraded: bool,
    ) -> MarketAwarenessParticipationDecision:
        if degraded:
            return (
                MarketAwarenessParticipationDecision.WAIT
                if probability >= 0.45 and odds >= 1.0
                else MarketAwarenessParticipationDecision.AVOID
            )
        if probability >= self._config.participate_probability_threshold and odds >= self._config.participate_odds_threshold:
            return MarketAwarenessParticipationDecision.PARTICIPATE
        if probability >= self._config.selective_probability_threshold and odds >= self._config.selective_odds_threshold:
            return MarketAwarenessParticipationDecision.SELECTIVE
        if probability < 0.45 or odds < 1.0:
            return MarketAwarenessParticipationDecision.AVOID
        return MarketAwarenessParticipationDecision.WAIT

    @staticmethod
    def _confidence(
        degraded: bool,
        blockers: list[str],
        probability: float,
        odds: float,
    ) -> MarketAwarenessConfidence:
        if degraded or blockers:
            return MarketAwarenessConfidence.LOW
        if probability >= 0.65 and odds >= 1.5:
            return MarketAwarenessConfidence.HIGH
        if probability >= 0.5 and odds >= 1.1:
            return MarketAwarenessConfidence.MEDIUM
        return MarketAwarenessConfidence.LOW

    @staticmethod
    def _reasons(
        *,
        decision: MarketAwarenessParticipationDecision,
        probability: float,
        odds: float,
        fear_greed: MarketAwarenessFearGreed,
        volume_price: MarketAwarenessVolumePrice,
    ) -> list[str]:
        reasons = [
            f"Probability {probability:.2f} and odds {odds:.2f}.",
            f"Fear-greed band: {fear_greed.band.value}.",
            f"Volume-price state: {volume_price.state.value}.",
        ]
        if decision == MarketAwarenessParticipationDecision.PARTICIPATE:
            reasons.append("Probability and payoff both clear the participation bar.")
        elif decision == MarketAwarenessParticipationDecision.SELECTIVE:
            reasons.append("Conditions justify selective participation, not broad aggression.")
        elif decision == MarketAwarenessParticipationDecision.AVOID:
            reasons.append("Either win probability or payoff is too weak to justify participation.")
        else:
            reasons.append("Conditions are mixed; waiting preserves optionality.")
        return reasons

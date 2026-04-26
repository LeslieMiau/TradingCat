from __future__ import annotations

from statistics import mean

from tradingcat.domain.models import (
    MarketAwarenessAshareIndices,
    MarketAwarenessContributor,
    MarketAwarenessPriceVolumeState,
    MarketAwarenessVolumePrice,
)


class VolumePriceToolService:
    def observe(self, a_share_indices: MarketAwarenessAshareIndices) -> MarketAwarenessVolumePrice:
        if not a_share_indices.index_views:
            return MarketAwarenessVolumePrice(
                state=MarketAwarenessPriceVolumeState.DIVERGENCE,
                score=0.0,
                explanation="A-share tape observation is unavailable.",
                guidance="Wait until the three-index tape becomes observable again.",
                contributors=[],
            )

        contributors = [
            MarketAwarenessContributor(
                label=view.label,
                score=round(view.score, 4),
                explanation=f"{view.price_volume_state.value}: {view.explanation}",
            )
            for view in a_share_indices.index_views
        ]
        state_counts: dict[MarketAwarenessPriceVolumeState, int] = {}
        for view in a_share_indices.index_views:
            state_counts[view.price_volume_state] = state_counts.get(view.price_volume_state, 0) + 1
        dominant_state = max(state_counts.items(), key=lambda item: item[1])[0]
        score = round(mean([item.score for item in a_share_indices.index_views]), 4)
        if len(state_counts) >= 3 and max(state_counts.values()) == 1:
            dominant_state = MarketAwarenessPriceVolumeState.DIVERGENCE
        explanation = self._explanation(dominant_state, score, a_share_indices.degraded)
        guidance = self._guidance(dominant_state, score)
        return MarketAwarenessVolumePrice(
            state=dominant_state,
            score=score,
            explanation=explanation,
            guidance=guidance,
            contributors=contributors,
        )

    @staticmethod
    def _explanation(
        state: MarketAwarenessPriceVolumeState,
        score: float,
        degraded: bool,
    ) -> str:
        state_text = {
            MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_UP: "The three-index tape is confirming price strength with expanding volume.",
            MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_DOWN: "Prices are rising but participation is thinning.",
            MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_UP: "Weak price action is attracting more volume, which is a clear warning.",
            MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_DOWN: "The tape is weak, though panic participation is not accelerating.",
            MarketAwarenessPriceVolumeState.REPAIR: "The tape is attempting a repair after prior weakness.",
            MarketAwarenessPriceVolumeState.DIVERGENCE: "The three indices are diverging and do not yet confirm each other.",
        }[state]
        degrade_text = " Some index legs degraded." if degraded else ""
        return f"{state_text} 综合评分 {score:.2f}。{degrade_text}"

    @staticmethod
    def _guidance(state: MarketAwarenessPriceVolumeState, score: float) -> str:
        if state == MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_UP and score >= 0.2:
            return "Tape follow-through exists; participation can be considered if odds also hold."
        if state == MarketAwarenessPriceVolumeState.REPAIR:
            return "Treat the move as an early repair, not a confirmed chase."
        if state in {
            MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_UP,
            MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_DOWN,
            MarketAwarenessPriceVolumeState.DIVERGENCE,
        }:
            return "Wait for broader confirmation before adding new risk."
        return "Use patience; the tape is not strong enough for aggressive chasing."

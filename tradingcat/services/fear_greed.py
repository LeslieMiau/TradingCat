from __future__ import annotations

from statistics import mean

from tradingcat.domain.models import (
    MarketAwarenessAshareIndices,
    MarketAwarenessContributor,
    MarketAwarenessFearGreed,
    MarketAwarenessNewsObservation,
    MarketAwarenessSentimentBand,
)


class FearGreedToolService:
    def observe(
        self,
        *,
        a_share_indices: MarketAwarenessAshareIndices,
        news_observation: MarketAwarenessNewsObservation,
        cross_asset_score: float,
    ) -> MarketAwarenessFearGreed:
        contributors = [
            MarketAwarenessContributor(
                label="A股三大指数结构",
                score=round(a_share_indices.score, 4),
                explanation=a_share_indices.explanation,
            ),
            MarketAwarenessContributor(
                label="重点新闻倾向",
                score=round(news_observation.score, 4),
                explanation=news_observation.explanation,
            ),
            MarketAwarenessContributor(
                label="跨资产防御确认",
                score=round(cross_asset_score, 4),
                explanation="Defensive assets weaken the sentiment score when bonds/gold confirm risk aversion.",
            ),
        ]
        score = round(mean([item.score for item in contributors]), 4)
        band = self._band(score)
        explanation = self._explanation(band, score, news_observation.degraded or a_share_indices.degraded)
        return MarketAwarenessFearGreed(
            score=score,
            band=band,
            explanation=explanation,
            contributors=contributors,
        )

    @staticmethod
    def _band(score: float) -> MarketAwarenessSentimentBand:
        if score <= -0.35:
            return MarketAwarenessSentimentBand.FEAR
        if score <= -0.1:
            return MarketAwarenessSentimentBand.CAUTION
        if score < 0.15:
            return MarketAwarenessSentimentBand.NEUTRAL
        if score < 0.4:
            return MarketAwarenessSentimentBand.CONSTRUCTIVE
        return MarketAwarenessSentimentBand.GREED

    @staticmethod
    def _explanation(
        band: MarketAwarenessSentimentBand,
        score: float,
        degraded: bool,
    ) -> str:
        summary = {
            MarketAwarenessSentimentBand.FEAR: "Internal fear-greed sits in fear territory.",
            MarketAwarenessSentimentBand.CAUTION: "Internal fear-greed is cautious.",
            MarketAwarenessSentimentBand.NEUTRAL: "Internal fear-greed is neutral.",
            MarketAwarenessSentimentBand.CONSTRUCTIVE: "Internal fear-greed is constructive.",
            MarketAwarenessSentimentBand.GREED: "Internal fear-greed is extended toward greed.",
        }[band]
        degrade_text = " Confidence is capped because one or more observation legs degraded." if degraded else ""
        return f"{summary} Score {score:.2f}.{degrade_text}"

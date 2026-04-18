from datetime import date

from tradingcat.api.view_models import MarketAwarenessResponse
from tradingcat.domain.models import (
    Market,
    MarketAwarenessActionItem,
    MarketAwarenessActionSeverity,
    MarketAwarenessConfidence,
    MarketAwarenessDataQuality,
    MarketAwarenessDataStatus,
    MarketAwarenessEvidenceRow,
    MarketAwarenessMarketView,
    MarketAwarenessRegime,
    MarketAwarenessRiskPosture,
    MarketAwarenessSignalStatus,
    MarketAwarenessSnapshot,
    MarketAwarenessStrategyGuidance,
    MarketAwarenessStrategyStance,
)


def test_market_awareness_snapshot_serializes_degraded_payload():
    snapshot = MarketAwarenessSnapshot(
        as_of=date(2026, 4, 9),
        overall_regime=MarketAwarenessRegime.CAUTION,
        confidence=MarketAwarenessConfidence.LOW,
        risk_posture=MarketAwarenessRiskPosture.PAUSE_NEW_ADDS,
        overall_score=-0.22,
        market_views=[
            MarketAwarenessMarketView(
                market=Market.US,
                benchmark_symbol="SPY",
                reference_symbols=["QQQ", "VTI"],
                regime=MarketAwarenessRegime.CAUTION,
                confidence=MarketAwarenessConfidence.MEDIUM,
                risk_posture=MarketAwarenessRiskPosture.REDUCE_RISK,
                score=-0.18,
                breadth_ratio=0.42,
                momentum_21d=-0.04,
                drawdown_20d=-0.07,
                realized_volatility_20d=0.031,
                evidence=[
                    MarketAwarenessEvidenceRow(
                        market="US",
                        signal_key="trend_alignment",
                        label="Trend alignment",
                        status=MarketAwarenessSignalStatus.WARNING,
                        value=-0.07,
                        unit="ratio",
                        explanation="SPY slipped below the medium trend window while breadth stayed weak.",
                    )
                ],
            )
        ],
        evidence=[
            MarketAwarenessEvidenceRow(
                market="overall",
                signal_key="cross_asset_confirmation",
                label="Cross-asset confirmation",
                status=MarketAwarenessSignalStatus.MIXED,
                value=0.0,
                unit="score",
                explanation="Defensive assets are improving while equity leadership is fading.",
            )
        ],
        actions=[
            MarketAwarenessActionItem(
                severity=MarketAwarenessActionSeverity.HIGH,
                action_key="pause_new_adds",
                text="Pause new adds until breadth recovers.",
                rationale="The weakest market lens and overall posture both moved into a cautionary state.",
                markets=["US", "HK"],
            )
        ],
        strategy_guidance=[
            MarketAwarenessStrategyGuidance(
                strategy_id="strategy_a_etf_rotation",
                stance=MarketAwarenessStrategyStance.DEFENSIVE,
                summary="Keep broad ETF adds on a short leash.",
                rationale="Trend confirmation is incomplete and breadth fell below the support line.",
                action_key="tighten_rotation_adds",
            )
        ],
        data_quality=MarketAwarenessDataQuality(
            status=MarketAwarenessDataStatus.DEGRADED,
            complete=False,
            degraded=True,
            fallback_driven=True,
            missing_symbols=["9988"],
            stale_windows=["HK:63d_momentum"],
            adapter_limitations=["live_quote_rate_limited"],
            blockers=["HK breadth uses fallback constituents because persisted coverage is incomplete."],
        ),
    )

    payload = snapshot.model_dump(mode="json")

    assert payload["overall_regime"] == "caution"
    assert payload["risk_posture"] == "pause_new_adds"
    assert payload["market_views"][0]["market"] == "US"
    assert payload["market_views"][0]["evidence"][0]["status"] == "warning"
    assert payload["data_quality"]["status"] == "degraded"
    assert payload["data_quality"]["missing_symbols"] == ["9988"]


def test_market_awareness_response_accepts_full_snapshot_payload():
    payload = {
        "as_of": "2026-04-09",
        "overall_regime": "bullish",
        "confidence": "high",
        "risk_posture": "build_risk",
        "overall_score": 0.61,
        "market_views": [
            {
                "market": "CN",
                "benchmark_symbol": "510300",
                "reference_symbols": ["159915"],
                "regime": "bullish",
                "confidence": "high",
                "risk_posture": "build_risk",
                "score": 0.74,
                "breadth_ratio": 0.68,
                "momentum_21d": 0.08,
                "drawdown_20d": -0.01,
                "realized_volatility_20d": 0.015,
                "evidence": [
                    {
                        "market": "CN",
                        "signal_key": "breadth",
                        "label": "Breadth",
                        "status": "supportive",
                        "value": 0.68,
                        "unit": "ratio",
                        "explanation": "Most tracked CN constituents remain above their medium trend filters.",
                    }
                ],
            }
        ],
        "evidence": [],
        "actions": [
            {
                "severity": "medium",
                "action_key": "hold_pace",
                "text": "Build risk gradually instead of all at once.",
                "rationale": "The broad trend is supportive but still concentrated in a few leadership names.",
                "markets": ["CN"],
            }
        ],
        "strategy_guidance": [
            {
                "strategy_id": "strategy_b_equity_momentum",
                "stance": "balanced",
                "summary": "Keep adds selective and require trend confirmation.",
                "rationale": "Momentum is positive but the posture engine still wants breadth confirmation.",
                "action_key": "tighten_entry_filters",
            }
        ],
        "data_quality": {
            "status": "complete",
            "complete": True,
            "degraded": False,
            "fallback_driven": False,
            "missing_symbols": [],
            "stale_windows": [],
            "adapter_limitations": [],
            "blockers": [],
        },
        "news_observation": {
            "score": 0.2,
            "tone": "supportive",
            "dominant_topics": ["policy", "macro"],
            "key_items": [
                {
                    "source": "google_news_cn_market",
                    "title": "A股 政策 发力",
                    "topic": "policy",
                    "tone": "supportive",
                    "importance": 0.8,
                    "published_at": "2026-04-09T09:00:00Z",
                    "url": "https://example.com/cn-policy",
                    "markets": ["CN"],
                    "symbols": [],
                }
            ],
            "degraded": False,
            "blockers": [],
            "explanation": "News flow leans supportive.",
        },
        "a_share_indices": {
            "score": 0.35,
            "tone": "supportive",
            "index_views": [
                {
                    "label": "上证指数",
                    "symbol": "SH000001",
                    "trend_status": "supportive",
                    "price_volume_state": "price_up_volume_up",
                    "score": 0.5,
                    "close": 3300.0,
                    "return_1d": 0.01,
                    "return_5d": 0.03,
                    "return_20d": 0.06,
                    "volume_ratio_20d": 1.2,
                    "above_sma20": True,
                    "above_sma50": True,
                    "above_sma200": True,
                    "explanation": "trend aligned above 20/50/200-day structure",
                }
            ],
            "degraded": False,
            "blockers": [],
            "explanation": "A-share three-index tape is broadly supportive.",
        },
        "fear_greed": {
            "score": 0.25,
            "band": "constructive",
            "explanation": "Internal fear-greed is constructive. Score 0.25.",
            "contributors": [
                {"label": "A股三大指数结构", "score": 0.35, "explanation": "indices supportive"},
                {"label": "重点新闻倾向", "score": 0.2, "explanation": "news supportive"},
            ],
        },
        "volume_price": {
            "state": "price_up_volume_up",
            "score": 0.3,
            "explanation": "The three-index tape is confirming price strength with expanding volume.",
            "guidance": "Tape follow-through exists; participation can be considered if odds also hold.",
            "contributors": [
                {"label": "上证指数", "score": 0.5, "explanation": "价涨量增"},
            ],
        },
        "participation": {
            "decision": "participate",
            "probability": 0.7,
            "odds": 1.8,
            "confidence": "high",
            "reasons": ["Probability 0.70 and odds 1.80."],
            "blockers": [],
        },
    }

    response = MarketAwarenessResponse.model_validate(payload)

    assert response.as_of == date(2026, 4, 9)
    assert response.market_views[0].benchmark_symbol == "510300"
    assert response.actions[0].action_key == "hold_pace"
    assert response.strategy_guidance[0].stance == "balanced"
    assert response.news_observation.key_items[0].source == "google_news_cn_market"
    assert response.a_share_indices.index_views[0].symbol == "SH000001"
    assert response.fear_greed.band == "constructive"
    assert response.volume_price.state == "price_up_volume_up"
    assert response.participation.decision == "participate"

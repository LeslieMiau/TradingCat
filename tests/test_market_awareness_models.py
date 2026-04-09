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
    }

    response = MarketAwarenessResponse.model_validate(payload)

    assert response.as_of == date(2026, 4, 9)
    assert response.market_views[0].benchmark_symbol == "510300"
    assert response.actions[0].action_key == "hold_pace"
    assert response.strategy_guidance[0].stance == "balanced"

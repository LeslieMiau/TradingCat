from __future__ import annotations

from tradingcat.domain.models import Instrument, Market
from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency
from tradingcat.services.universe_screener import UniverseScreener


def _instrument(symbol: str) -> Instrument:
    return Instrument(symbol=symbol, market=Market.CN, currency="CNY", name=symbol)


def test_universe_screener_ranks_multidimensional_candidates():
    instruments = [_instrument("600000"), _instrument("300308")]
    screener = UniverseScreener()

    ranked = screener.screen(
        instruments,
        technical={
            "600000": {"trend_alignment": "mixed", "momentum_state": "negative_momentum", "volume_ratio_20d": 0.8},
            "300308": {"trend_alignment": "bullish_alignment", "momentum_state": "positive_momentum", "volume_ratio_20d": 2.0},
        },
        fundamentals={
            "600000": {"pe": 40, "pb": 5, "roe": 5, "revenue_growth": -3},
            "300308": {"pe": 22, "pb": 2.5, "roe": 18, "revenue_growth": 30},
        },
        news=[
            NewsItem(
                source="cls",
                title="重大 行业 利好 300308",
                symbols=["300308"],
                urgency=NewsUrgency.HIGH,
                event_class=NewsEventClass.INDUSTRY,
                relevance=1.0,
                quality_score=0.9,
            )
        ],
    )

    assert [item.instrument.symbol for item in ranked] == ["300308", "600000"]
    assert ranked[0].score > ranked[1].score
    assert "bullish MA alignment" in ranked[0].reasons
    assert ranked[0].metadata["execution_mode"] == "research_only"


def test_universe_screener_degrades_with_missing_data_and_limits():
    instruments = [_instrument("600000"), _instrument("300308")]
    screener = UniverseScreener(technical_weight=1, fundamental_weight=0, news_weight=0)

    ranked = screener.screen(
        instruments,
        technical={"600000": {"trend_alignment": "bullish_alignment", "momentum_state": "positive_momentum"}},
        limit=1,
    )

    assert len(ranked) == 1
    assert ranked[0].instrument.symbol == "600000"
    assert ranked[0].fundamental_score == 0.4


def test_universe_candidate_as_dict_serializes_instrument():
    candidate = UniverseScreener().screen([_instrument("600000")], limit=1)[0]

    payload = candidate.as_dict()

    assert payload["instrument"]["symbol"] == "600000"
    assert payload["metadata"]["execution_mode"] == "research_only"

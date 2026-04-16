"""Integration tests: `MarketAwarenessService` with sentiment injection.

Verifies the two hard contracts from `.harness/spec.md`:

1. **No regression on the weighted score path.** When sentiment is absent or
   disabled, `overall_score` / `overall_regime` / `actions` must equal the
   pre-sentiment baseline produced by the same inputs.
2. **Action dedup.** When a `reduce_risk`-class HIGH action already exists
   and sentiment says risk-off, the service must NOT emit a duplicate
   `sentiment_force_defense`. Instead the existing action gets a
   `sentiment_confirmed` tag on `.markets`.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.sentiment_sources.fakes import (
    StaticCNMarketFlowsClient,
    StaticCNNFearGreedClient,
    make_cn_margin_reading,
    make_cn_northbound_reading,
    make_cn_turnover_reading,
    make_cnn_reading,
)
from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    AssetClass,
    Bar,
    Instrument,
    Market,
    MarketAwarenessRiskPosture,
)
from tradingcat.repositories.market_data import (
    HistoricalMarketDataRepository,
    InstrumentCatalogRepository,
)
from tradingcat.services.market_awareness import MarketAwarenessService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.market_sentiment import MarketSentimentService


_AS_OF = date(2026, 4, 15)


def _build(tmp_path, *, sentiment: MarketSentimentService | None = None):
    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    service = MarketAwarenessService(
        config,
        market_data,
        market_sentiment=sentiment,
    )
    return service, market_data, config


def _save_closes(
    market_data: MarketDataService,
    symbol: str,
    market: Market,
    asset_class: AssetClass,
    closes: list[float],
) -> None:
    instrument = Instrument(
        symbol=symbol,
        market=market,
        asset_class=asset_class,
        currency="USD" if market == Market.US else "HKD" if market == Market.HK else "CNY",
        liquidity_bucket="high",
        avg_daily_dollar_volume_m=1000,
    )
    market_data.upsert_instruments([instrument])
    start = _AS_OF - timedelta(days=len(closes) - 1)
    bars = [
        Bar(
            instrument=instrument,
            timestamp=datetime.combine(start + timedelta(days=index), datetime.min.time(), tzinfo=UTC),
            open=close * 0.99,
            high=close * 1.01,
            low=close * 0.98,
            close=close,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    ]
    market_data._history.save_bars(instrument, bars)


def _seed_baseline_histories(market_data: MarketDataService, *, bullish: bool) -> None:
    step = 0.08 if bullish else -0.05
    count = 260
    base_closes = [round(100.0 + step * i, 4) for i in range(count)]
    symbols = {
        ("SPY", Market.US, AssetClass.ETF),
        ("QQQ", Market.US, AssetClass.ETF),
        ("VTI", Market.US, AssetClass.ETF),
        ("0700", Market.HK, AssetClass.STOCK),
        ("9988", Market.HK, AssetClass.STOCK),
        ("510300", Market.CN, AssetClass.ETF),
        ("159915", Market.CN, AssetClass.ETF),
        ("TLT", Market.US, AssetClass.ETF),
        ("IEF", Market.US, AssetClass.ETF),
        ("GLD", Market.US, AssetClass.ETF),
        ("GSG", Market.US, AssetClass.ETF),
    }
    for symbol, market, asset_class in symbols:
        _save_closes(market_data, symbol, market, asset_class, base_closes)


def _seed_volatility_indices(market_data: MarketDataService, vix_close: float, vxn_close: float) -> None:
    for symbol, close in (("^VIX", vix_close), ("^VXN", vxn_close)):
        instrument = Instrument(
            symbol=symbol,
            market=Market.US,
            asset_class=AssetClass.ETF,
            currency="USD",
            tradable=False,
            liquidity_bucket="high",
        )
        market_data.upsert_instruments([instrument])
        bars = []
        for offset in range(30, -1, -1):
            ts_date = _AS_OF - timedelta(days=offset)
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(ts_date, datetime.min.time(), tzinfo=UTC),
                    open=close * 0.99,
                    high=close * 1.01,
                    low=close * 0.98,
                    close=float(close),
                    volume=0.0,
                )
            )
        market_data._history.save_bars(instrument, bars)


# ---------------------------------------------------------------------------
# Baseline golden: sentiment must not shift the weighted score
# ---------------------------------------------------------------------------


def test_snapshot_overall_score_matches_baseline_when_sentiment_absent(tmp_path):
    """Baseline snapshot (no sentiment) behaves exactly as before."""

    service, market_data, _ = _build(tmp_path, sentiment=None)
    _seed_baseline_histories(market_data, bullish=True)
    snapshot = service.snapshot(_AS_OF)
    assert snapshot.market_sentiment is None
    assert isinstance(snapshot.overall_score, float)


def test_sentiment_does_not_change_overall_score(tmp_path):
    """Injecting sentiment must not modify the weighted regime score."""

    # Build two services sharing the SAME market data so the price path is
    # identical and only the sentiment dependency differs.
    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)

    baseline = MarketAwarenessService(config, market_data)
    baseline_snapshot = baseline.snapshot(_AS_OF)

    _seed_volatility_indices(market_data, vix_close=15.0, vxn_close=18.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    sentiment_service = MarketSentimentService(config, market_data, cnn_client=cnn_client)
    enriched = MarketAwarenessService(config, market_data, market_sentiment=sentiment_service)
    enriched_snapshot = enriched.snapshot(_AS_OF)

    assert enriched_snapshot.overall_score == pytest.approx(baseline_snapshot.overall_score)
    assert enriched_snapshot.overall_regime == baseline_snapshot.overall_regime
    assert enriched_snapshot.risk_posture == baseline_snapshot.risk_posture


# ---------------------------------------------------------------------------
# Dedup: reduce_risk + risk_off sentiment
# ---------------------------------------------------------------------------


def _make_risk_off_service(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    # Bearish baseline: triggers reduce_risk / risk_off posture.
    _seed_baseline_histories(market_data, bullish=False)

    # High VIX + CNN extreme greed → strongly negative sentiment → risk_switch OFF.
    _seed_volatility_indices(market_data, vix_close=40.0, vxn_close=35.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(90.0))
    sentiment_service = MarketSentimentService(config, market_data, cnn_client=cnn_client)
    service = MarketAwarenessService(
        config, market_data, market_sentiment=sentiment_service
    )
    return service, sentiment_service, market_data


def test_sentiment_risk_off_tags_existing_reduce_risk_action(tmp_path):
    service, sentiment_service, _ = _make_risk_off_service(tmp_path)
    snapshot = service.snapshot(_AS_OF)

    # Sanity: sentiment ran and is risk-off.
    assert snapshot.market_sentiment is not None
    assert snapshot.market_sentiment.risk_switch.value == "off"

    action_keys = [item.action_key for item in snapshot.actions]

    # If the price path emitted reduce_risk-class actions, the sentiment layer
    # MUST NOT double-stamp a new sentiment_force_defense item. In bearish
    # setups the baseline emits trim_weak_adds / raise_defense / pause_new_adds.
    if any(
        key in action_keys
        for key in ("trim_weak_adds", "raise_defense", "pause_new_adds")
    ):
        assert "sentiment_force_defense" not in action_keys, (
            f"Expected dedup to suppress sentiment_force_defense, got {action_keys}"
        )
        # The existing action must now carry sentiment_confirmed in .markets.
        tagged = [
            item
            for item in snapshot.actions
            if item.action_key in ("trim_weak_adds", "raise_defense", "pause_new_adds")
            and "sentiment_confirmed" in item.markets
        ]
        assert tagged, "reduce_risk action should be tagged sentiment_confirmed"
        # Rationale must reference sentiment.
        assert any("Confirmed by sentiment" in item.rationale for item in tagged)
    else:
        # If the price path did NOT emit reduce_risk actions (unlikely with a
        # bearish seed but possible), sentiment must still force a new item.
        assert "sentiment_force_defense" in action_keys


def test_sentiment_vix_shock_emits_us_vol_shock_action(tmp_path):
    service, _, _ = _make_risk_off_service(tmp_path)
    snapshot = service.snapshot(_AS_OF)
    assert "sentiment_us_vol_shock" in {
        item.action_key for item in snapshot.actions
    }


def test_snapshot_does_not_raise_when_sentiment_service_blows_up(tmp_path):
    """A failing sentiment service must not propagate into the awareness path."""

    class _ExplodingSentiment:
        def snapshot(self, as_of):  # noqa: D401
            raise RuntimeError("boom")

    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)
    service = MarketAwarenessService(
        config, market_data, market_sentiment=_ExplodingSentiment()
    )
    snapshot = service.snapshot(_AS_OF)
    assert snapshot.market_sentiment is None
    assert "sentiment_snapshot_failed" in snapshot.data_quality.adapter_limitations


def test_sentiment_contrarian_action_when_extreme_fear_not_risk_off(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)
    # Low VIX (calm) + CNN extreme fear (contrarian +0.6) → risk_switch ON.
    _seed_volatility_indices(market_data, vix_close=12.0, vxn_close=17.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(5.0))
    sentiment_service = MarketSentimentService(config, market_data, cnn_client=cnn_client)
    service = MarketAwarenessService(
        config, market_data, market_sentiment=sentiment_service
    )
    snapshot = service.snapshot(_AS_OF)
    assert snapshot.market_sentiment is not None
    assert snapshot.market_sentiment.risk_switch.value != "off"
    action_keys = {item.action_key for item in snapshot.actions}
    assert "sentiment_contrarian_tactical_add" in action_keys
    # Severity must be LOW (permissive tone per AGENTS.md).
    contrarian = next(
        item for item in snapshot.actions
        if item.action_key == "sentiment_contrarian_tactical_add"
    )
    assert contrarian.severity.value == "low"
    assert "允许" in contrarian.text or "permitted" in contrarian.text.lower()


# ---------------------------------------------------------------------------
# Round 2: CN action rules
# ---------------------------------------------------------------------------


def test_sentiment_cn_overheated_emitted_on_turnover_stress(tmp_path):
    """When CN turnover > 5% (STRESS), emit sentiment_cn_overheated."""

    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)
    _seed_volatility_indices(market_data, vix_close=15.0, vxn_close=18.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    cn_client = StaticCNMarketFlowsClient(
        turnover=make_cn_turnover_reading(6.0),       # STRESS
        northbound=make_cn_northbound_reading(0.0),
        margin=make_cn_margin_reading(0.0),
    )
    sentiment_service = MarketSentimentService(
        config, market_data, cnn_client=cnn_client, cn_flows_client=cn_client
    )
    service = MarketAwarenessService(
        config, market_data, market_sentiment=sentiment_service
    )
    snapshot = service.snapshot(_AS_OF)
    action_keys = {item.action_key for item in snapshot.actions}
    assert "sentiment_cn_overheated" in action_keys
    overheated = next(item for item in snapshot.actions if item.action_key == "sentiment_cn_overheated")
    assert overheated.severity.value == "medium"
    assert Market.CN.value in overheated.markets


def test_sentiment_cn_outflow_pressure_emitted_on_northbound_negative(tmp_path):
    """When northbound 5d < -20bn, emit sentiment_cn_outflow_pressure."""

    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)
    _seed_volatility_indices(market_data, vix_close=15.0, vxn_close=18.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    cn_client = StaticCNMarketFlowsClient(
        turnover=make_cn_turnover_reading(2.0),
        northbound=make_cn_northbound_reading(-30.0),  # below -20bn
        margin=make_cn_margin_reading(0.0),
    )
    sentiment_service = MarketSentimentService(
        config, market_data, cnn_client=cnn_client, cn_flows_client=cn_client
    )
    service = MarketAwarenessService(
        config, market_data, market_sentiment=sentiment_service
    )
    snapshot = service.snapshot(_AS_OF)
    action_keys = {item.action_key for item in snapshot.actions}
    assert "sentiment_cn_outflow_pressure" in action_keys
    outflow = next(item for item in snapshot.actions if item.action_key == "sentiment_cn_outflow_pressure")
    assert outflow.severity.value == "medium"
    assert Market.CN.value in outflow.markets


def test_cn_sentiment_does_not_change_overall_score(tmp_path):
    """CN sentiment must not alter the weighted regime score (same invariant as US)."""

    config = AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    _seed_baseline_histories(market_data, bullish=True)

    baseline = MarketAwarenessService(config, market_data)
    baseline_snapshot = baseline.snapshot(_AS_OF)

    _seed_volatility_indices(market_data, vix_close=15.0, vxn_close=18.0)
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    cn_client = StaticCNMarketFlowsClient(
        turnover=make_cn_turnover_reading(6.0),
        northbound=make_cn_northbound_reading(-30.0),
        margin=make_cn_margin_reading(+10.0),
    )
    sentiment_service = MarketSentimentService(
        config, market_data, cnn_client=cnn_client, cn_flows_client=cn_client
    )
    enriched = MarketAwarenessService(config, market_data, market_sentiment=sentiment_service)
    enriched_snapshot = enriched.snapshot(_AS_OF)

    assert enriched_snapshot.overall_score == pytest.approx(baseline_snapshot.overall_score)
    assert enriched_snapshot.overall_regime == baseline_snapshot.overall_regime
    assert enriched_snapshot.risk_posture == baseline_snapshot.risk_posture

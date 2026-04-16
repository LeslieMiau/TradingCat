"""Unit tests for `MarketSentimentService`.

Exercises bucket classification, composite scoring, and the no-raise / full-
degradation contract. Uses `StaticMarketDataAdapter` + seeded historical bars
so `MarketDataService.ensure_history` returns deterministic closes without
hitting yfinance.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.adapters.sentiment_sources.fakes import (
    StaticCNNFearGreedClient,
    make_cnn_reading,
)
from tradingcat.config import AppConfig, MarketSentimentConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market
from tradingcat.domain.sentiment import (
    MarketSentimentSnapshot,
    RiskSwitch,
    SentimentStatus,
)
from tradingcat.repositories.market_data import (
    HistoricalMarketDataRepository,
    InstrumentCatalogRepository,
)
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.market_sentiment import MarketSentimentService


_AS_OF = date(2026, 4, 15)


def _build_services(
    tmp_path,
    *,
    config: AppConfig | None = None,
    cnn_client=None,
    vix_close: float | None = None,
    vxn_close: float | None = None,
) -> tuple[MarketSentimentService, MarketDataService]:
    app_config = config or AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(app_config),
        history=HistoricalMarketDataRepository(app_config),
    )
    service = MarketSentimentService(app_config, market_data, cnn_client=cnn_client)
    if vix_close is not None:
        _seed_index_close(market_data, "^VIX", Market.US, vix_close)
    if vxn_close is not None:
        _seed_index_close(market_data, "^VXN", Market.US, vxn_close)
    return service, market_data


def _seed_index_close(
    market_data: MarketDataService,
    symbol: str,
    market: Market,
    close: float,
    *,
    as_of: date = _AS_OF,
) -> None:
    # The service auto-seeds the catalog; to be safe in tests, upsert too.
    instrument = Instrument(
        symbol=symbol,
        market=market,
        asset_class=AssetClass.ETF,
        currency="USD",
        name=f"{symbol} test",
        tradable=False,
        liquidity_bucket="high",
    )
    market_data.upsert_instruments([instrument])
    bars: list[Bar] = []
    # Seed at least 30 daily bars so ensure_history's sparsity guard is happy.
    for offset in range(30, 0, -1):
        bar_date = as_of - timedelta(days=offset)
        bars.append(
            Bar(
                instrument=instrument,
                timestamp=datetime.combine(bar_date, datetime.min.time(), tzinfo=UTC),
                open=close * 0.99,
                high=close * 1.01,
                low=close * 0.98,
                close=float(close),
                volume=0.0,
            )
        )
    # Final bar on as_of date → latest close.
    bars.append(
        Bar(
            instrument=instrument,
            timestamp=datetime.combine(as_of, datetime.min.time(), tzinfo=UTC),
            open=close * 0.99,
            high=close * 1.01,
            low=close * 0.98,
            close=float(close),
            volume=0.0,
        )
    )
    market_data._history.save_bars(instrument, bars)


# ---------------------------------------------------------------------------
# Bucket classification
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "vix_value,expected_status",
    [
        (10.0, SentimentStatus.CALM),
        (16.0, SentimentStatus.NEUTRAL),
        (22.0, SentimentStatus.ELEVATED),
        (30.0, SentimentStatus.STRESS),
        (45.0, SentimentStatus.EXTREME_FEAR),
    ],
)
def test_vix_bucket_classification(tmp_path, vix_value, expected_status):
    service, _ = _build_services(tmp_path, vix_close=vix_value, vxn_close=20.0)
    snapshot = service.snapshot(_AS_OF)
    vix = snapshot.indicator(Market.US, "us_vix")
    assert vix is not None
    assert vix.value == pytest.approx(vix_value, abs=1e-3)
    assert vix.status == expected_status


@pytest.mark.parametrize(
    "cnn_value,expected_status,expected_sign",
    [
        (5.0, SentimentStatus.EXTREME_FEAR, "+"),
        (30.0, SentimentStatus.NEUTRAL, "+"),   # rating "fear" but small +0.2 score
        (50.0, SentimentStatus.NEUTRAL, "0"),
        (70.0, SentimentStatus.ELEVATED, "-"),
        (90.0, SentimentStatus.EXTREME_GREED, "-"),
    ],
)
def test_cnn_bucket_classification(tmp_path, cnn_value, expected_status, expected_sign):
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(cnn_value))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=15.0, vxn_close=20.0
    )
    snapshot = service.snapshot(_AS_OF)
    cnn = snapshot.indicator(Market.US, "us_cnn_fng")
    assert cnn is not None
    assert cnn.status == expected_status
    if expected_sign == "+":
        assert cnn.score > 0
    elif expected_sign == "-":
        assert cnn.score < 0
    else:
        assert cnn.score == 0.0


# ---------------------------------------------------------------------------
# Risk switch + overrides
# ---------------------------------------------------------------------------


def test_us_score_excludes_missing_indicators(tmp_path):
    """When CNN is offline, US score must be based only on VIX+VXN weights."""

    service, _ = _build_services(
        tmp_path, cnn_client=None, vix_close=10.0, vxn_close=16.0
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    assert us_view is not None
    # VIX 10 → CALM (+0.6) @ 0.5 weight, VXN 16 → CALM (+0.5) @ 0.25, renormalised.
    # weighted total = 0.5*0.6 + 0.25*0.5 = 0.425; total_weight = 0.75
    # → 0.425 / 0.75 ≈ 0.5667
    assert us_view.score == pytest.approx(0.5667, abs=1e-3)


def test_vix_shock_forces_watch_minimum(tmp_path):
    """VIX > 30 should force risk_switch to at-least WATCH even if composite > +0.30."""

    # Artificially strong positive CNN so composite would lean ON absent override.
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(5.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=35.0, vxn_close=20.0
    )
    snapshot = service.snapshot(_AS_OF)
    # Even if US score leans positive (from CNN extreme_fear), VIX > 30 forces
    # the switch away from ON.
    assert snapshot.risk_switch in {RiskSwitch.WATCH, RiskSwitch.OFF}


def test_risk_switch_on_when_composite_positive(tmp_path):
    # Low VIX + low VXN + CNN extreme_fear (contrarian +0.6) → strongly positive US score.
    # CNN value kept >= 10 to avoid the "CNN<10 → min WATCH" safety override; still
    # inside the EXTREME_FEAR bucket (0-24) so the contrarian score applies.
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(15.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=12.0, vxn_close=16.0
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    assert us_view is not None
    assert us_view.score > 0.3
    # Round 1: composite is US weight (0.45) * us_score normalised by active
    # weight → equals us_score.
    assert snapshot.composite_score > 0.3
    assert snapshot.risk_switch == RiskSwitch.ON


def test_risk_switch_off_when_composite_strongly_negative(tmp_path):
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(90.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=32.0, vxn_close=33.0
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    assert us_view is not None
    assert us_view.score < -0.3
    assert snapshot.risk_switch == RiskSwitch.OFF


# ---------------------------------------------------------------------------
# Graceful degradation
# ---------------------------------------------------------------------------


def test_snapshot_never_raises_when_cnn_throws(tmp_path):
    broken_cnn = StaticCNNFearGreedClient(raise_on_fetch=True)
    service, _ = _build_services(
        tmp_path, cnn_client=broken_cnn, vix_close=15.0, vxn_close=20.0
    )
    snapshot = service.snapshot(_AS_OF)
    assert isinstance(snapshot, MarketSentimentSnapshot)
    cnn = snapshot.indicator(Market.US, "us_cnn_fng")
    assert cnn is not None
    assert cnn.value is None
    assert cnn.status == SentimentStatus.UNKNOWN
    # Adapter limitation recorded, but snapshot is still usable.
    assert "cnn_fetch_exception" in snapshot.data_quality.adapter_limitations


def test_snapshot_handles_missing_vix_history(tmp_path, monkeypatch):
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    service, market_data = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=None, vxn_close=None
    )

    # Simulate yfinance returning no bars for the volatility symbols. The
    # in-repo StaticMarketDataAdapter would otherwise produce synthetic bars.
    original_ensure_history = market_data.ensure_history

    def _empty_for_vol(symbols, start, end):
        result = original_ensure_history(symbols, start, end)
        for symbol in list(result):
            if symbol in {"^VIX", "^VXN"}:
                result[symbol] = []
        return result

    monkeypatch.setattr(market_data, "ensure_history", _empty_for_vol)

    snapshot = service.snapshot(_AS_OF)
    assert isinstance(snapshot, MarketSentimentSnapshot)
    vix = snapshot.indicator(Market.US, "us_vix")
    assert vix is not None
    assert vix.value is None
    assert vix.status == SentimentStatus.UNKNOWN
    # CNN still populated → view has SOME signal.
    cnn = snapshot.indicator(Market.US, "us_cnn_fng")
    assert cnn is not None and cnn.value is not None


def test_disabled_returns_empty_snapshot(tmp_path):
    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(enabled=False),
    )
    service, _ = _build_services(
        tmp_path, config=config, cnn_client=None, vix_close=None, vxn_close=None
    )
    snapshot = service.snapshot(_AS_OF)
    assert snapshot.risk_switch == RiskSwitch.UNKNOWN
    assert all(view.status == SentimentStatus.UNKNOWN for view in snapshot.views)
    assert "market_sentiment_disabled" in snapshot.data_quality.adapter_limitations


def test_hk_cn_views_are_placeholders_in_round_1(tmp_path):
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=16.0, vxn_close=20.0
    )
    snapshot = service.snapshot(_AS_OF)
    hk_view = snapshot.view_for(Market.HK)
    cn_view = snapshot.view_for(Market.CN)
    assert hk_view is not None and hk_view.status == SentimentStatus.UNKNOWN
    assert hk_view.indicators == []
    assert cn_view is not None and cn_view.status == SentimentStatus.UNKNOWN
    assert cn_view.indicators == []


def test_composite_excludes_unknown_markets(tmp_path):
    """Round 1 composite should equal the US score (no HK/CN contribution)."""

    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=14.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    assert us_view is not None
    # Active-weight renormalisation: with only US populated, composite equals
    # us score exactly (not us_score * 0.45).
    assert snapshot.composite_score == pytest.approx(us_view.score, abs=1e-4)

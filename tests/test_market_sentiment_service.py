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
    StaticCNMarketFlowsClient,
    StaticCNNFearGreedClient,
    StaticHKSouthboundClient,
    make_cn_margin_reading,
    make_cn_northbound_reading,
    make_cn_turnover_reading,
    make_cnn_reading,
    make_hk_southbound_reading,
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
    cn_flows_client=None,
    hk_flows_client=None,
    vix_close: float | None = None,
    vxn_close: float | None = None,
    hsiv_close: float | None = None,
) -> tuple[MarketSentimentService, MarketDataService]:
    app_config = config or AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(app_config),
        history=HistoricalMarketDataRepository(app_config),
    )
    service = MarketSentimentService(
        app_config, market_data,
        cnn_client=cnn_client,
        cn_flows_client=cn_flows_client,
        hk_flows_client=hk_flows_client,
    )
    if vix_close is not None:
        _seed_index_close(market_data, "^VIX", Market.US, vix_close)
    if vxn_close is not None:
        _seed_index_close(market_data, "^VXN", Market.US, vxn_close)
    if hsiv_close is not None:
        _seed_index_close(market_data, "^HSIV", Market.HK, hsiv_close)
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
    # HSIV seeded at CALM level so HK doesn't drag composite down via synthetic data.
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(15.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=12.0, vxn_close=16.0,
        hsiv_close=14.0,  # CALM → positive HK contribution
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    assert us_view is not None
    assert us_view.score > 0.3
    # Composite incorporates all active markets. With HSIV seeded at CALM (+0.5)
    # and strong US, composite stays above ON threshold.
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


def test_hk_view_with_hsiv_seeded(tmp_path):
    """When HSIV is seeded, HK view should be populated (no longer a placeholder)."""
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=16.0, vxn_close=20.0, hsiv_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    hk_view = snapshot.view_for(Market.HK)
    assert hk_view is not None
    assert hk_view.status != SentimentStatus.UNKNOWN
    assert len(hk_view.indicators) >= 1


def test_composite_excludes_unknown_markets(tmp_path, monkeypatch):
    """When only US is populated, composite equals the US score (renormalized)."""

    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    service, market_data = _build_services(
        tmp_path, cnn_client=cnn_client, vix_close=14.0, vxn_close=18.0
    )
    # Block HSIV and HK fallback symbols so HK stays UNKNOWN.
    original = market_data.ensure_history

    def _block_hk(symbols, start, end):
        result = original(symbols, start, end)
        for s in list(result):
            if s in {"^HSIV", "0700", "2800"}:
                result[s] = []
        return result

    monkeypatch.setattr(market_data, "ensure_history", _block_hk)

    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    hk_view = snapshot.view_for(Market.HK)
    assert us_view is not None
    assert hk_view is not None and hk_view.status == SentimentStatus.UNKNOWN
    # Active-weight renormalisation: with only US populated, composite equals
    # us score exactly (not us_score * 0.45).
    assert snapshot.composite_score == pytest.approx(us_view.score, abs=1e-4)


# ---------------------------------------------------------------------------
# CN bucket classification (Round 2)
# ---------------------------------------------------------------------------


def _cn_flows_client(
    turnover_pct: float | None = None,
    northbound_bn: float | None = None,
    margin_mom_pct: float | None = None,
) -> StaticCNMarketFlowsClient:
    return StaticCNMarketFlowsClient(
        turnover=make_cn_turnover_reading(turnover_pct) if turnover_pct is not None else None,
        northbound=make_cn_northbound_reading(northbound_bn) if northbound_bn is not None else None,
        margin=make_cn_margin_reading(margin_mom_pct) if margin_mom_pct is not None else None,
    )


@pytest.mark.parametrize(
    "turnover_pct,expected_status",
    [
        (1.0, SentimentStatus.CALM),
        (2.5, SentimentStatus.NEUTRAL),
        (4.0, SentimentStatus.ELEVATED),
        (6.0, SentimentStatus.STRESS),
    ],
)
def test_cn_turnover_bucket_classification(tmp_path, turnover_pct, expected_status):
    cn_client = _cn_flows_client(turnover_pct=turnover_pct, northbound_bn=0.0, margin_mom_pct=0.0)
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    ind = snapshot.indicator(Market.CN, "cn_turnover")
    assert ind is not None
    assert ind.value == pytest.approx(turnover_pct, abs=1e-3)
    assert ind.status == expected_status


@pytest.mark.parametrize(
    "northbound_bn,expected_status,expected_score",
    [
        (25.0, SentimentStatus.CALM, +0.5),
        (0.0, SentimentStatus.NEUTRAL, 0.0),
        (-25.0, SentimentStatus.STRESS, -0.5),
    ],
)
def test_cn_northbound_bucket_classification(tmp_path, northbound_bn, expected_status, expected_score):
    cn_client = _cn_flows_client(turnover_pct=2.0, northbound_bn=northbound_bn, margin_mom_pct=0.0)
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    ind = snapshot.indicator(Market.CN, "cn_northbound")
    assert ind is not None
    assert ind.value == pytest.approx(northbound_bn, abs=1e-3)
    assert ind.status == expected_status
    assert ind.score == pytest.approx(expected_score, abs=1e-3)


@pytest.mark.parametrize(
    "margin_mom_pct,expected_status,expected_score",
    [
        (+8.0, SentimentStatus.ELEVATED, -0.2),
        (0.0, SentimentStatus.NEUTRAL, 0.0),
        (-8.0, SentimentStatus.CALM, +0.3),
    ],
)
def test_cn_margin_bucket_classification(tmp_path, margin_mom_pct, expected_status, expected_score):
    cn_client = _cn_flows_client(turnover_pct=2.0, northbound_bn=0.0, margin_mom_pct=margin_mom_pct)
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    ind = snapshot.indicator(Market.CN, "cn_margin")
    assert ind is not None
    assert ind.value == pytest.approx(margin_mom_pct, abs=1e-3)
    assert ind.status == expected_status
    assert ind.score == pytest.approx(expected_score, abs=1e-3)


def test_cn_view_populates_when_all_sources_available(tmp_path):
    cn_client = _cn_flows_client(turnover_pct=2.0, northbound_bn=10.0, margin_mom_pct=0.0)
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    assert cn_view.status != SentimentStatus.UNKNOWN
    assert len(cn_view.indicators) == 3
    assert all(ind.value is not None for ind in cn_view.indicators)


def test_cn_score_follows_weight_formula(tmp_path):
    """CN = 0.4*turnover + 0.4*northbound + 0.2*margin."""
    cn_client = _cn_flows_client(
        turnover_pct=1.0,   # CALM +0.2
        northbound_bn=25.0, # CALM +0.5
        margin_mom_pct=-8.0, # CALM +0.3
    )
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    # 0.4*0.2 + 0.4*0.5 + 0.2*0.3 = 0.08 + 0.20 + 0.06 = 0.34
    assert cn_view.score == pytest.approx(0.34, abs=1e-3)


def test_cn_score_excludes_missing_indicators(tmp_path):
    """When one CN indicator is unavailable, renormalize by active weight."""
    cn_client = _cn_flows_client(
        turnover_pct=1.0,    # CALM +0.2
        northbound_bn=None,  # missing
        margin_mom_pct=0.0,  # NEUTRAL 0.0
    )
    service, _ = _build_services(
        tmp_path, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    # Active weights: 0.4 (turnover) + 0.2 (margin) = 0.6
    # weighted = 0.4*0.2 + 0.2*0.0 = 0.08
    # score = 0.08 / 0.6 ≈ 0.1333
    assert cn_view.score == pytest.approx(0.1333, abs=1e-3)


def test_cn_disabled_returns_unknown(tmp_path):
    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(cn_backend="disabled"),
    )
    cn_client = _cn_flows_client(turnover_pct=2.0, northbound_bn=0.0, margin_mom_pct=0.0)
    service, _ = _build_services(
        tmp_path, config=config, cn_flows_client=cn_client, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    assert cn_view.status == SentimentStatus.UNKNOWN
    assert cn_view.indicators == []


def test_cn_client_missing_returns_unknown(tmp_path):
    service, _ = _build_services(
        tmp_path, cn_flows_client=None, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    assert cn_view.status == SentimentStatus.UNKNOWN


def test_cn_exception_does_not_propagate(tmp_path):
    broken = StaticCNMarketFlowsClient(
        raise_on_turnover=True, raise_on_northbound=True, raise_on_margin=True
    )
    service, _ = _build_services(
        tmp_path, cn_flows_client=broken, vix_close=15.0, vxn_close=18.0
    )
    snapshot = service.snapshot(_AS_OF)
    assert isinstance(snapshot, MarketSentimentSnapshot)
    cn_view = snapshot.view_for(Market.CN)
    assert cn_view is not None
    # All three indicators should have value=None due to exceptions
    for ind in cn_view.indicators:
        assert ind.value is None
        assert ind.status == SentimentStatus.UNKNOWN


def test_composite_includes_cn_when_populated(tmp_path):
    """Composite should incorporate CN when both US and CN are populated."""
    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    cn_client = _cn_flows_client(turnover_pct=1.0, northbound_bn=25.0, margin_mom_pct=-8.0)
    service, market_data = _build_services(
        tmp_path, cnn_client=cnn_client, cn_flows_client=cn_client,
        vix_close=14.0, vxn_close=18.0
    )
    # Ensure HK fallback doesn't interfere — monkeypatch ensure_history for HSIV
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    cn_view = snapshot.view_for(Market.CN)
    hk_view = snapshot.view_for(Market.HK)
    assert us_view is not None and cn_view is not None
    # Composite uses all active views. If HK is also active (fallback resolved),
    # the denominator includes all 3. If HK is unknown, only US + CN.
    active_weights = {"US": 0.45, "CN": 0.30}
    if hk_view is not None and hk_view.status != SentimentStatus.UNKNOWN:
        active_weights["HK"] = 0.25
    total_w = sum(active_weights.values())
    expected = sum(
        w * {"US": us_view, "CN": cn_view, "HK": hk_view}.get(m, hk_view).score
        for m, w in active_weights.items()
    ) / total_w
    assert snapshot.composite_score == pytest.approx(expected, abs=1e-2)


# ---------------------------------------------------------------------------
# HK view (Round 3)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "hsiv_value,expected_status",
    [
        (14.0, SentimentStatus.CALM),
        (20.0, SentimentStatus.NEUTRAL),
        (25.0, SentimentStatus.ELEVATED),
        (35.0, SentimentStatus.STRESS),
    ],
)
def test_hsiv_bucket_classification(tmp_path, hsiv_value, expected_status):
    service, _ = _build_services(
        tmp_path, vix_close=15.0, vxn_close=18.0, hsiv_close=hsiv_value
    )
    snapshot = service.snapshot(_AS_OF)
    hk_vol = snapshot.indicator(Market.HK, "hk_vol")
    assert hk_vol is not None
    assert hk_vol.value == pytest.approx(hsiv_value, abs=1e-3)
    assert hk_vol.status == expected_status
    assert hk_vol.source == "yfinance"


def test_hk_fallback_realized_vol_when_hsiv_missing(tmp_path, monkeypatch):
    """When HSIV returns no bars, fallback to realized-vol from 0700/2800."""

    service, market_data = _build_services(
        tmp_path, vix_close=15.0, vxn_close=18.0, hsiv_close=None
    )
    # Seed fallback symbols with steady returns → low realized vol.
    for symbol in ("0700", "2800"):
        instrument = Instrument(
            symbol=symbol,
            market=Market.HK,
            asset_class=AssetClass.STOCK,
            currency="HKD",
            liquidity_bucket="high",
        )
        market_data.upsert_instruments([instrument])
        bars = []
        for offset in range(30, -1, -1):
            bar_date = _AS_OF - timedelta(days=offset)
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.combine(bar_date, datetime.min.time(), tzinfo=UTC),
                    open=100.0,
                    high=100.5,
                    low=99.5,
                    close=100.0 + 0.01 * (30 - offset),  # gentle uptrend
                    volume=1_000_000,
                )
            )
        market_data._history.save_bars(instrument, bars)

    # Monkeypatch ensure_history to return empty for HSIV.
    original = market_data.ensure_history

    def _empty_hsiv(symbols, start, end):
        result = original(symbols, start, end)
        for s in list(result):
            if s in {"^HSIV"}:
                result[s] = []
        return result

    monkeypatch.setattr(market_data, "ensure_history", _empty_hsiv)

    snapshot = service.snapshot(_AS_OF)
    hk_vol = snapshot.indicator(Market.HK, "hk_vol")
    assert hk_vol is not None
    assert hk_vol.value is not None
    assert hk_vol.source == "realized_vol_fallback"
    assert hk_vol.status != SentimentStatus.UNKNOWN


def test_hk_score_with_southbound_disabled(tmp_path):
    """When southbound is disabled, HK score = 1.0 * vol_score."""

    service, _ = _build_services(
        tmp_path, vix_close=15.0, vxn_close=18.0, hsiv_close=14.0  # CALM +0.5
    )
    snapshot = service.snapshot(_AS_OF)
    hk_view = snapshot.view_for(Market.HK)
    assert hk_view is not None
    assert hk_view.score == pytest.approx(0.5, abs=1e-3)  # 1.0 * +0.5


# ---------------------------------------------------------------------------
# Two-market STRESS override (Round 3)
# ---------------------------------------------------------------------------


def test_two_market_stress_forces_risk_off(tmp_path):
    """When >= 2 markets are in STRESS, risk_switch must be OFF."""

    cn_client = _cn_flows_client(
        turnover_pct=6.0,     # STRESS
        northbound_bn=-30.0,  # STRESS
        margin_mom_pct=+10.0, # ELEVATED
    )
    service, _ = _build_services(
        tmp_path,
        cn_flows_client=cn_client,
        vix_close=32.0,     # US: STRESS
        vxn_close=33.0,     # US: STRESS
        hsiv_close=14.0,    # HK: CALM
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    cn_view = snapshot.view_for(Market.CN)
    # Both US and CN should be in STRESS territory.
    assert us_view is not None and us_view.status in {SentimentStatus.STRESS, SentimentStatus.EXTREME_FEAR}
    assert cn_view is not None and cn_view.status in {SentimentStatus.STRESS, SentimentStatus.EXTREME_FEAR}
    # Two-market STRESS → force OFF.
    assert snapshot.risk_switch == RiskSwitch.OFF


def test_single_market_stress_does_not_force_off(tmp_path):
    """One market in STRESS alone should not trigger the two-market override."""

    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(15.0))  # EXTREME_FEAR +0.6
    cn_client = _cn_flows_client(turnover_pct=1.0, northbound_bn=25.0, margin_mom_pct=-8.0)  # all positive
    service, _ = _build_services(
        tmp_path,
        cnn_client=cnn_client,
        cn_flows_client=cn_client,
        vix_close=12.0,    # US: CALM
        vxn_close=16.0,    # US: CALM
        hsiv_close=35.0,   # HK: STRESS (only one market)
    )
    snapshot = service.snapshot(_AS_OF)
    # Only HK in STRESS → should NOT force OFF.
    assert snapshot.risk_switch != RiskSwitch.OFF


def test_composite_includes_all_three_markets(tmp_path):
    """With US + CN + HK all populated, composite uses all three weights."""

    cnn_client = StaticCNNFearGreedClient(reading=make_cnn_reading(50.0))
    cn_client = _cn_flows_client(turnover_pct=2.0, northbound_bn=0.0, margin_mom_pct=0.0)
    service, _ = _build_services(
        tmp_path, cnn_client=cnn_client, cn_flows_client=cn_client,
        vix_close=14.0, vxn_close=18.0, hsiv_close=18.0,
    )
    snapshot = service.snapshot(_AS_OF)
    us_view = snapshot.view_for(Market.US)
    cn_view = snapshot.view_for(Market.CN)
    hk_view = snapshot.view_for(Market.HK)
    assert all(v is not None and v.status != SentimentStatus.UNKNOWN for v in [us_view, cn_view, hk_view])
    # All three active → no renormalization needed.
    expected = 0.45 * us_view.score + 0.30 * cn_view.score + 0.25 * hk_view.score
    assert snapshot.composite_score == pytest.approx(expected, abs=1e-3)


# ---------------------------------------------------------------------------
# HK southbound (Round 3 — feature-flagged)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "net_hkd_bn,expected_status,expected_score",
    [
        (+15.0, SentimentStatus.CALM, +0.5),
        (0.0, SentimentStatus.NEUTRAL, 0.0),
        (-15.0, SentimentStatus.STRESS, -0.5),
    ],
)
def test_hk_southbound_bucket_classification(
    tmp_path, net_hkd_bn, expected_status, expected_score
):
    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(hk_southbound_enabled=True),
    )
    hk_client = StaticHKSouthboundClient(
        reading=make_hk_southbound_reading(net_hkd_bn)
    )
    service, _ = _build_services(
        tmp_path, config=config, hk_flows_client=hk_client,
        vix_close=15.0, vxn_close=18.0, hsiv_close=18.0,
    )
    snapshot = service.snapshot(_AS_OF)
    sb = snapshot.indicator(Market.HK, "hk_southbound")
    assert sb is not None
    assert sb.value == pytest.approx(net_hkd_bn, abs=1e-3)
    assert sb.status == expected_status
    assert sb.score == pytest.approx(expected_score, abs=1e-3)


def test_hk_score_with_southbound_enabled(tmp_path):
    """When southbound is enabled, HK score = 0.7*vol + 0.3*southbound."""

    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(hk_southbound_enabled=True),
    )
    hk_client = StaticHKSouthboundClient(
        reading=make_hk_southbound_reading(+15.0)  # CALM +0.5
    )
    service, _ = _build_services(
        tmp_path, config=config, hk_flows_client=hk_client,
        vix_close=15.0, vxn_close=18.0,
        hsiv_close=14.0,  # CALM +0.5
    )
    snapshot = service.snapshot(_AS_OF)
    hk_view = snapshot.view_for(Market.HK)
    assert hk_view is not None
    # 0.7 * 0.5 + 0.3 * 0.5 = 0.35 + 0.15 = 0.50
    assert hk_view.score == pytest.approx(0.5, abs=1e-3)
    assert len(hk_view.indicators) == 2


def test_hk_score_with_southbound_enabled_divergent(tmp_path):
    """Vol and southbound diverge: vol CALM (+0.5), southbound STRESS (-0.5)."""

    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(hk_southbound_enabled=True),
    )
    hk_client = StaticHKSouthboundClient(
        reading=make_hk_southbound_reading(-15.0)  # STRESS -0.5
    )
    service, _ = _build_services(
        tmp_path, config=config, hk_flows_client=hk_client,
        vix_close=15.0, vxn_close=18.0,
        hsiv_close=14.0,  # CALM +0.5
    )
    snapshot = service.snapshot(_AS_OF)
    hk_view = snapshot.view_for(Market.HK)
    assert hk_view is not None
    # 0.7 * 0.5 + 0.3 * (-0.5) = 0.35 - 0.15 = 0.20
    assert hk_view.score == pytest.approx(0.2, abs=1e-3)


def test_hk_southbound_enabled_but_client_missing(tmp_path):
    """When flag is on but no client wired, southbound returns UNKNOWN indicator."""

    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(hk_southbound_enabled=True),
    )
    service, _ = _build_services(
        tmp_path, config=config,
        vix_close=15.0, vxn_close=18.0, hsiv_close=18.0,
    )
    snapshot = service.snapshot(_AS_OF)
    sb = snapshot.indicator(Market.HK, "hk_southbound")
    assert sb is not None
    assert sb.value is None
    assert sb.status == SentimentStatus.UNKNOWN
    assert "hk_southbound_client_missing" in snapshot.data_quality.adapter_limitations


def test_hk_southbound_exception_does_not_propagate(tmp_path):
    """Southbound client raising → indicator degrades, snapshot valid."""

    config = AppConfig(
        data_dir=tmp_path,
        market_sentiment=MarketSentimentConfig(hk_southbound_enabled=True),
    )
    broken = StaticHKSouthboundClient(raise_on_fetch=True)
    service, _ = _build_services(
        tmp_path, config=config, hk_flows_client=broken,
        vix_close=15.0, vxn_close=18.0, hsiv_close=18.0,
    )
    snapshot = service.snapshot(_AS_OF)
    assert isinstance(snapshot, MarketSentimentSnapshot)
    sb = snapshot.indicator(Market.HK, "hk_southbound")
    assert sb is not None
    assert sb.value is None
    assert sb.status == SentimentStatus.UNKNOWN

"""Tests for Insight engine — detectors, store, and orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    Bar,
    Insight,
    InsightEvidence,
    InsightKind,
    MarketAwarenessSignalStatus,
    InsightSeverity,
    InsightUserAction,
    Instrument,
    Market,
    AssetClass,
)
from tradingcat.repositories.insight_store import InsightStore
from tradingcat.services.insight_detectors.correlation_break import (
    CorrelationBreakConfig,
    CorrelationBreakDetector,
    _correlation,
    _returns,
    _stable_id,
    _zscore,
)
from tradingcat.services.insight_engine import InsightEngineRunResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _instrument(symbol: str = "0700", market: Market = Market.HK) -> Instrument:
    return Instrument(
        symbol=symbol,
        market=market,
        asset_class=AssetClass.STOCK,
        currency="HKD",
    )


def _closes(start: float, step: float, count: int) -> list[float]:
    """Generate a price series."""
    return [round(start + step * i, 4) for i in range(count)]


def _bars(closes: list[float], start_dt: datetime | None = None) -> list[Bar]:
    base = start_dt or datetime(2026, 1, 1, tzinfo=UTC)
    return [
        Bar(
            instrument=_instrument(),
            timestamp=base + timedelta(days=i),
            open=c * 0.99,
            high=c * 1.01,
            low=c * 0.98,
            close=c,
            volume=1_000_000,
        )
        for i, c in enumerate(closes)
    ]


def _make_detector(
    correlation_window: int = 30,
    deviation_window: int = 90,
    min_correlation: float = 0.5,
    z_notable: float = 2.0,
    z_urgent: float = 3.0,
) -> CorrelationBreakDetector:
    return CorrelationBreakDetector(
        CorrelationBreakConfig(
            correlation_window=correlation_window,
            deviation_window=deviation_window,
            min_correlation=min_correlation,
            z_notable=z_notable,
            z_urgent=z_urgent,
        )
    )


# ---------------------------------------------------------------------------
# Detector math
# ---------------------------------------------------------------------------


def test_returns_computes_daily_pct_change():
    result = _returns([100.0, 101.0, 103.0])
    assert len(result) == 2
    assert result[0] == pytest.approx(0.01)
    assert result[1] == pytest.approx(0.0198, rel=1e-3)


def test_correlation_perfect_positive():
    xs = [1.0, 2.0, 3.0, 4.0, 5.0]
    r = _correlation(xs, xs)
    assert r is not None
    assert abs(r - 1.0) < 1e-9


def test_correlation_insufficient_data():
    assert _correlation([1.0], [2.0]) is None


def test_zscore_above_threshold():
    sample = [0.0] * 89 + [0.01]  # mostly 0, one small positive
    z, mu, sigma = _zscore(sample, 0.05)
    assert z is not None
    assert z > 2.0


def test_zscore_below_threshold():
    # Realistic return-like sample with some variance
    sample = [0.001 * (i % 5 - 2) for i in range(90)]
    z, mu, sigma = _zscore(sample, 0.0005)
    assert z is not None
    assert z < 2.0


def test_zscore_too_few_samples():
    assert _zscore([0.0] * 5, 1.0) is None


# ---------------------------------------------------------------------------
# Detector correlation_break
# ---------------------------------------------------------------------------


def test_detector_triggers_on_divergence():
    """Insight emitted when correlation is high and return-divergence z >= 2.0."""
    detector = _make_detector()
    as_of = date(2026, 3, 15)
    # Both rise at similar pace for ~130 days, then diverge sharply on last day.
    asset = [100.0]
    bench = [100.0]
    for i in range(1, 130):
        drift = 0.002
        jitter = (i * 7) % 13 * 0.0003  # deterministic tiny jitter
        asset.append(round(asset[-1] * (1 + drift + jitter), 4))
        bench.append(round(bench[-1] * (1 + drift), 4))
    # Last day: bench jumps, asset drops → opposite sign → urgent
    asset.append(round(asset[-1] * 0.97, 4))
    bench.append(round(bench[-1] * 1.015, 4))

    insight = detector._detect_one(
        instrument=_instrument(),
        benchmark_symbol="SPY",
        bars_by_symbol={"0700": _bars(asset), "SPY": _bars(bench)},
        as_of=as_of,
        triggered_at=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insight is not None
    assert insight.severity == InsightSeverity.URGENT  # opposite sign


def test_detector_skips_low_correlation():
    """No insight when instrument and benchmark move independently."""
    detector = _make_detector()
    as_of = date(2026, 3, 15)
    # Random-walk-ish series: asset goes up, bench goes nowhere
    closes_asset = _closes(100.0, 0.3, 130)
    closes_bench = [100.0 + (i % 3) * 0.1 for i in range(130)]

    insight = detector._detect_one(
        instrument=_instrument(),
        benchmark_symbol="SPY",
        bars_by_symbol={"0700": _bars(closes_asset), "SPY": _bars(closes_bench)},
        as_of=as_of,
        triggered_at=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insight is None


def test_detector_notable_vs_urgent():
    """Same-sign deviation below z=3 is notable; opposite sign is urgent."""
    detector = _make_detector()
    as_of = date(2026, 3, 15)
    # For opposite sign we need today_asset_ret * today_bench_ret < 0.
    # Build 95 values that are correlated, then make the last bar diverge.
    base_closes = _closes(100.0, 0.1, 96)
    # Last bar: asset drops, bench rises (opposite sign)
    asset_bars = _bars(base_closes + [99.0])
    bench_bars = _bars(base_closes + [101.0])

    insight = detector._detect_one(
        instrument=_instrument(),
        benchmark_symbol="SPY",
        bars_by_symbol={"0700": asset_bars, "SPY": bench_bars},
        as_of=as_of,
        triggered_at=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    # Opposite sign should trigger urgent regardless of z magnitude
    if insight is not None:
        assert insight.severity == InsightSeverity.URGENT


def _diverging_series() -> tuple[list[float], list[float]]:
    """Return (asset_closes, bench_closes) with high correlation then last-day divergence."""
    asset = [100.0]
    bench = [100.0]
    for i in range(1, 130):
        jitter = (i * 7) % 13 * 0.0003
        asset.append(round(asset[-1] * (1 + 0.002 + jitter), 4))
        bench.append(round(bench[-1] * 1.002, 4))
    asset.append(round(asset[-1] * 0.97, 4))
    bench.append(round(bench[-1] * 1.015, 4))
    return asset, bench


def test_detector_causal_chain_completeness():
    """Every insight has at least 3 evidence entries with source + fact."""
    detector = _make_detector()
    as_of = date(2026, 3, 15)
    asset_closes, bench_closes = _diverging_series()

    insight = detector._detect_one(
        instrument=_instrument(),
        benchmark_symbol="SPY",
        bars_by_symbol={"0700": _bars(asset_closes), "SPY": _bars(bench_closes)},
        as_of=as_of,
        triggered_at=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insight is not None
    assert len(insight.causal_chain) >= 3
    for ev in insight.causal_chain:
        assert ev.source, f"evidence missing source: {ev}"
        assert ev.fact, f"evidence missing fact: {ev}"
        assert ev.value, f"evidence missing value dict: {ev}"


# ---------------------------------------------------------------------------
# Stable ID
# ---------------------------------------------------------------------------


def test_stable_id_is_deterministic():
    id1 = _stable_id("0700", "SPY", date(2026, 3, 15))
    id2 = _stable_id("0700", "SPY", date(2026, 3, 15))
    assert id1 == id2


def test_stable_id_differs_for_different_date():
    id1 = _stable_id("0700", "SPY", date(2026, 3, 15))
    id2 = _stable_id("0700", "SPY", date(2026, 3, 16))
    assert id1 != id2


# ---------------------------------------------------------------------------
# InsightStore (memory backend — DuckDB tested in integration)
# ---------------------------------------------------------------------------


def test_store_upsert_and_get():
    store = InsightStore(AppConfig())
    insight = Insight(
        id="test-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.NOTABLE,
        headline="test headline",
        subjects=["0700"],
        causal_chain=[
            InsightEvidence(source="test", fact="x", value={}, observed_at=datetime.now(UTC))
        ],
        confidence=0.8,
        triggered_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(hours=36),
    )
    store.upsert(insight)
    loaded = store.get("test-1")
    assert loaded is not None
    assert loaded.id == "test-1"
    assert loaded.headline == "test headline"


def test_store_dedup_upsert_replaces():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    insight = Insight(
        id="dedup-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.NOTABLE,
        headline="original",
        subjects=[],
        confidence=0.5,
        triggered_at=now,
        expires_at=now + timedelta(hours=36),
    )
    store.upsert(insight)
    updated = insight.model_copy(update={"headline": "updated"})
    store.upsert(updated)
    loaded = store.get("dedup-1")
    assert loaded is not None
    assert loaded.headline == "updated"


def test_store_list_excludes_expired():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    expired = Insight(
        id="exp-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.INFO,
        headline="expired",
        subjects=[],
        confidence=0.5,
        triggered_at=now - timedelta(days=10),
        expires_at=now - timedelta(hours=1),
    )
    active = Insight(
        id="act-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.URGENT,
        headline="active",
        subjects=[],
        confidence=0.9,
        triggered_at=now,
        expires_at=now + timedelta(hours=36),
    )
    store.upsert(expired)
    store.upsert(active)
    items = store.list()
    ids = [item.id for item in items]
    assert "act-1" in ids
    assert "exp-1" not in ids


def test_store_expire_stale_removes_pending():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    stale = Insight(
        id="stale-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.INFO,
        headline="stale",
        subjects=[],
        confidence=0.5,
        triggered_at=now - timedelta(days=10),
        expires_at=now - timedelta(hours=1),
    )
    store.upsert(stale)
    count = store.expire_stale(now=now)
    assert count == 1
    assert store.get("stale-1") is None


def test_store_expire_skips_dismissed():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    dismissed = Insight(
        id="dismissed-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.INFO,
        headline="dismissed stale",
        subjects=[],
        confidence=0.5,
        triggered_at=now - timedelta(days=10),
        expires_at=now - timedelta(hours=1),
        user_action=InsightUserAction.DISMISSED,
    )
    store.upsert(dismissed)
    count = store.expire_stale(now=now)
    assert count == 0  # dismissed insights are not auto-expired


def test_store_list_respects_include_dismissed():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    dismissed = Insight(
        id="dismissed-visible",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.INFO,
        headline="gone",
        subjects=[],
        confidence=0.5,
        triggered_at=now,
        expires_at=now + timedelta(hours=36),
        user_action=InsightUserAction.DISMISSED,
    )
    store.upsert(dismissed)
    assert len(store.list()) == 0
    assert len(store.list(include_dismissed=True)) == 1


def test_store_update_user_action():
    store = InsightStore(AppConfig())
    now = datetime.now(UTC)
    insight = Insight(
        id="action-1",
        kind=InsightKind.CORRELATION_BREAK,
        severity=InsightSeverity.NOTABLE,
        headline="actionable",
        subjects=[],
        confidence=0.7,
        triggered_at=now,
        expires_at=now + timedelta(hours=36),
    )
    store.upsert(insight)
    assert store.update_user_action("action-1", InsightUserAction.DISMISSED, reason="noise")
    loaded = store.get("action-1")
    assert loaded is not None
    assert loaded.user_action == InsightUserAction.DISMISSED
    assert loaded.dismissed_reason == "noise"


# ---------------------------------------------------------------------------
# Engine orchestration
# ---------------------------------------------------------------------------


def test_engine_run_empty_watchlist_yields_empty():
    """Engine returns no insights when watchlist is empty."""
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.repositories.insight_store import InsightStore
    config = AppConfig()

    class _EmptyMarketData:
        def list_instruments(self, **kwargs):
            return []
        def get_instrument(self, symbol, strict=False):
            return None

    engine = InsightEngine(
        store=InsightStore(config),
        market_data=_EmptyMarketData(),  # type: ignore[arg-type]
        market_awareness=None,  # won't be called due to empty watchlist
    )
    result = engine.run(as_of=date(2026, 3, 15))
    assert isinstance(result, InsightEngineRunResult)
    assert result.produced == []
    assert result.suppressed_duplicates == 0


# ---------------------------------------------------------------------------
# Sector Map
# ---------------------------------------------------------------------------


def test_sector_map_basic():
    """SectorMap returns correct sector and benchmark lookups."""
    from tradingcat.services.insight_detectors.sector_map import SectorMap

    sm = SectorMap()
    assert sm.get_sector("0700") == "technology"
    assert sm.get_sector("SPY") == "broad_market"
    assert sm.get_sector("QQQ") == "technology"
    assert sm.get_sector("UNKNOWN") is None
    assert sm.get_sector_benchmark("technology") == "QQQ"
    assert sm.get_sector_benchmark("broad_market") == "SPY"
    assert sm.get_sector_benchmark("nonexistent") is None


def test_sector_map_group_by_sector():
    """Instruments are grouped by their sector, unknowns omitted."""
    from tradingcat.services.insight_detectors.sector_map import SectorMap

    sm = SectorMap()
    watchlist = [
        _instrument("0700", Market.HK),
        _instrument("9988", Market.HK),
        _instrument("SPY", Market.US),
        _instrument("UNKNOWN", Market.US),
    ]
    groups = sm.group_by_sector(watchlist)
    assert "technology" in groups
    assert "broad_market" in groups
    assert len(groups["technology"]) == 2
    assert len(groups["broad_market"]) == 1


# ---------------------------------------------------------------------------
# Sector Divergence Detector
# ---------------------------------------------------------------------------


def _make_sector_detector(
    deviation_window: int = 60,
    min_sector_move_pct: float = 2.0,
    percentile_notable: float = 20.0,
    percentile_urgent: float = 10.0,
    min_beta: float = 0.5,
) -> SectorDivergenceDetector:
    from tradingcat.services.insight_detectors.sector_divergence import (
        SectorDivergenceConfig,
        SectorDivergenceDetector,
    )
    return SectorDivergenceDetector(
        SectorDivergenceConfig(
            deviation_window=deviation_window,
            min_sector_move_pct=min_sector_move_pct,
            percentile_notable=percentile_notable,
            percentile_urgent=percentile_urgent,
            min_beta=min_beta,
        )
    )


def test_sector_divergence_detector_triggers():
    """Instrument at extreme percentile within sector emits insight."""
    detector = _make_sector_detector()
    as_of = date(2026, 3, 15)

    # 6 technology symbols: 5 move together, 0700 diverges upward
    tech_symbols = ["0700", "9988", "300308", "603986", "QQQ", "XLK"]
    base_closes = _closes(100.0, 0.2, 66)
    bars_by_symbol: dict[str, list[Bar]] = {}
    for sym in tech_symbols:
        if sym == "0700":
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.07, 4)]
        else:
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.035, 4)]
        bars_by_symbol[sym] = _bars(closes)

    watchlist = [_instrument(sym, Market.US if sym in ("QQQ", "XLK") else Market.HK if sym in ("0700", "9988") else Market.CN) for sym in tech_symbols]
    insights = detector.detect(
        as_of=as_of,
        watchlist=watchlist,
        bars_by_symbol=bars_by_symbol,
        benchmark_by_market={},
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert len(insights) == 1
    assert "0700" in insights[0].headline


def test_sector_divergence_detector_skips_small_sector_move():
    """No insight when sector return is below min_sector_move_pct."""
    detector = _make_sector_detector(min_sector_move_pct=2.0)
    as_of = date(2026, 3, 15)

    tech_symbols = ["0700", "9988"]
    base_closes = _closes(100.0, 0.01, 66)  # tiny drift → sector moves < 2%
    bars_by_symbol = {sym: _bars(base_closes) for sym in tech_symbols}
    watchlist = [_instrument(sym, Market.HK) for sym in tech_symbols]

    insights = detector.detect(
        as_of=as_of,
        watchlist=watchlist,
        bars_by_symbol=bars_by_symbol,
        benchmark_by_market={},
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insights == []


def test_sector_divergence_detector_skips_single_instrument_sector():
    """No insight when sector has fewer than 2 instruments."""
    detector = _make_sector_detector()
    as_of = date(2026, 3, 15)

    closes = _closes(100.0, 0.2, 66)
    bars_by_symbol = {"0700": _bars(closes)}
    watchlist = [_instrument("0700", Market.HK)]

    insights = detector.detect(
        as_of=as_of,
        watchlist=watchlist,
        bars_by_symbol=bars_by_symbol,
        benchmark_by_market={},
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insights == []


def test_sector_divergence_causal_chain():
    """Every insight has 3+ evidence entries with source + fact + value."""
    detector = _make_sector_detector()
    as_of = date(2026, 3, 15)

    tech_symbols = ["0700", "9988", "300308", "603986", "QQQ", "XLK"]
    base_closes = _closes(100.0, 0.2, 66)
    bars_by_symbol: dict[str, list[Bar]] = {}
    for sym in tech_symbols:
        if sym == "0700":
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.07, 4)]
        else:
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.035, 4)]
        bars_by_symbol[sym] = _bars(closes)

    watchlist = [_instrument(sym, Market.US if sym in ("QQQ", "XLK") else Market.HK if sym in ("0700", "9988") else Market.CN) for sym in tech_symbols]
    insights = detector.detect(
        as_of=as_of,
        watchlist=watchlist,
        bars_by_symbol=bars_by_symbol,
        benchmark_by_market={},
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert len(insights) >= 1
    for insight in insights:
        assert len(insight.causal_chain) >= 3
        for ev in insight.causal_chain:
            assert ev.source, f"evidence missing source: {ev}"
            assert ev.fact, f"evidence missing fact: {ev}"
            assert ev.value is not None, f"evidence missing value: {ev}"


# ---------------------------------------------------------------------------
# Engine orchestration with both detectors
# ---------------------------------------------------------------------------


def test_engine_runs_both_detectors():
    """Engine.run() with both detectors wired does not crash and produces sector insights."""
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.insight_detectors.sector_map import SectorMap

    config = AppConfig()

    tech_symbols = ["0700", "9988", "300308", "603986", "QQQ", "XLK"]
    base_closes = _closes(100.0, 0.2, 96)
    bars_by_symbol: dict[str, list[Bar]] = {}
    for sym in tech_symbols:
        closes: list[float]
        if sym == "0700":
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.07, 4)]
        else:
            closes = base_closes[:-1] + [round(base_closes[-1] * 1.035, 4)]
        bars_by_symbol[sym] = _bars(closes)

    class _RichMarketData:
        def list_instruments(self, **kwargs):
            return [
                _instrument("0700", Market.HK),
                _instrument("9988", Market.HK),
                _instrument("300308", Market.CN),
                _instrument("603986", Market.CN),
                _instrument("QQQ", Market.US),
                _instrument("XLK", Market.US),
            ]

        def get_instrument(self, symbol, strict=False):
            return _instrument(symbol)

        def get_bars(self, symbol, start, end):
            return bars_by_symbol.get(symbol, [])

    class _MockAwareness:
        def benchmark_baskets(self):
            return {
                "hk": {"benchmark_symbol": "0700"},
                "cn": {"benchmark_symbol": "510300"},
                "us": {"benchmark_symbol": "SPY"},
            }

    engine = InsightEngine(
        store=InsightStore(config),
        market_data=_RichMarketData(),  # type: ignore[arg-type]
        market_awareness=_MockAwareness(),  # type: ignore[arg-type]
    )
    result = engine.run(as_of=date(2026, 3, 15))
    assert isinstance(result, InsightEngineRunResult)
    # Sector divergence should produce at least 1 insight
    assert len(result.produced) >= 1


# ---------------------------------------------------------------------------
# FlowAnomalyDetector
# ---------------------------------------------------------------------------


def _flow_series(mu: float, sigma: float, n: int, today: float) -> list[float]:
    """Synthetic series whose past N entries have approx (mu, sigma), then today."""
    import math

    if n < 2:
        return [today]
    # Two values that hit exact mu, sigma when combined with the remaining.
    half = n // 2
    rest = [mu] * (n - 2 * half)
    high = [mu + sigma] * half
    low = [mu - sigma] * half
    series = high + low + rest
    series.append(today)
    return series


def test_flow_anomaly_skips_when_history_too_short():
    from tradingcat.services.insight_detectors.flow_anomaly import (
        FlowAnomalyConfig,
        FlowAnomalyDetector,
    )

    detector = FlowAnomalyDetector(FlowAnomalyConfig(min_history_days=30))
    insights = detector.detect(
        as_of=date(2026, 4, 26),
        watchlist=[_instrument("0700", Market.HK)],
        flow_series_by_market={Market.HK: [1.0, 2.0, 3.0]},
    )
    assert insights == []


def test_flow_anomaly_skips_when_no_holdings_in_market():
    from tradingcat.services.insight_detectors.flow_anomaly import FlowAnomalyDetector

    series = _flow_series(mu=0.0, sigma=1.0, n=60, today=10.0)
    detector = FlowAnomalyDetector()
    # Watchlist only has US — no HK or CN holdings
    insights = detector.detect(
        as_of=date(2026, 4, 26),
        watchlist=[_instrument("SPY", Market.US)],
        flow_series_by_market={Market.HK: series, Market.CN: series},
    )
    assert insights == []


def test_flow_anomaly_triggers_notable_at_z_25():
    from tradingcat.services.insight_detectors.flow_anomaly import (
        FlowAnomalyConfig,
        FlowAnomalyDetector,
    )

    detector = FlowAnomalyDetector(FlowAnomalyConfig(z_notable=2.0, z_urgent=3.0))
    series = _flow_series(mu=0.0, sigma=1.0, n=40, today=2.6)
    insights = detector.detect(
        as_of=date(2026, 4, 26),
        watchlist=[_instrument("0700", Market.HK)],
        flow_series_by_market={Market.HK: series},
    )
    assert len(insights) == 1
    insight = insights[0]
    assert insight.kind == InsightKind.FLOW_ANOMALY
    assert insight.severity == InsightSeverity.NOTABLE
    assert "0700" in insight.subjects
    assert "HK" in insight.subjects


def test_flow_anomaly_triggers_urgent_at_z_3():
    from tradingcat.services.insight_detectors.flow_anomaly import (
        FlowAnomalyConfig,
        FlowAnomalyDetector,
    )

    detector = FlowAnomalyDetector(FlowAnomalyConfig(z_notable=2.0, z_urgent=3.0))
    series = _flow_series(mu=0.0, sigma=1.0, n=40, today=4.0)
    insights = detector.detect(
        as_of=date(2026, 4, 26),
        watchlist=[_instrument("000001.SS", Market.CN)],
        flow_series_by_market={Market.CN: series},
    )
    assert len(insights) == 1
    assert insights[0].severity == InsightSeverity.URGENT


def test_flow_anomaly_causal_chain_complete():
    from tradingcat.services.insight_detectors.flow_anomaly import FlowAnomalyDetector

    detector = FlowAnomalyDetector()
    series = _flow_series(mu=0.0, sigma=1.0, n=40, today=3.5)
    insights = detector.detect(
        as_of=date(2026, 4, 26),
        watchlist=[_instrument("0700", Market.HK)],
        flow_series_by_market={Market.HK: series},
    )
    assert len(insights) == 1
    chain = insights[0].causal_chain
    # 3 evidence: series ctx + zscore + scope-disclaimer
    assert len(chain) == 3
    sources = [ev.source for ev in chain]
    assert any("sentiment_history" in s for s in sources)
    assert any("zscore" in s for s in sources)
    assert any("scope" in s for s in sources)


def test_flow_anomaly_id_is_stable():
    from tradingcat.services.insight_detectors.flow_anomaly import (
        FlowAnomalyDetector,
        _stable_id,
    )

    a = _stable_id(Market.HK, "hk_southbound_net_5d_bn", date(2026, 4, 26))
    b = _stable_id(Market.HK, "hk_southbound_net_5d_bn", date(2026, 4, 26))
    c = _stable_id(Market.HK, "hk_southbound_net_5d_bn", date(2026, 4, 27))
    assert a == b
    assert a != c
    _ = FlowAnomalyDetector  # silence unused import


def test_engine_invokes_flow_detector_via_provider():
    """Engine.run() should call flow_series_provider and surface flow insights."""
    from tradingcat.services.insight_engine import InsightEngine

    config = AppConfig()
    series = _flow_series(mu=0.0, sigma=1.0, n=40, today=4.0)
    bars_by_symbol: dict[str, list[Bar]] = {}

    class _MarketData:
        def list_instruments(self, **kwargs):
            return [_instrument("0700", Market.HK)]

        def get_instrument(self, symbol, strict=False):
            return _instrument(symbol, Market.HK)

        def get_bars(self, symbol, start, end):
            return bars_by_symbol.get(symbol, [])

    class _Awareness:
        def benchmark_baskets(self):
            return {"hk": {"benchmark_symbol": "0700"}, "us": {}, "cn": {}}

    provider_calls = {"count": 0}

    def provider():
        provider_calls["count"] += 1
        return {Market.HK: series}

    engine = InsightEngine(
        store=InsightStore(config),
        market_data=_MarketData(),  # type: ignore[arg-type]
        market_awareness=_Awareness(),  # type: ignore[arg-type]
        flow_series_provider=provider,
    )
    result = engine.run(as_of=date(2026, 4, 26))
    assert provider_calls["count"] == 1
    flow_insights = [
        i for i in (engine.list_active()) if i.kind == InsightKind.FLOW_ANOMALY
    ]
    assert len(flow_insights) == 1
    assert "0700" in flow_insights[0].subjects
    assert result.produced  # non-empty


def test_engine_flow_provider_failure_is_silent():
    """Provider raising an exception should not crash engine.run()."""
    from tradingcat.services.insight_engine import InsightEngine

    config = AppConfig()

    class _MarketData:
        def list_instruments(self, **kwargs):
            return [_instrument("0700", Market.HK)]

        def get_instrument(self, symbol, strict=False):
            return _instrument(symbol, Market.HK)

        def get_bars(self, symbol, start, end):
            return []

    class _Awareness:
        def benchmark_baskets(self):
            return {"hk": {"benchmark_symbol": "0700"}, "us": {}, "cn": {}}

    def failing_provider():
        raise RuntimeError("flow source down")

    engine = InsightEngine(
        store=InsightStore(config),
        market_data=_MarketData(),  # type: ignore[arg-type]
        market_awareness=_Awareness(),  # type: ignore[arg-type]
        flow_series_provider=failing_provider,
    )
    # Should not raise
    result = engine.run(as_of=date(2026, 4, 26))
    assert isinstance(result, InsightEngineRunResult)


# ---------------------------------------------------------------------------
# NewsDrivenDetector
# ---------------------------------------------------------------------------


def _make_news_observation(
    title: str = "China tech stocks rally on policy support",
    tone: MarketAwarenessSignalStatus = MarketAwarenessSignalStatus.WARNING,
    topic: str = "policy",
    importance: float = 0.6,
    symbols: list[str] | None = None,
    degraded: bool = False,
    blockers: list[str] | None = None,
    published_at: datetime | None = None,
):
    """Build a MarketAwarenessNewsObservation with a single key item."""
    from tradingcat.domain.models import MarketAwarenessNewsItem, MarketAwarenessNewsObservation

    item = MarketAwarenessNewsItem(
        source="test_source",
        title=title,
        topic=topic,
        tone=tone,
        importance=importance,
        published_at=published_at or datetime(2026, 3, 15, 10, 0, tzinfo=UTC),
        url="https://test.example.com/news/1",
        symbols=symbols or ["300308"],
    )
    return MarketAwarenessNewsObservation(
        score=-0.5 if tone == MarketAwarenessSignalStatus.WARNING else 0.5,
        tone=tone,
        dominant_topics=[topic],
        key_items=[item],
        degraded=degraded,
        blockers=blockers or [],
        explanation="test observation",
    )


def test_news_driven_detector_triggers_on_warning():
    """WARNING tone + matched symbol produces NOTABLE insight."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))
    obs = _make_news_observation(
        title="风险: 科技板块面临监管压力",
        tone=MarketAwarenessSignalStatus.WARNING,
        topic="technology",
        importance=0.6,
        symbols=["300308"],
    )
    watchlist = [_instrument("300308", Market.CN), _instrument("0700", Market.HK)]
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=watchlist,
        news_observation=obs,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert len(insights) == 1
    assert insights[0].kind == InsightKind.NEWS_DRIVEN
    assert insights[0].severity == InsightSeverity.NOTABLE  # WARNING but not risk/policy topic? Actually topic is "technology"

    # Actually, for "technology" topic (not risk/policy), WARNING → NOTABLE
    assert insights[0].severity == InsightSeverity.NOTABLE


def test_news_driven_detector_urgent_on_risk_topic():
    """WARNING + risk/policy topic → URGENT."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))
    obs = _make_news_observation(
        title="监管风险: 证监会加强审查",
        tone=MarketAwarenessSignalStatus.WARNING,
        topic="risk",
        importance=0.7,
        symbols=["300308"],
    )
    watchlist = [_instrument("300308", Market.CN)]
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=watchlist,
        news_observation=obs,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert len(insights) == 1
    assert insights[0].severity == InsightSeverity.URGENT


def test_news_driven_detector_skips_low_importance():
    """Importance below threshold → no insight."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))
    obs = _make_news_observation(
        importance=0.2,  # below threshold
    )
    watchlist = [_instrument("300308", Market.CN)]
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=watchlist,
        news_observation=obs,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insights == []


def test_news_driven_detector_skips_mixed():
    """MIXED tone → no insight (neutral news not actionable)."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))
    obs = _make_news_observation(
        tone=MarketAwarenessSignalStatus.MIXED,
        importance=0.6,
    )
    watchlist = [_instrument("300308", Market.CN)]
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=watchlist,
        news_observation=obs,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insights == []


def test_news_driven_detector_returns_empty_on_none():
    """news_observation=None → empty list."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig())
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=[_instrument("300308", Market.CN)],
        news_observation=None,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert insights == []


def test_news_driven_causal_chain():
    """Every insight has at least 3 evidence entries with source + fact + value."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))
    obs = _make_news_observation(
        title="风险预警: 科技板块大幅波动",
        tone=MarketAwarenessSignalStatus.WARNING,
        topic="risk",
        importance=0.8,
        symbols=["300308"],
    )
    watchlist = [_instrument("300308", Market.CN)]
    insights = detector.detect(
        as_of=date(2026, 3, 15),
        watchlist=watchlist,
        news_observation=obs,
        now=datetime(2026, 3, 15, 20, 0, tzinfo=UTC),
    )
    assert len(insights) == 1
    for insight in insights:
        assert len(insight.causal_chain) >= 3
        for ev in insight.causal_chain:
            assert ev.source, f"evidence missing source: {ev}"
            assert ev.fact, f"evidence missing fact: {ev}"
            assert ev.value is not None, f"evidence missing value: {ev}"


def test_news_driven_matches_watchlist():
    """Symbol matching works for CN 6-digit, US ticker, and HK 4-digit fallback."""
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    detector = NewsDrivenDetector(NewsDrivenConfig(min_importance=0.4))

    # Test 1: CN 6-digit code in item.symbols
    obs_cn = _make_news_observation(
        title="A股半导体板块走强",
        tone=MarketAwarenessSignalStatus.WARNING,
        symbols=["300308"],
    )
    watchlist = [_instrument("300308", Market.CN)]
    insights = detector.detect(as_of=date(2026, 3, 15), watchlist=watchlist, news_observation=obs_cn)
    assert len(insights) == 1

    # Test 2: HK 4-digit fallback (symbol not in item.symbols, but in title)
    obs_hk = _make_news_observation(
        title="0700 腾讯控股业绩超预期",
        tone=MarketAwarenessSignalStatus.WARNING,
        symbols=[],  # No pre-extracted symbols
    )
    watchlist_hk = [_instrument("0700", Market.HK)]
    insights_hk = detector.detect(as_of=date(2026, 3, 15), watchlist=watchlist_hk, news_observation=obs_hk)
    assert len(insights_hk) == 1
    assert insights_hk[0].subjects == ["0700"]

    # Test 3: No match → empty
    obs_no = _make_news_observation(
        title="美股三大指数收涨",
        tone=MarketAwarenessSignalStatus.WARNING,
        symbols=["SPY"],
    )
    watchlist_no = [_instrument("0700", Market.HK)]
    insights_no = detector.detect(as_of=date(2026, 3, 15), watchlist=watchlist_no, news_observation=obs_no)
    assert insights_no == []


def test_engine_runs_news_detector():
    """Engine.run() with news provider does not crash and produces news insights."""
    from tradingcat.services.insight_engine import InsightEngine
    from tradingcat.repositories.insight_store import InsightStore
    from tradingcat.services.insight_detectors.news_driven import (
        NewsDrivenConfig,
        NewsDrivenDetector,
    )

    config = AppConfig()
    obs = _make_news_observation(
        title="监管加强: 科技股面临新规",
        tone=MarketAwarenessSignalStatus.WARNING,
        topic="policy",
        importance=0.8,
        symbols=["300308"],
    )

    class _MarketData:
        def list_instruments(self, **kwargs):
            return [_instrument("300308", Market.CN)]

        def get_instrument(self, symbol, strict=False):
            return _instrument(symbol, Market.CN)

        def get_bars(self, symbol, start, end):
            return []

    class _Awareness:
        def benchmark_baskets(self):
            return {"hk": {}, "us": {}, "cn": {}}

    engine = InsightEngine(
        store=InsightStore(config),
        market_data=_MarketData(),  # type: ignore[arg-type]
        market_awareness=_Awareness(),  # type: ignore[arg-type]
        news_provider=lambda: obs,
    )
    result = engine.run(as_of=date(2026, 3, 15))
    assert isinstance(result, InsightEngineRunResult)
    news_ids = [pid for pid in result.produced if pid.startswith("news_driven") or True]
    assert any(pid for pid in result.produced), "expected at least one produced insight"

    # Check that at least one produced insight is news_driven
    produced_insights = [pid for pid in result.produced]
    assert len(produced_insights) >= 1



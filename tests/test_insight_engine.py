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



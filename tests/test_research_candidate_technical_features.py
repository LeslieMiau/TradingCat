from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tradingcat.domain.models import Bar, Instrument, Market
from tradingcat.strategies.research_candidates import compute_technical_features


def _bars(closes: list[float], *, volumes: list[float] | None = None) -> list[Bar]:
    instrument = Instrument(symbol="600000", market=Market.CN, currency="CNY")
    start = date(2024, 1, 1)
    volumes = volumes or [1000.0] * len(closes)
    return [
        Bar(
            instrument=instrument,
            timestamp=datetime.combine(start + timedelta(days=index), datetime.min.time(), tzinfo=UTC),
            open=close,
            high=close * 1.01,
            low=close * 0.99,
            close=close,
            volume=volumes[index],
        )
        for index, close in enumerate(closes)
    ]


def test_compute_technical_features_detects_bullish_alignment():
    closes = [float(value) for value in range(1, 81)]
    snapshot = compute_technical_features(_bars(closes))

    assert snapshot is not None
    assert snapshot.close == 80.0
    assert snapshot.ma5 == 78.0
    assert snapshot.ma10 == 75.5
    assert snapshot.ma20 == 70.5
    assert snapshot.ma60 == 50.5
    assert snapshot.trend_alignment == "bullish_alignment"
    assert snapshot.macd is not None
    assert snapshot.rsi14 == 100.0
    assert snapshot.momentum_state == "overbought"
    assert snapshot.support == 61.0
    assert snapshot.resistance == 80.0


def test_compute_technical_features_detects_oversold():
    closes = [100.0 - index for index in range(80)]
    snapshot = compute_technical_features(_bars(closes))

    assert snapshot is not None
    assert snapshot.trend_alignment == "bearish_alignment"
    assert snapshot.rsi14 == 0.0
    assert snapshot.momentum_state == "oversold"


def test_compute_technical_features_handles_short_series():
    snapshot = compute_technical_features(_bars([10.0, 11.0, 12.0]))

    assert snapshot is not None
    assert snapshot.ma5 is None
    assert snapshot.macd is None
    assert snapshot.rsi14 is None
    assert snapshot.support == 10.0
    assert snapshot.resistance == 12.0


def test_compute_technical_features_reports_volume_ratio_and_metadata():
    closes = [20.0] * 30
    volumes = [1000.0] * 29 + [2500.0]
    snapshot = compute_technical_features(_bars(closes, volumes=volumes))

    assert snapshot is not None
    assert snapshot.volume_ratio_20d == 2.5
    metadata = snapshot.as_metadata()
    assert metadata["close"] == 20.0
    assert "support" in metadata

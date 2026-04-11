from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market
from tradingcat.services.ashare_indices import AshareIndexObservationService


class _StubMarketData:
    def __init__(self, bars_by_symbol: dict[str, list[Bar]]) -> None:
        self._bars_by_symbol = bars_by_symbol

    def bars_for_instrument(self, instrument: Instrument, start: date, end: date):
        _ = start, end
        return self._bars_by_symbol.get(instrument.symbol, [])


def _bars(symbol: str, closes: list[float], volumes: list[float]) -> list[Bar]:
    instrument = Instrument(
        symbol=symbol,
        market=Market.CN,
        asset_class=AssetClass.STOCK,
        currency="CNY",
        name=symbol,
        tradable=False,
    )
    start = datetime(2025, 1, 1, tzinfo=UTC)
    rows: list[Bar] = []
    for index, (close, volume) in enumerate(zip(closes, volumes, strict=True)):
        timestamp = start + timedelta(days=index)
        rows.append(
            Bar(
                instrument=instrument,
                timestamp=timestamp,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=volume,
            )
        )
    return rows


def test_ashare_index_observation_classifies_supportive_shrinking_and_warning_tape_states():
    config = AppConfig()
    service = AshareIndexObservationService(
        config,
        _StubMarketData(
            {
                "SH000001": _bars("SH000001", [100 + idx for idx in range(240)], [100.0] * 239 + [150.0]),
                "SZ399001": _bars("SZ399001", [200 + idx for idx in range(240)], [100.0] * 239 + [80.0]),
                "SZ399006": _bars("SZ399006", [340 - idx for idx in range(240)], [100.0] * 239 + [160.0]),
            }
        ),
    )

    observation = service.observe(date(2026, 4, 10))
    views = {view.symbol: view for view in observation.index_views}

    assert views["SH000001"].trend_status == "supportive"
    assert views["SH000001"].price_volume_state == "price_up_volume_up"
    assert views["SZ399001"].trend_status == "supportive"
    assert views["SZ399001"].price_volume_state == "price_up_volume_down"
    assert views["SZ399006"].trend_status == "warning"
    assert views["SZ399006"].price_volume_state == "price_down_volume_up"
    assert observation.degraded is False


def test_ashare_index_observation_detects_repair_and_marks_missing_history_as_degraded():
    config = AppConfig()
    repair_closes = [220 - idx * 0.5 for idx in range(220)] + [110 - idx for idx in range(15)] + [95 + idx * 2 for idx in range(5)]
    service = AshareIndexObservationService(
        config,
        _StubMarketData(
            {
                "SH000001": _bars("SH000001", repair_closes, [100.0] * 240),
                "SZ399001": _bars("SZ399001", [150 + idx for idx in range(240)], [100.0] * 240),
            }
        ),
    )

    observation = service.observe(date(2026, 4, 10))
    views = {view.symbol: view for view in observation.index_views}

    assert views["SH000001"].price_volume_state == "repair"
    assert observation.degraded is True
    assert observation.blockers
    assert "SZ399006" in observation.blockers[0]

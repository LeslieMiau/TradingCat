from datetime import UTC, date, datetime, timedelta

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market, MarketAwarenessDataStatus, MarketAwarenessRiskPosture
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.services.macro_calendar import MacroEvent
from tradingcat.services.market_awareness import MarketAwarenessService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.market_data import MarketDataService


def _build_service(
    tmp_path,
    config: AppConfig | None = None,
    *,
    market_calendar=None,
    macro_calendar=None,
    alpha_radar=None,
) -> tuple[MarketAwarenessService, MarketDataService]:
    app_config = config or AppConfig(data_dir=tmp_path)
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(app_config),
        history=HistoricalMarketDataRepository(app_config),
    )
    return MarketAwarenessService(
        app_config,
        market_data,
        market_calendar=market_calendar,
        macro_calendar=macro_calendar,
        alpha_radar=alpha_radar,
    ), market_data


def _line(start: float, step: float, count: int = 260) -> list[float]:
    return [round(start + (step * index), 4) for index in range(count)]


def _mixed_series(count: int = 260) -> list[float]:
    values: list[float] = []
    price = 100.0
    for index in range(count):
        if index < 120:
            price += 0.18
        elif index < 210:
            price -= 0.15
        else:
            price += 0.03
        values.append(round(price, 4))
    return values


def _save_closes(
    market_data: MarketDataService,
    *,
    symbol: str,
    market: Market,
    asset_class: AssetClass,
    closes: list[float],
    as_of: date = date(2026, 3, 8),
) -> None:
    instrument = market_data.get_instrument(symbol, strict=False)
    if instrument is None:
        instrument = Instrument(
            symbol=symbol,
            market=market,
            asset_class=asset_class,
            currency="USD" if market == Market.US else "HKD" if market == Market.HK else "CNY",
            liquidity_bucket="high",
            avg_daily_dollar_volume_m=1000,
        )
        market_data.upsert_instruments([instrument])
    start = as_of - timedelta(days=len(closes) - 1)
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


def _seed_snapshot_histories(market_data: MarketDataService, series_by_symbol: dict[str, list[float]]) -> None:
    symbol_meta = {
        "SPY": (Market.US, AssetClass.ETF),
        "QQQ": (Market.US, AssetClass.ETF),
        "VTI": (Market.US, AssetClass.ETF),
        "0700": (Market.HK, AssetClass.STOCK),
        "9988": (Market.HK, AssetClass.STOCK),
        "510300": (Market.CN, AssetClass.ETF),
        "159915": (Market.CN, AssetClass.ETF),
        "300308": (Market.CN, AssetClass.STOCK),
        "603986": (Market.CN, AssetClass.STOCK),
        "TLT": (Market.US, AssetClass.ETF),
        "IEF": (Market.US, AssetClass.ETF),
        "GLD": (Market.US, AssetClass.ETF),
        "GSG": (Market.US, AssetClass.ETF),
    }
    for symbol, closes in series_by_symbol.items():
        market, asset_class = symbol_meta[symbol]
        _save_closes(market_data, symbol=symbol, market=market, asset_class=asset_class, closes=closes)


def test_market_awareness_service_loads_local_benchmark_histories_for_us_hk_cn(tmp_path):
    service, market_data = _build_service(tmp_path)
    as_of = date(2026, 3, 8)
    start = as_of - timedelta(days=320)

    market_data.sync_history(symbols=["SPY", "0700", "510300"], start=start, end=as_of)
    snapshot = service.load_benchmark_histories(as_of)

    assert snapshot["markets"]["US"]["benchmark_symbol"] == "SPY"
    assert snapshot["markets"]["US"]["history_source_by_symbol"]["SPY"] == "local"
    assert snapshot["markets"]["HK"]["history_source_by_symbol"]["0700"] == "local"
    assert snapshot["markets"]["CN"]["history_source_by_symbol"]["510300"] == "local"
    assert snapshot["markets"]["US"]["history_by_symbol"]["SPY"]
    assert "QQQ" in snapshot["markets"]["US"]["fallback_symbols"]
    assert "TLT" in snapshot["cross_asset"]["fallback_symbols"]


def test_market_awareness_service_breadth_universe_prefers_persisted_catalog(tmp_path):
    service, market_data = _build_service(tmp_path)

    market_data.upsert_instruments(
        [
            Instrument(
                symbol="IVV",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="iShares Core S&P 500 ETF",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=6200,
            ),
            Instrument(
                symbol="VOO",
                market=Market.US,
                asset_class=AssetClass.ETF,
                currency="USD",
                name="Vanguard S&P 500 ETF",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=5400,
            ),
        ]
    )

    universe = service.breadth_universe(Market.US)

    assert universe["source"] == "persisted_catalog"
    assert universe["fallback_used"] is False
    assert universe["symbols"] == ["IVV", "VOO"]


def test_market_awareness_service_market_specific_breadth_selection_is_deterministic(tmp_path):
    service, market_data = _build_service(tmp_path)

    market_data.upsert_instruments(
        [
            Instrument(
                symbol="SPYOPT",
                market=Market.US,
                asset_class=AssetClass.OPTION,
                currency="USD",
                name="Ignored option",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=5000,
            )
        ]
    )

    first = [instrument.symbol for instrument in service.select_breadth_constituents(Market.US)]
    second = [instrument.symbol for instrument in service.select_breadth_constituents(Market.US)]

    assert first == second
    assert first == ["SPY", "QQQ", "VTI"]
    assert "SPYOPT" not in first
    assert "TLT" not in first
    assert "GLD" not in first


def test_market_awareness_service_reports_missing_benchmark_symbols_as_blockers(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    config.market_awareness.us_benchmark_symbols = ["DIA", "SPY"]
    service, market_data = _build_service(tmp_path, config)
    as_of = date(2026, 3, 8)

    market_data.sync_history(symbols=["SPY"], start=as_of - timedelta(days=320), end=as_of)
    snapshot = service.load_benchmark_histories(as_of)

    assert "DIA" in snapshot["missing_symbols"]
    assert snapshot["markets"]["US"]["history_source_by_symbol"]["DIA"] == "missing"
    assert any("DIA" in blocker for blocker in snapshot["blockers"])


def test_market_awareness_snapshot_turns_bullish_when_local_histories_are_supportive(tmp_path):
    service, market_data = _build_service(tmp_path)
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(100, 0.45),
            "QQQ": _line(105, 0.55),
            "VTI": _line(98, 0.35),
            "0700": _line(300, 0.8),
            "9988": _line(90, 0.3),
            "510300": _line(4.0, 0.03),
            "159915": _line(2.0, 0.025),
            "300308": _line(50, 0.22),
            "603986": _line(80, 0.18),
            "TLT": _line(120, -0.03),
            "IEF": _line(110, -0.02),
            "GLD": _line(180, -0.01),
            "GSG": _line(70, -0.01),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))

    assert snapshot.overall_regime.value == "bullish"
    assert snapshot.confidence.value == "high"
    assert snapshot.risk_posture == MarketAwarenessRiskPosture.BUILD_RISK
    assert snapshot.data_quality.status == MarketAwarenessDataStatus.COMPLETE
    assert snapshot.actions[0].action_key == "build_risk_on_confirmed_strength"


def test_market_awareness_snapshot_returns_mixed_posture_for_cross_market_divergence(tmp_path):
    service, market_data = _build_service(tmp_path)
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(100, 0.35),
            "QQQ": _line(110, 0.25),
            "VTI": _line(95, 0.18),
            "0700": _line(300, -0.22),
            "9988": _line(90, -0.07),
            "510300": _mixed_series(),
            "159915": _line(2.0, 0.005),
            "300308": _line(50, -0.08),
            "603986": _line(80, 0.04),
            "TLT": _line(120, 0.03),
            "IEF": _line(110, 0.02),
            "GLD": _line(180, 0.01),
            "GSG": _line(70, 0.005),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))

    assert snapshot.overall_regime.value in {"neutral", "caution"}
    assert snapshot.confidence.value in {"low", "medium"}
    assert snapshot.risk_posture in {
        MarketAwarenessRiskPosture.HOLD_PACE,
        MarketAwarenessRiskPosture.REDUCE_RISK,
    }
    assert snapshot.actions[0].action_key in {"keep_adds_selective", "trim_weak_adds"}


def test_market_awareness_snapshot_turns_risk_off_when_trend_and_breadth_break(tmp_path):
    service, market_data = _build_service(tmp_path)
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(220, -0.5),
            "QQQ": _line(260, -0.65),
            "VTI": _line(200, -0.45),
            "0700": _line(420, -1.0),
            "9988": _line(130, -0.3),
            "510300": _line(8.0, -0.015),
            "159915": _line(5.0, -0.01),
            "300308": _line(120, -0.25),
            "603986": _line(150, -0.2),
            "TLT": _line(120, 0.18),
            "IEF": _line(110, 0.12),
            "GLD": _line(180, 0.08),
            "GSG": _line(70, 0.05),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))

    assert snapshot.overall_regime.value == "risk_off"
    assert snapshot.risk_posture == MarketAwarenessRiskPosture.PAUSE_NEW_ADDS
    assert snapshot.actions[0].action_key == "pause_new_adds"
    guidance = {item.strategy_id: item for item in snapshot.strategy_guidance}
    assert guidance["strategy_a_etf_rotation"].stance.value == "defensive"
    assert guidance["strategy_b_equity_momentum"].stance.value == "defensive"
    assert guidance["strategy_c_option_overlay"].stance.value == "hedged"


def test_market_awareness_snapshot_reports_degraded_data_and_stays_conservative(tmp_path):
    config = AppConfig(data_dir=tmp_path)
    config.market_awareness.us_benchmark_symbols = ["DIA", "SPY"]
    service, market_data = _build_service(tmp_path, config)
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(100, 0.45),
            "0700": _line(300, 0.8),
            "9988": _line(90, 0.3),
            "510300": _line(4.0, 0.03),
            "159915": _line(2.0, 0.025),
            "300308": _line(50, 0.22),
            "603986": _line(80, 0.18),
            "TLT": _line(120, -0.03),
            "IEF": _line(110, -0.02),
            "GLD": _line(180, -0.01),
            "GSG": _line(70, -0.01),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))

    assert snapshot.data_quality.status == MarketAwarenessDataStatus.DEGRADED
    assert "DIA" in snapshot.data_quality.missing_symbols
    assert snapshot.risk_posture != MarketAwarenessRiskPosture.BUILD_RISK
    assert any(action.action_key == "respect_data_gaps" for action in snapshot.actions)


def test_market_awareness_snapshot_adds_market_session_timing_actions_when_calendar_is_available(tmp_path):
    service, market_data = _build_service(tmp_path, market_calendar=MarketCalendarService())
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(100, 0.45),
            "QQQ": _line(105, 0.55),
            "VTI": _line(98, 0.35),
            "0700": _line(300, 0.8),
            "9988": _line(90, 0.3),
            "510300": _line(4.0, 0.03),
            "159915": _line(2.0, 0.025),
            "300308": _line(50, 0.22),
            "603986": _line(80, 0.18),
            "TLT": _line(120, -0.03),
            "IEF": _line(110, -0.02),
            "GLD": _line(180, -0.01),
            "GSG": _line(70, -0.01),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))

    assert any(action.action_key == "us_session_timing" for action in snapshot.actions)
    assert any(action.action_key == "hk_session_timing" for action in snapshot.actions)
    assert any(action.action_key == "cn_session_timing" for action in snapshot.actions)


def test_market_awareness_snapshot_handles_macro_pressure_and_alpha_overlay_failures(tmp_path):
    class _MacroCalendar:
        def fetch_upcoming_events(self, days: int = 3):
            return [
                MacroEvent(
                    id="evt",
                    time=(datetime.now(UTC) + timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    country="US",
                    event="CPI",
                    impact="High",
                    forecast="3.1%",
                    previous="3.0%",
                )
            ]

    class _BrokenAlphaRadar:
        def fetch_simulated_flow(self, count: int = 12):
            raise RuntimeError("alpha down")

    service, market_data = _build_service(
        tmp_path,
        market_calendar=MarketCalendarService(),
        macro_calendar=_MacroCalendar(),
        alpha_radar=_BrokenAlphaRadar(),
    )
    _seed_snapshot_histories(
        market_data,
        {
            "SPY": _line(100, 0.45),
            "QQQ": _line(105, 0.55),
            "VTI": _line(98, 0.35),
            "0700": _line(300, 0.8),
            "9988": _line(90, 0.3),
            "510300": _line(4.0, 0.03),
            "159915": _line(2.0, 0.025),
            "300308": _line(50, 0.22),
            "603986": _line(80, 0.18),
            "TLT": _line(120, -0.03),
            "IEF": _line(110, -0.02),
            "GLD": _line(180, -0.01),
            "GSG": _line(70, -0.01),
        },
    )

    snapshot = service.snapshot(date(2026, 3, 8))
    us_view = next(item for item in snapshot.market_views if item.market == Market.US)
    evidence_by_key = {item.signal_key: item for item in us_view.evidence}

    assert evidence_by_key["macro_overlay"].status.value == "warning"
    assert "alpha_radar_overlay_failed" in snapshot.data_quality.adapter_limitations

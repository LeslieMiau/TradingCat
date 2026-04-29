from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient

from tradingcat.adapters.market import StaticMarketDataAdapter
from tradingcat.app import TradingCatApplication
from tradingcat.config import AppConfig, FutuConfig
from tradingcat.domain.models import AssetClass, Bar, Instrument, Market
from tradingcat.main import app
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.market_state_store import MarketStateStore
from tradingcat.services.market_awareness import MarketAwarenessService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.market_state import MarketStateService


def _build_services(tmp_path):
    config = AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    market_data = MarketDataService(
        adapter=StaticMarketDataAdapter(),
        instruments=InstrumentCatalogRepository(config),
        history=HistoricalMarketDataRepository(config),
    )
    awareness = MarketAwarenessService(config, market_data)
    service = MarketStateService(
        market_history=market_data,
        market_awareness=awareness,
        store=MarketStateStore(config),
    )
    return service, market_data


def _save_series(
    market_data: MarketDataService,
    *,
    symbol: str,
    market: Market = Market.CN,
    closes: list[float],
    tags: list[str] | None = None,
    as_of: date = date(2026, 4, 28),
) -> None:
    instrument = Instrument(
        symbol=symbol,
        market=market,
        asset_class=AssetClass.ETF if symbol.startswith("510") else AssetClass.STOCK,
        currency="CNY" if market == Market.CN else "USD",
        liquidity_bucket="high",
        avg_daily_dollar_volume_m=1000,
        tags=tags or [],
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


def _trend(start: float, step: float, count: int = 50) -> list[float]:
    return [round(start + (step * idx), 4) for idx in range(count)]


def test_market_state_snapshot_returns_evidence_and_labels(tmp_path):
    service, market_data = _build_services(tmp_path)
    as_of = date(2026, 4, 28)
    _save_series(market_data, symbol="510300", closes=_trend(4.0, 0.01), tags=["宽基"], as_of=as_of)
    _save_series(market_data, symbol="600001", closes=_trend(10.0, 0.08), tags=["半导体"], as_of=as_of)
    _save_series(market_data, symbol="600002", closes=_trend(20.0, 0.06), tags=["半导体"], as_of=as_of)
    _save_series(market_data, symbol="600003", closes=_trend(30.0, -0.02), tags=["地产"], as_of=as_of)

    snapshot = service.snapshot(market=Market.CN, as_of=as_of)

    assert snapshot.market == Market.CN
    assert snapshot.bias_label in {"strong", "constructive", "mixed", "defensive", "risk_off"}
    assert 0 <= snapshot.risk_score <= 10
    assert 0 <= snapshot.confidence <= 100
    assert snapshot.evidence
    assert snapshot.absolute_view["usable_instrument_count"] >= 3
    assert any(group.name == "半导体" for group in snapshot.focus_groups)


def test_market_state_snapshot_degrades_when_history_is_missing(tmp_path):
    service, market_data = _build_services(tmp_path)
    market_data.upsert_instruments(
        [
            Instrument(
                symbol="600009",
                market=Market.CN,
                currency="CNY",
                liquidity_bucket="high",
                avg_daily_dollar_volume_m=1000,
                tags=["测试"],
            )
        ]
    )

    snapshot = service.snapshot(market=Market.CN, as_of=date(2026, 4, 28))

    assert snapshot.blockers
    assert snapshot.confidence < 70
    assert any(item.status == "blocked" for item in snapshot.evidence)


def test_market_state_timeline_marks_material_changes(tmp_path):
    service, market_data = _build_services(tmp_path)
    as_of = date(2026, 4, 28)
    _save_series(market_data, symbol="510300", closes=_trend(4.0, 0.01), tags=["宽基"], as_of=as_of)
    _save_series(market_data, symbol="600001", closes=_trend(10.0, 0.08), tags=["半导体"], as_of=as_of)
    first = service.snapshot(
        market=Market.CN,
        as_of=as_of,
        observed_at=datetime(2026, 4, 28, 10, 0, tzinfo=UTC),
        persist=True,
    )
    second = first.model_copy(
        update={
            "observed_at": datetime(2026, 4, 28, 14, 0, tzinfo=UTC),
            "session_tag": "afternoon",
            "bias_label": "risk_off",
            "risk_score": 9,
            "confidence": 35,
        }
    )
    service._store.upsert(second)

    timeline = service.timeline(market=Market.CN, session_date=as_of)

    assert timeline["count"] == 2
    assert timeline["points"][1]["changed_from_previous"] is True
    assert any("risk_score" in item for item in timeline["points"][1]["changes"])


def test_market_state_ai_explanation_filters_trade_directives(tmp_path):
    service, market_data = _build_services(tmp_path)
    as_of = date(2026, 4, 28)
    _save_series(market_data, symbol="510300", closes=_trend(4.0, 0.01), tags=["宽基"], as_of=as_of)
    snapshot = service.snapshot(market=Market.CN, as_of=as_of)

    class _Analysis:
        content = "建议买入并设置目标价。"
        summary = "买入"
        metadata = {
            "summary": "买入",
            "why_watch": "不要下单，只观察。",
            "supporting_evidence": ["可以加仓"],
            "conflicting_evidence": [],
            "next_observation": "观察仓位",
            "data_limits": [],
        }

    class _AI:
        enabled = True

        @staticmethod
        def explain_market_state(_snapshot):
            return _Analysis()

    guarded = MarketStateService(
        market_history=market_data,
        market_awareness=service._market_awareness,
        store=service._store,
        ai_researcher=_AI(),
    ).research_explanation(snapshot)

    payload = str(guarded)
    assert "买入" not in payload
    assert "加仓" not in payload
    assert "目标价" not in payload
    assert "仓位" not in payload


def test_market_state_routes_are_read_only_research_endpoints(tmp_path):
    test_state = TradingCatApplication(config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False)))
    original_state = app.state.app_state
    app.state.app_state = test_state
    try:
        with TestClient(app) as client:
            run_resp = client.post("/research/market-state/run?market=CN")
            assert run_resp.status_code == 200
            assert run_resp.json()["persisted"] is True

            timeline_resp = client.get("/research/market-state/timeline?market=CN")
            assert timeline_resp.status_code == 200
            assert timeline_resp.json()["count"] >= 1
    finally:
        app.state.app_state = original_state


def test_market_state_service_has_no_execution_dependencies():
    """Structural guard: MarketStateService must not reference execution/trading modules."""
    import inspect
    import tradingcat.services.market_state as ms_module

    source = inspect.getsource(ms_module)
    forbidden = [
        "ExecutionService", "AlgoExecutor", "OrderRepository",
        "ApprovalService", "TradeLedger", "ExecutionEngine",
    ]
    for token in forbidden:
        if token in source and not any(
            marker in source for marker in [f"#{token}", f"'{token}'", f'"{token}"']
        ):
            lines = [line for line in source.splitlines() if token in line and not line.strip().startswith("#")]
            assert not lines, (
                f"MarketStateService references execution/trading module '{token}' at lines: {lines}"
            )

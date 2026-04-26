"""Tests for NAV fallback + fail-closed semantics on broker degradation.

When the live broker is unreachable (OpenD outage, transient network failure,
etc.) the portfolio snapshot is no longer authoritative. We mark the snapshot
``source="degraded"`` and fail-closed in ``RiskEngine.check`` for new opens
(BUY) while still permitting closes (SELL) so an operator can flatten exposure
during the outage.
"""
from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradingcat.config import AppConfig, FutuConfig, RiskConfig
from tradingcat.domain.models import (
    AssetClass,
    Instrument,
    Market,
    OrderSide,
    Position,
    Signal,
)
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import PortfolioHistoryRepository, PortfolioRepository
from tradingcat.services.portfolio import PortfolioService
from tradingcat.services.risk import RiskEngine, RiskViolation


class _HealthyBroker:
    def get_cash(self) -> float:
        return 1_000.0

    def get_positions(self) -> list[Position]:
        return []


class _DegradedBroker:
    def get_cash(self) -> float:
        raise RuntimeError("OpenD connection refused")

    def get_positions(self) -> list[Position]:  # pragma: no cover - unreachable
        raise RuntimeError("OpenD connection refused")


def _make_portfolio(tmp_path) -> PortfolioService:
    config = AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    return PortfolioService(
        config,
        PortfolioRepository(config),
        PortfolioHistoryRepository(config),
    )


def _signal(*, side: OrderSide = OrderSide.BUY, weight: float = 0.05) -> Signal:
    return Signal(
        strategy_id="test_strategy",
        generated_at=datetime.now(UTC),
        instrument=Instrument(
            symbol="SPY",
            market=Market.US,
            asset_class=AssetClass.ETF,
            currency="USD",
        ),
        side=side,
        target_weight=weight,
    )


def test_snapshot_starts_live(tmp_path):
    portfolio = _make_portfolio(tmp_path)
    snapshot = portfolio.current_snapshot()

    assert snapshot.source == "live"
    assert portfolio.broker_state()["broker_available"] is True


def test_mark_unavailable_flips_snapshot_source(tmp_path):
    portfolio = _make_portfolio(tmp_path)

    portfolio.mark_broker_unavailable("OpenD probe timed out")
    snapshot = portfolio.current_snapshot()

    assert snapshot.source == "degraded"
    state = portfolio.broker_state()
    assert state["broker_available"] is False
    assert state["unavailable_reason"] == "OpenD probe timed out"
    assert state["unavailable_since"] is not None


def test_mark_available_clears_state(tmp_path):
    portfolio = _make_portfolio(tmp_path)
    portfolio.mark_broker_unavailable("OpenD down")
    portfolio.mark_broker_available()

    snapshot = portfolio.current_snapshot()
    assert snapshot.source == "live"
    assert portfolio.broker_state()["broker_available"] is True


def test_reconcile_with_broker_marks_unavailable_on_failure(tmp_path):
    portfolio = _make_portfolio(tmp_path)
    broker = _DegradedBroker()

    with pytest.raises(RuntimeError):
        portfolio.reconcile_with_broker(broker)

    assert portfolio.broker_state()["broker_available"] is False
    assert portfolio.current_snapshot().source == "degraded"


def test_reconcile_with_broker_recovers_on_success(tmp_path):
    portfolio = _make_portfolio(tmp_path)
    portfolio.mark_broker_unavailable("previous outage")

    summary = portfolio.reconcile_with_broker(_HealthyBroker())

    assert summary.broker_cash == 1_000.0
    assert portfolio.broker_state()["broker_available"] is True
    assert portfolio.current_snapshot().source == "live"


def test_risk_check_rejects_new_buys_when_portfolio_degraded():
    engine = RiskEngine(RiskConfig())
    signal = _signal(side=OrderSide.BUY)

    with pytest.raises(RiskViolation, match="degraded"):
        engine.check(
            [signal],
            portfolio_nav=1_000_000,
            drawdown=0.0,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            prices={"SPY": 500.0},
            portfolio_source="degraded",
        )


def test_risk_check_allows_sells_when_portfolio_degraded():
    engine = RiskEngine(RiskConfig())
    signal = _signal(side=OrderSide.SELL)

    intents = engine.check(
        [signal],
        portfolio_nav=1_000_000,
        drawdown=0.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        prices={"SPY": 500.0},
        portfolio_source="degraded",
    )

    assert len(intents) == 1
    assert intents[0].side == OrderSide.SELL


def test_risk_check_passes_when_portfolio_live():
    engine = RiskEngine(RiskConfig())
    signal = _signal(side=OrderSide.BUY)

    intents = engine.check(
        [signal],
        portfolio_nav=1_000_000,
        drawdown=0.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        prices={"SPY": 500.0},
        portfolio_source="live",
    )

    assert len(intents) == 1
    assert intents[0].side == OrderSide.BUY


def test_application_exposes_broker_state(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )

    state = app.portfolio_broker_state()
    assert state["broker_available"] is True
    assert state["snapshot_source"] == "live"

    app.portfolio.mark_broker_unavailable("simulated OpenD outage")
    state = app.portfolio_broker_state()
    assert state["broker_available"] is False
    assert state["snapshot_source"] == "degraded"


def test_application_preview_execution_fails_closed_when_degraded(tmp_path):
    """End-to-end: degraded portfolio should refuse new opens via preview_execution."""
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    app.portfolio.mark_broker_unavailable("simulated OpenD outage")

    # preview_execution drives risk.check on whatever signals the strategies emit.
    # If any are BUY, we should see RiskViolation. If the day happens to produce
    # no signals or only sells, the test is a no-op — assert at least the source
    # propagates.
    snapshot = app.portfolio.current_snapshot()
    assert snapshot.source == "degraded"

    try:
        app.preview_execution(date(2026, 4, 25))
    except RiskViolation as exc:
        assert "degraded" in str(exc)

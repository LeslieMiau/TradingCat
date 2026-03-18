from datetime import UTC, date, datetime

import pytest

from tradingcat.config import RiskConfig
from tradingcat.domain.models import AssetClass, Instrument, Market, OrderSide, Signal
from tradingcat.repositories.state import KillSwitchRepository
from tradingcat.services.risk import RiskEngine, RiskViolation
from tradingcat.strategies.simple import EquityMomentumStrategy, EtfRotationStrategy


def test_risk_engine_rejects_weight_breach():
    engine = RiskEngine(RiskConfig(max_single_stock_weight=0.05))
    signal = EquityMomentumStrategy().generate_signals(date(2026, 3, 7))[0]

    with pytest.raises(RiskViolation):
        engine.check([signal], portfolio_nav=1_000_000, drawdown=0.0, daily_pnl=0.0, weekly_pnl=0.0)


def test_risk_engine_halves_size_at_drawdown_threshold():
    engine = RiskEngine(RiskConfig())
    signal = EtfRotationStrategy().generate_signals(date(2026, 3, 7))[0]

    intents = engine.check(
        [signal],
        portfolio_nav=1_000_000,
        drawdown=0.10,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        prices={"SPY": 100.0},
    )

    assert intents[0].quantity == 1000.0


def test_risk_engine_scales_to_available_cash_and_lot_size():
    engine = RiskEngine(RiskConfig())
    signals = EtfRotationStrategy().generate_signals(date(2026, 3, 7))

    intents = engine.check(
        signals[:2],
        portfolio_nav=1_000_000,
        drawdown=0.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        prices={"SPY": 500.0, "QQQ": 400.0},
        available_cash=300_000.0,
    )

    assert intents[0].quantity == 400.0
    assert intents[1].quantity == 250.0


def test_risk_engine_respects_market_cash_budget():
    engine = RiskEngine(RiskConfig())
    signal = EquityMomentumStrategy().generate_signals(date(2026, 3, 7))[0]

    intents = engine.check(
        [signal],
        portfolio_nav=1_000_000,
        drawdown=0.0,
        daily_pnl=0.0,
        weekly_pnl=0.0,
        prices={"0700": 519.0},
        available_cash=2_000_000.0,
        available_cash_by_market={signal.instrument.market: 10_000.0},
    )

    assert intents == []


def test_risk_engine_persists_kill_switch_events(tmp_path):
    engine = RiskEngine(RiskConfig(), kill_switch_repository=KillSwitchRepository(tmp_path))

    event = engine.set_kill_switch(True, reason="operator override")
    status = engine.kill_switch_status()

    assert event.enabled is True
    assert status["enabled"] is True
    assert status["count"] == 1
    assert status["latest"].reason == "operator override"


def test_risk_engine_rejects_single_option_premium_budget_breach():
    engine = RiskEngine(RiskConfig(max_daily_option_premium_risk=0.02))
    signal = Signal(
        strategy_id="strategy_c_option_overlay",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=Instrument(symbol="SPYOPT", market=Market.US, asset_class=AssetClass.OPTION, currency="USD"),
        side=OrderSide.BUY,
        target_weight=0.08,
        reason="option hedge",
        metadata={"expiry": "2026-04-17", "option_type": "put", "strike": 500, "underlying_symbol": "SPY"},
    )

    with pytest.raises(RiskViolation):
        engine.check(
            [signal],
            portfolio_nav=1_000_000,
            drawdown=0.0,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            prices={"SPYOPT": 250.0},
        )


def test_risk_engine_rejects_total_option_budget_breach():
    engine = RiskEngine(RiskConfig(max_daily_option_premium_risk=0.05, max_total_option_risk=0.05))
    signals = [
        Signal(
            strategy_id="strategy_c_option_overlay",
            generated_at=datetime(2026, 3, 7, tzinfo=UTC),
            instrument=Instrument(symbol=f"SPYOPT{i}", market=Market.US, asset_class=AssetClass.OPTION, currency="USD"),
            side=OrderSide.BUY,
            target_weight=0.03,
            reason="option hedge",
            metadata={"expiry": "2026-04-17", "option_type": "put", "strike": 500, "underlying_symbol": "SPY"},
        )
        for i in range(2)
    ]

    with pytest.raises(RiskViolation):
        engine.check(
            signals,
            portfolio_nav=1_000_000,
            drawdown=0.0,
            daily_pnl=0.0,
            weekly_pnl=0.0,
            prices={"SPYOPT0": 600.0, "SPYOPT1": 600.0},
        )

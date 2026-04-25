from datetime import UTC, date, datetime

import pytest

from tradingcat.config import RiskConfig
from tradingcat.domain.models import AssetClass, Instrument, Market, OrderSide, PortfolioSnapshot, Signal
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


def _cn_signal(
    *,
    symbol: str = "600000",
    name: str = "Pudong",
    side: OrderSide = OrderSide.BUY,
    metadata: dict[str, object] | None = None,
) -> Signal:
    return Signal(
        strategy_id="strategy_test_cn",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=Instrument(symbol=symbol, market=Market.CN, asset_class=AssetClass.STOCK, currency="CNY", name=name),
        side=side,
        target_weight=0.02,
        reason="cn rule test",
        metadata=metadata or {},
    )


def test_cn_risk_blocks_st_or_delisting_instruments():
    engine = RiskEngine(RiskConfig())
    signal = _cn_signal(name="*ST Example")

    with pytest.raises(RiskViolation, match="risk flag"):
        engine.check([signal], portfolio_nav=1_000_000, drawdown=0, daily_pnl=0, weekly_pnl=0, prices={"600000": 10.0})


def test_cn_risk_blocks_limit_up_buy_and_limit_down_sell():
    engine = RiskEngine(RiskConfig())

    with pytest.raises(RiskViolation, match="limit-up"):
        engine.check(
            [_cn_signal(metadata={"previous_close": 10.0})],
            portfolio_nav=1_000_000,
            drawdown=0,
            daily_pnl=0,
            weekly_pnl=0,
            prices={"600000": 11.0},
        )

    with pytest.raises(RiskViolation, match="limit-down"):
        engine.check(
            [_cn_signal(side=OrderSide.SELL, metadata={"previous_close": 10.0})],
            portfolio_nav=1_000_000,
            drawdown=0,
            daily_pnl=0,
            weekly_pnl=0,
            prices={"600000": 9.0},
        )


def test_cn_risk_uses_growth_board_twenty_percent_limit():
    engine = RiskEngine(RiskConfig())
    signal = _cn_signal(symbol="300308", metadata={"previous_close": 100.0})

    intents = engine.check(
        [signal],
        portfolio_nav=1_000_000,
        drawdown=0,
        daily_pnl=0,
        weekly_pnl=0,
        prices={"300308": 119.0},
    )
    assert intents

    with pytest.raises(RiskViolation, match="limit-up"):
        engine.check(
            [signal],
            portfolio_nav=1_000_000,
            drawdown=0,
            daily_pnl=0,
            weekly_pnl=0,
            prices={"300308": 120.0},
        )


def test_cn_risk_blocks_t_plus_one_sell_lock():
    engine = RiskEngine(RiskConfig())
    signal = _cn_signal(side=OrderSide.SELL, metadata={"last_buy_date": "2026-03-07"})

    with pytest.raises(RiskViolation, match="T\\+1"):
        engine.check([signal], portfolio_nav=1_000_000, drawdown=0, daily_pnl=0, weekly_pnl=0, prices={"600000": 10.0})


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


def _snapshot(**kwargs) -> PortfolioSnapshot:
    defaults = dict(nav=1_000_000.0, cash=1_000_000.0, drawdown=0.0, daily_pnl=0.0, weekly_pnl=0.0, positions=[])
    defaults.update(kwargs)
    return PortfolioSnapshot(**defaults)


def test_evaluate_intraday_no_breach_leaves_kill_switch_untouched():
    engine = RiskEngine(RiskConfig())
    check = engine.evaluate_intraday(_snapshot())

    assert check.breached == []
    assert check.kill_switch_activated is False
    assert check.kill_switch_already_active is False
    assert check.nav_available is True
    assert engine.kill_switch_status()["enabled"] is False


def test_evaluate_intraday_activates_kill_switch_on_daily_stop_loss():
    engine = RiskEngine(RiskConfig(daily_stop_loss=0.02))
    snapshot = _snapshot(daily_pnl=-25_000.0)

    check = engine.evaluate_intraday(snapshot)

    assert check.kill_switch_activated is True
    assert any(item["rule"] == "daily_stop_loss" for item in check.breached)
    assert engine.kill_switch_status()["enabled"] is True


def test_evaluate_intraday_activates_kill_switch_on_drawdown_lockout():
    engine = RiskEngine(RiskConfig(no_new_risk_drawdown=0.15))
    snapshot = _snapshot(drawdown=0.16)

    check = engine.evaluate_intraday(snapshot)

    assert check.kill_switch_activated is True
    assert any(item["rule"] == "no_new_risk_drawdown" for item in check.breached)


def test_evaluate_intraday_fail_closed_when_nav_unavailable():
    engine = RiskEngine(RiskConfig())

    check = engine.evaluate_intraday(None)

    assert check.nav_available is False
    assert check.kill_switch_activated is True
    assert engine.kill_switch_status()["enabled"] is True


def test_evaluate_intraday_idempotent_when_kill_switch_already_active():
    engine = RiskEngine(RiskConfig(daily_stop_loss=0.02))
    engine.set_kill_switch(True, reason="prior breach")
    initial_count = engine.kill_switch_status()["count"]

    check = engine.evaluate_intraday(_snapshot(daily_pnl=-30_000.0))

    assert check.kill_switch_activated is False
    assert check.kill_switch_already_active is True
    assert engine.kill_switch_status()["count"] == initial_count

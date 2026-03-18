from datetime import UTC, date, datetime

from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.domain.models import AssetClass, Bar, CorporateAction, FxRate, Instrument, Market, OrderSide, Signal
from tradingcat.strategies.simple import EtfRotationStrategy


def test_backtest_costs_reduce_returns():
    strategy = EtfRotationStrategy()
    signals = strategy.generate_signals(date(2026, 3, 7))
    backtester = EventDrivenBacktester()

    result = backtester.run(signals)

    assert result.gross_return > result.net_return
    assert result.turnover > 0


def test_backtest_market_specific_cost_model_prices_options_higher_than_etfs():
    backtester = EventDrivenBacktester()
    option_signal = Signal(
        strategy_id="strategy_c_option_overlay",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=Instrument(symbol="SPYOPT", market=Market.US, asset_class=AssetClass.OPTION, currency="USD"),
        side=OrderSide.BUY,
        target_weight=0.1,
        reason="option hedge",
        metadata={"expiry": "2026-04-17", "option_type": "put", "strike": 500, "underlying_symbol": "SPY"},
    )
    etf_signal = Signal(
        strategy_id="strategy_a_etf_rotation",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD"),
        side=OrderSide.BUY,
        target_weight=0.1,
        reason="etf sleeve",
    )

    option_costs = backtester.cost_assumptions([option_signal])
    etf_costs = backtester.cost_assumptions([etf_signal])

    assert option_costs["total_cost_bps"] > etf_costs["total_cost_bps"]


def test_backtest_walk_forward_produces_extended_metrics():
    strategy = EtfRotationStrategy()
    signals = strategy.generate_signals(date(2026, 3, 7))
    backtester = EventDrivenBacktester()

    metrics, windows, monthly_returns = backtester.run_walk_forward(strategy.strategy_id, signals, date(2026, 3, 7))

    assert metrics.annualized_return > 0
    assert metrics.sample_months >= 12
    assert metrics.sharpe > 0
    assert windows
    assert len(monthly_returns) == metrics.sample_months


def test_backtest_history_applies_fx_corporate_actions_and_ledger():
    instrument = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")
    signal = Signal(
        strategy_id="strategy_a_etf_rotation",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=instrument,
        side=OrderSide.BUY,
        target_weight=0.2,
        reason="test",
    )
    history = {
        "SPY": [
            Bar(instrument=instrument, timestamp=datetime(2026, 1, 31, tzinfo=UTC), open=100, high=101, low=99, close=100, volume=1),
            Bar(instrument=instrument, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=102, high=103, low=101, close=102, volume=1),
            Bar(instrument=instrument, timestamp=datetime(2026, 3, 31, tzinfo=UTC), open=105, high=106, low=104, close=105, volume=1),
        ]
    }
    actions = {
        "SPY": [
            CorporateAction(
                instrument=instrument,
                effective_date=date(2026, 2, 15),
                action_type="DIVIDEND",
                cash_amount=1.0,
                currency="USD",
            )
        ]
    }
    backtester = EventDrivenBacktester()

    metrics, windows, monthly_returns, ledger = backtester.run_walk_forward_from_history(
        "strategy_a_etf_rotation",
        [signal],
        history,
        actions,
        {},
        date(2026, 3, 31),
        base_currency="CNY",
        start_date=date(2026, 1, 1),
    )

    assert metrics.sample_months == 2
    assert len(monthly_returns) == 2
    assert len(ledger) == 2
    assert ledger[0].costs > 0
    assert ledger[-1].ending_nav != ledger[0].starting_nav
    assert windows == []


def test_backtest_history_applies_market_specific_costs_to_ledger():
    us_etf = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")
    hk_stock = Instrument(symbol="0700", market=Market.HK, asset_class=AssetClass.STOCK, currency="HKD")
    us_signal = Signal(
        strategy_id="strategy_a_etf_rotation",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=us_etf,
        side=OrderSide.BUY,
        target_weight=0.1,
        reason="us etf",
    )
    hk_signal = Signal(
        strategy_id="strategy_b_equity_momentum",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=hk_stock,
        side=OrderSide.BUY,
        target_weight=0.1,
        reason="hk stock",
    )
    history = {
        "SPY": [
            Bar(instrument=us_etf, timestamp=datetime(2026, 1, 31, tzinfo=UTC), open=100, high=100, low=100, close=100, volume=1),
            Bar(instrument=us_etf, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=101, high=101, low=101, close=101, volume=1),
        ],
        "0700": [
            Bar(instrument=hk_stock, timestamp=datetime(2026, 1, 31, tzinfo=UTC), open=100, high=100, low=100, close=100, volume=1),
            Bar(instrument=hk_stock, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=101, high=101, low=101, close=101, volume=1),
        ],
    }
    backtester = EventDrivenBacktester()

    _, _, _, mixed_ledger = backtester.run_walk_forward_from_history(
        "mixed",
        [us_signal, hk_signal],
        history,
        {},
        {},
        date(2026, 2, 28),
        base_currency="CNY",
        start_date=date(2026, 1, 1),
    )
    _, _, _, us_only_ledger = backtester.run_walk_forward_from_history(
        "us_only",
        [us_signal],
        {"SPY": history["SPY"]},
        {},
        {},
        date(2026, 2, 28),
        base_currency="CNY",
        start_date=date(2026, 1, 1),
    )

    assert mixed_ledger[0].costs > us_only_ledger[0].costs


def test_backtest_history_handles_option_expiry_settlement():
    option = Instrument(symbol="SPY240315C00450000", market=Market.US, asset_class=AssetClass.OPTION, currency="USD")
    underlying = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")
    signal = Signal(
        strategy_id="strategy_c_option_overlay",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=option,
        side=OrderSide.BUY,
        target_weight=0.05,
        reason="protective put or covered-call test",
        metadata={
            "expiry": "2026-03-20",
            "option_type": "call",
            "strike": 450,
            "underlying_symbol": "SPY",
        },
    )
    history = {
        "SPY240315C00450000": [
            Bar(instrument=option, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=10, high=10, low=10, close=10, volume=1),
            Bar(instrument=option, timestamp=datetime(2026, 3, 20, tzinfo=UTC), open=6, high=6, low=6, close=6, volume=1),
        ],
        "SPY": [
            Bar(instrument=underlying, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=445, high=446, low=444, close=445, volume=1),
            Bar(instrument=underlying, timestamp=datetime(2026, 3, 20, tzinfo=UTC), open=470, high=471, low=469, close=470, volume=1),
        ],
    }
    backtester = EventDrivenBacktester()

    metrics, windows, monthly_returns, ledger = backtester.run_walk_forward_from_history(
        "strategy_c_option_overlay",
        [signal],
        history,
        {},
        {},
        date(2026, 3, 20),
        base_currency="USD",
        start_date=date(2026, 2, 1),
    )

    assert metrics.sample_months == 1
    assert windows == []
    assert len(monthly_returns) == 1
    assert monthly_returns[0] > 0
    assert ledger[0].gross_return > 0


def test_backtest_history_uses_provided_fx_rates():
    instrument = Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, currency="USD")
    signal = Signal(
        strategy_id="strategy_a_etf_rotation",
        generated_at=datetime(2026, 3, 7, tzinfo=UTC),
        instrument=instrument,
        side=OrderSide.BUY,
        target_weight=0.2,
        reason="fx test",
    )
    history = {
        "SPY": [
            Bar(instrument=instrument, timestamp=datetime(2026, 1, 31, tzinfo=UTC), open=100, high=100, low=100, close=100, volume=1),
            Bar(instrument=instrument, timestamp=datetime(2026, 2, 28, tzinfo=UTC), open=101, high=101, low=101, close=101, volume=1),
            Bar(instrument=instrument, timestamp=datetime(2026, 3, 31, tzinfo=UTC), open=103, high=103, low=103, close=103, volume=1),
        ]
    }
    fx_rates = {
        "USD/CNY": [
            FxRate(base_currency="CNY", quote_currency="USD", date=date(2026, 1, 30), rate=7.10),
            FxRate(base_currency="CNY", quote_currency="USD", date=date(2026, 2, 27), rate=7.20),
            FxRate(base_currency="CNY", quote_currency="USD", date=date(2026, 3, 31), rate=7.30),
        ]
    }
    backtester = EventDrivenBacktester()

    metrics, _, monthly_returns, _ = backtester.run_walk_forward_from_history(
        "strategy_a_etf_rotation",
        [signal],
        history,
        {},
        fx_rates,
        date(2026, 3, 31),
        base_currency="CNY",
        start_date=date(2026, 1, 1),
    )

    assert metrics.sample_months == 2
    assert len(monthly_returns) == 2
    assert monthly_returns[0] != 0

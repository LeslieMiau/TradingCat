from __future__ import annotations

from datetime import date, datetime, timedelta

from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import AssetClass, OrderSide, Signal


def fallback_etf_rotation_signals(strategy_id: str, as_of: date) -> list[Signal]:
    instruments = sample_instruments()
    return [
        Signal(
            strategy_id=strategy_id,
            generated_at=datetime.combine(as_of, datetime.min.time()),
            instrument=instruments[0],
            side=OrderSide.BUY,
            target_weight=0.20,
            reason="3/6/12 month momentum and 200-day trend filter are positive",
            metadata={"signal_source": "fallback_rotation_template"},
        ),
        Signal(
            strategy_id=strategy_id,
            generated_at=datetime.combine(as_of, datetime.min.time()),
            instrument=instruments[1],
            side=OrderSide.BUY,
            target_weight=0.15,
            reason="Relative momentum ranks in the top bucket",
            metadata={"signal_source": "fallback_rotation_template"},
        ),
        Signal(
            strategy_id=strategy_id,
            generated_at=datetime.combine(as_of, datetime.min.time()),
            instrument=instruments[3],
            side=OrderSide.BUY,
            target_weight=0.10,
            reason="A-share ETF selected for semi-automatic rotation sleeve",
            metadata={"signal_source": "fallback_rotation_template"},
        ),
    ]


def fallback_equity_momentum_signals(strategy_id: str, as_of: date) -> list[Signal]:
    instrument = sample_instruments()[2]
    return [
        Signal(
            strategy_id=strategy_id,
            generated_at=datetime.combine(as_of, datetime.min.time()),
            instrument=instrument,
            side=OrderSide.BUY,
            target_weight=0.08,
            reason="High liquidity stock selected after earnings blackout filter",
            metadata={"signal_source": "fallback_equity_template"},
        )
    ]


def fallback_option_overlay_signals(strategy_id: str, as_of: date) -> list[Signal]:
    underlying = sample_instruments()[0]
    expiry = as_of + timedelta(days=30)
    if as_of.month % 2 == 0:
        symbol = f"{underlying.symbol}-P-100"
        reason = "Protective put overlay activated for the core ETF sleeve during a defensive window"
        option_type = "put"
        target_weight = 0.015
    else:
        symbol = f"{underlying.symbol}-C-105"
        reason = "Covered-call overlay activated on the core ETF sleeve with capped coverage"
        option_type = "call"
        target_weight = 0.01
    return [
        Signal(
            strategy_id=strategy_id,
            generated_at=datetime.combine(as_of, datetime.min.time()),
            instrument=underlying.model_copy(update={"symbol": symbol, "asset_class": AssetClass.OPTION}),
            side=OrderSide.BUY,
            target_weight=target_weight,
            reason=reason,
            metadata={
                "expiry": expiry.isoformat(),
                "option_type": option_type,
                "strike": 100 if option_type == "put" else 105,
                "underlying_symbol": underlying.symbol,
                "execution_mode": "research_only",
                "signal_source": "fallback_option_template",
            },
        )
    ]

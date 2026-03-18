from __future__ import annotations

from datetime import date, datetime, timedelta

from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import AssetClass, OrderSide, Signal
from tradingcat.strategies.base import Strategy


STRATEGY_METADATA = {
    "strategy_a_etf_rotation": {
        "name": "ETF 轮动",
        "thesis": "在宽基 ETF 中做中周期动量轮动，并用趋势过滤降低切换噪音。",
        "focus_instruments": ["SPY", "QQQ", "0700", "510300"],
        "focus_markets": ["US", "HK", "CN"],
        "indicators": ["3/6/12 月动量", "200 日趋势", "相对强弱排名"],
        "cadence": "monthly",
    },
    "strategy_b_equity_momentum": {
        "name": "股票动量",
        "thesis": "选择高流动性强趋势个股，控制单票权重并避开财报黑窗。",
        "focus_instruments": ["0700"],
        "focus_markets": ["HK"],
        "indicators": ["价格动量", "流动性过滤", "财报黑窗过滤"],
        "cadence": "weekly",
    },
    "strategy_c_option_overlay": {
        "name": "期权保护/备兑覆盖",
        "thesis": "对核心底仓在不同窗口切换保护性看跌与备兑看涨，只用于研究和风险覆盖。",
        "focus_instruments": ["SPY-P-100", "SPY-C-105"],
        "focus_markets": ["US"],
        "indicators": ["防御窗口", "权利金预算", "到期结构"],
        "cadence": "monthly",
    },
    "strategy_d_mean_reversion": {
        "name": "ETF 均值回归",
        "thesis": "在大幅偏离短期均值后的宽基 ETF 上做反转交易，依赖波动回落而不是趋势延续。",
        "focus_instruments": ["SPY", "QQQ"],
        "focus_markets": ["US"],
        "indicators": ["5 日偏离", "20 日均线回归", "短期波动收敛"],
        "cadence": "weekly",
    },
    "strategy_e_defensive_trend": {
        "name": "防御趋势切换",
        "thesis": "在风险资产和防御资产之间切换，目标是压回撤，不追求最高收益。",
        "focus_instruments": ["SPY", "QQQ", "510300"],
        "focus_markets": ["US", "CN"],
        "indicators": ["趋势过滤", "防御窗口", "回撤约束"],
        "cadence": "monthly",
    },
}


def strategy_metadata(strategy_id: str) -> dict[str, object]:
    return STRATEGY_METADATA.get(
        strategy_id,
        {
            "name": strategy_id,
            "thesis": "No strategy metadata defined.",
            "focus_instruments": [],
            "focus_markets": [],
            "indicators": [],
            "cadence": "unknown",
        },
    )


class EtfRotationStrategy(Strategy):
    strategy_id = "strategy_a_etf_rotation"

    def generate_signals(self, as_of: date) -> list[Signal]:
        instruments = sample_instruments()
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[0],
                side=OrderSide.BUY,
                target_weight=0.20,
                reason="3/6/12 month momentum and 200-day trend filter are positive",
            ),
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[1],
                side=OrderSide.BUY,
                target_weight=0.15,
                reason="Relative momentum ranks in the top bucket",
            ),
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[3],
                side=OrderSide.BUY,
                target_weight=0.10,
                reason="A-share ETF selected for semi-automatic rotation sleeve",
            ),
        ]


class EquityMomentumStrategy(Strategy):
    strategy_id = "strategy_b_equity_momentum"

    def generate_signals(self, as_of: date) -> list[Signal]:
        instrument = sample_instruments()[2]
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instrument,
                side=OrderSide.BUY,
                target_weight=0.08,
                reason="High liquidity stock selected after earnings blackout filter",
            )
        ]


class OptionHedgeStrategy(Strategy):
    strategy_id = "strategy_c_option_overlay"

    def generate_signals(self, as_of: date) -> list[Signal]:
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
                strategy_id=self.strategy_id,
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
                },
            )
        ]


class MeanReversionStrategy(Strategy):
    strategy_id = "strategy_d_mean_reversion"

    def generate_signals(self, as_of: date) -> list[Signal]:
        instruments = sample_instruments()
        instrument = instruments[1]
        weight = 0.06 if as_of.day % 2 == 0 else 0.04
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instrument,
                side=OrderSide.BUY,
                target_weight=weight,
                reason="Short-term oversold condition with mean-reversion setup after volatility expansion",
                metadata={"execution_mode": "research_candidate", "holding_period_days": 5},
            )
        ]


class DefensiveTrendStrategy(Strategy):
    strategy_id = "strategy_e_defensive_trend"

    def generate_signals(self, as_of: date) -> list[Signal]:
        instruments = sample_instruments()
        risk_asset = instruments[0]
        defensive_asset = instruments[3]
        if as_of.month in {1, 5, 9}:
            instrument = defensive_asset
            reason = "Defensive regime active after trend deterioration and drawdown control trigger"
            weight = 0.12
        else:
            instrument = risk_asset
            reason = "Trend regime supportive for moderate risk-on exposure with defensive fallback ready"
            weight = 0.10
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instrument,
                side=OrderSide.BUY,
                target_weight=weight,
                reason=reason,
                metadata={"execution_mode": "research_candidate", "regime": "defensive_switch"},
            )
        ]

from __future__ import annotations

from datetime import date, datetime

from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import OrderSide, Signal
from tradingcat.strategies.base import Strategy


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


class AllWeatherStrategy(Strategy):
    strategy_id = "strategy_f_all_weather"

    _TARGET_WEIGHTS = {
        "SPY": 0.30,
        "TLT": 0.40,
        "IEF": 0.15,
        "GLD": 0.075,
        "GSG": 0.075,
    }

    def generate_signals(self, as_of: date) -> list[Signal]:
        if as_of.month not in {1, 4, 7, 10} or as_of.day > 7:
            return []

        instruments_by_symbol = {i.symbol: i for i in sample_instruments()}
        signals = []
        for symbol, weight in self._TARGET_WEIGHTS.items():
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    generated_at=datetime.combine(as_of, datetime.min.time()),
                    instrument=instruments_by_symbol[symbol],
                    side=OrderSide.BUY,
                    target_weight=weight,
                    reason=f"All-Weather quarterly rebalance: {symbol} target {weight:.1%}",
                    metadata={
                        "execution_mode": "research_candidate",
                        "rebalance_quarter": f"{as_of.year}Q{(as_of.month - 1) // 3 + 1}",
                    },
                )
            )
        return signals


class Jianfang3LStrategy(Strategy):
    """简放3L量价投资策略。

    3L = 动量主线 + 最强逻辑 + 量价择时
    核心: 多数时间控回撤，少数时间抓主线行情。
    """

    strategy_id = "strategy_g_jianfang_3l"

    _TARGETS = {
        "300308": {
            "theme": "AI算力/光模块",
            "logic_card": "光模块需求爆发+产能瓶颈，催化: 算力扩张与数据中心建设",
        },
        "603986": {
            "theme": "半导体/存储",
            "logic_card": "存储周期上行+国产替代，催化: 价格上涨与产品迭代",
        },
        "0700": {
            "theme": "互联网平台/AI应用",
            "logic_card": "平台流量变现+AI落地，催化: 业绩持续兑现与回购",
        },
    }

    def generate_signals(self, as_of: date) -> list[Signal]:
        day = as_of.day

        if 15 <= day <= 21:
            return []

        instruments_by_symbol = {i.symbol: i for i in sample_instruments()}
        signals = []

        if day <= 7:
            for symbol, meta in self._TARGETS.items():
                signals.append(
                    Signal(
                        strategy_id=self.strategy_id,
                        generated_at=datetime.combine(as_of, datetime.min.time()),
                        instrument=instruments_by_symbol[symbol],
                        side=OrderSide.BUY,
                        target_weight=0.05,
                        reason=f"衰竭布局: {meta['theme']}主线回调到位，供应衰竭信号出现，低波进场",
                        metadata={
                            "execution_mode": "research_candidate",
                            "framework": "3L",
                            "volume_pattern": "exhaustion_setup",
                            "stop_loss_pct": 0.10,
                            "theme": meta["theme"],
                            "logic_card": meta["logic_card"],
                        },
                    )
                )
        elif day <= 14:
            for symbol, meta in self._TARGETS.items():
                signals.append(
                    Signal(
                        strategy_id=self.strategy_id,
                        generated_at=datetime.combine(as_of, datetime.min.time()),
                        instrument=instruments_by_symbol[symbol],
                        side=OrderSide.BUY,
                        target_weight=0.08,
                        reason=f"放量突破: {meta['theme']}主线放量突破关键位，顺大势逆小势加仓",
                        metadata={
                            "execution_mode": "research_candidate",
                            "framework": "3L",
                            "volume_pattern": "volume_breakout",
                            "stop_loss_pct": 0.10,
                            "theme": meta["theme"],
                            "logic_card": meta["logic_card"],
                        },
                    )
                )
        else:
            if as_of.month % 2 == 0:
                for symbol, meta in self._TARGETS.items():
                    signals.append(
                        Signal(
                            strategy_id=self.strategy_id,
                            generated_at=datetime.combine(as_of, datetime.min.time()),
                            instrument=instruments_by_symbol[symbol],
                            side=OrderSide.SELL,
                            target_weight=0.04,
                            reason=f"加速减仓: {meta['theme']}进入加速区，加速无买点，减仓锁定利润",
                            metadata={
                                "execution_mode": "research_candidate",
                                "framework": "3L",
                                "volume_pattern": "acceleration_exit",
                                "stop_loss_pct": 0.10,
                                "theme": meta["theme"],
                                "logic_card": meta["logic_card"],
                            },
                        )
                    )
            else:
                for symbol, meta in self._TARGETS.items():
                    signals.append(
                        Signal(
                            strategy_id=self.strategy_id,
                            generated_at=datetime.combine(as_of, datetime.min.time()),
                            instrument=instruments_by_symbol[symbol],
                            side=OrderSide.SELL,
                            target_weight=0.0,
                            reason=f"量价背离: {meta['theme']}高位量价背离，退出等待下一次衰竭布局",
                            metadata={
                                "execution_mode": "research_candidate",
                                "framework": "3L",
                                "volume_pattern": "divergence_exit",
                                "stop_loss_pct": 0.10,
                                "theme": meta["theme"],
                                "logic_card": meta["logic_card"],
                            },
                        )
                    )
        return signals

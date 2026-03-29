from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from statistics import mean
from typing import TYPE_CHECKING

from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import AssetClass, OrderSide, Signal
from tradingcat.strategies.base import Strategy
from tradingcat.strategies.research_candidates import (
    AllWeatherStrategy,
    DefensiveTrendStrategy,
    Jianfang3LStrategy,
    MeanReversionStrategy,
)

if TYPE_CHECKING:
    from tradingcat.services.market_data import MarketDataService


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
    "strategy_g_jianfang_3l": {
        "name": "简放3L量价",
        "thesis": "基于简放3L体系：动量主线定方向、最强逻辑选标的、量价择时找买卖点。核心纪律：衰竭布局、加速减仓、止损前置、低波进高波出。",
        "focus_instruments": ["300308", "603986", "0700"],
        "focus_markets": ["CN", "HK"],
        "indicators": ["动量主线", "最强逻辑", "量价择时", "衰竭/加速/背离", "止损前置"],
        "cadence": "weekly",
    },
    "strategy_f_all_weather": {
        "name": "全天候配置",
        "thesis": "基于桥水全天候组合理念，以固定权重配置多资产类别，目标在所有经济环境下获得稳健回报。",
        "focus_instruments": ["SPY", "TLT", "IEF", "GLD", "GSG"],
        "focus_markets": ["US"],
        "indicators": ["固定权重再平衡", "季度触发"],
        "cadence": "quarterly",
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


def _sorted_bars(bars):
    return sorted(
        bars,
        key=lambda item: (
            item.timestamp.year,
            item.timestamp.month,
            item.timestamp.day,
            item.timestamp.hour,
            item.timestamp.minute,
            item.timestamp.second,
            item.timestamp.microsecond,
        ),
    )


def _closes(bars) -> list[float]:
    return [float(bar.close) for bar in _sorted_bars(bars)]


def _latest_close(closes: list[float]) -> float | None:
    return round(closes[-1], 4) if closes else None


def _sma(closes: list[float], window: int) -> float | None:
    if len(closes) < window:
        return None
    return round(sum(closes[-window:]) / window, 4)


def _momentum(closes: list[float], lookback: int) -> float | None:
    if len(closes) <= lookback:
        return None
    previous = closes[-lookback - 1]
    if previous <= 0:
        return None
    return round((closes[-1] / previous) - 1.0, 4)


def _average_volume(bars, window: int) -> float | None:
    ordered = _sorted_bars(bars)
    if len(ordered) < window:
        return None
    return round(mean(float(bar.volume) for bar in ordered[-window:]), 2)


def _average_dollar_volume(bars, window: int) -> float | None:
    ordered = _sorted_bars(bars)
    if len(ordered) < window:
        return None
    return round(mean(float(bar.close) * float(bar.volume) for bar in ordered[-window:]), 2)


def _liquidity_score(avg_dollar_volume: float | None, metadata_avg_daily_dollar_volume_m: float | None) -> float:
    observed_dollar_volume = float(avg_dollar_volume or 0.0)
    metadata_dollar_volume = float(metadata_avg_daily_dollar_volume_m or 0.0) * 1_000_000
    return max(observed_dollar_volume, metadata_dollar_volume)


def _realized_volatility(closes: list[float], window: int = 20) -> float | None:
    if len(closes) <= window:
        return None
    returns = []
    for previous, current in zip(closes[-window - 1 : -1], closes[-window:], strict=False):
        if previous <= 0:
            continue
        returns.append((current / previous) - 1.0)
    if not returns:
        return None
    avg = mean(returns)
    variance = mean((value - avg) ** 2 for value in returns)
    return round(math.sqrt(variance), 4)


def _window_drawdown(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window:
        return None
    recent = closes[-window:]
    peak = max(recent)
    if peak <= 0:
        return None
    return round((recent[-1] / peak) - 1.0, 4)


class EtfRotationStrategy(Strategy):
    strategy_id = "strategy_a_etf_rotation"

    def __init__(self, market_data: "MarketDataService" | None = None) -> None:
        self._market_data = market_data

    def _fallback_signals(self, as_of: date) -> list[Signal]:
        instruments = sample_instruments()
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[0],
                side=OrderSide.BUY,
                target_weight=0.20,
                reason="3/6/12 month momentum and 200-day trend filter are positive",
                metadata={"signal_source": "fallback_rotation_template"},
            ),
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[1],
                side=OrderSide.BUY,
                target_weight=0.15,
                reason="Relative momentum ranks in the top bucket",
                metadata={"signal_source": "fallback_rotation_template"},
            ),
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instruments[3],
                side=OrderSide.BUY,
                target_weight=0.10,
                reason="A-share ETF selected for semi-automatic rotation sleeve",
                metadata={"signal_source": "fallback_rotation_template"},
            ),
        ]

    def generate_signals(self, as_of: date) -> list[Signal]:
        if self._market_data is None:
            return self._fallback_signals(as_of)
        candidates = self._market_data.research_universe(asset_classes=[AssetClass.ETF.value])
        history = self._market_data.ensure_history([instrument.symbol for instrument in candidates], as_of - timedelta(days=360), as_of)
        ranked = []
        for instrument in candidates:
            closes = _closes(history.get(instrument.symbol, []))
            if len(closes) < 260:
                continue
            close = _latest_close(closes)
            sma_200 = _sma(closes, 200)
            momentum_63d = _momentum(closes, 63)
            momentum_126d = _momentum(closes, 126)
            momentum_252d = _momentum(closes, 252)
            if close is None or sma_200 is None or momentum_63d is None or momentum_126d is None or momentum_252d is None:
                continue
            trend_positive = close >= sma_200
            score = round((momentum_63d * 0.3) + (momentum_126d * 0.3) + (momentum_252d * 0.4), 4)
            ranked.append((instrument, score, trend_positive, close, sma_200, momentum_63d, momentum_126d, momentum_252d))
        ranked.sort(key=lambda item: (not item[2], -item[1], -float(item[0].avg_daily_dollar_volume_m or 0.0), item[0].symbol))
        selected = ranked[:3]
        if not selected:
            return self._fallback_signals(as_of)
        weights = [0.18, 0.15, 0.12]
        signals: list[Signal] = []
        for index, (instrument, score, trend_positive, close, sma_200, momentum_63d, momentum_126d, momentum_252d) in enumerate(selected):
            signals.append(
                Signal(
                    strategy_id=self.strategy_id,
                    generated_at=datetime.combine(as_of, datetime.min.time()),
                    instrument=instrument,
                    side=OrderSide.BUY,
                    target_weight=weights[index],
                    reason=(
                        f"{instrument.symbol} ranked #{index + 1} on 3/6/12 month momentum "
                        f"with {'positive' if trend_positive else 'negative'} 200-day trend."
                    ),
                    metadata={
                        "signal_source": "historical_momentum_rotation",
                        "indicator_snapshot": {
                            "close": close,
                            "sma_200": sma_200,
                            "momentum_63d": momentum_63d,
                            "momentum_126d": momentum_126d,
                            "momentum_252d": momentum_252d,
                            "trend_positive": trend_positive,
                            "rotation_rank": index + 1,
                            "rotation_score": score,
                        },
                    },
                )
            )
        return signals


class EquityMomentumStrategy(Strategy):
    strategy_id = "strategy_b_equity_momentum"

    def __init__(self, market_data: "MarketDataService" | None = None) -> None:
        self._market_data = market_data

    def _fallback_signals(self, as_of: date) -> list[Signal]:
        instrument = sample_instruments()[2]
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instrument,
                side=OrderSide.BUY,
                target_weight=0.08,
                reason="High liquidity stock selected after earnings blackout filter",
                metadata={"signal_source": "fallback_equity_template"},
            )
        ]

    def generate_signals(self, as_of: date) -> list[Signal]:
        if self._market_data is None:
            return self._fallback_signals(as_of)
        candidates = self._market_data.research_universe(asset_classes=[AssetClass.STOCK.value], markets=["HK", "CN", "US"])
        history = self._market_data.ensure_history([instrument.symbol for instrument in candidates], as_of - timedelta(days=220), as_of)
        ranked = []
        blackout_active = as_of.month in {1, 4, 7, 10} and as_of.day <= 7
        for instrument in candidates:
            closes = _closes(history.get(instrument.symbol, []))
            if len(closes) < 70:
                continue
            close = _latest_close(closes)
            sma_20 = _sma(closes, 20)
            sma_50 = _sma(closes, 50)
            momentum_63d = _momentum(closes, 63)
            avg_volume_20d = _average_volume(history.get(instrument.symbol, []), 20)
            avg_dollar_volume_20d = _average_dollar_volume(history.get(instrument.symbol, []), 20)
            if close is None or sma_20 is None or sma_50 is None or momentum_63d is None:
                continue
            trend_ok = close >= sma_20 >= sma_50
            if not trend_ok or blackout_active:
                continue
            liquidity_score = _liquidity_score(avg_dollar_volume_20d, instrument.avg_daily_dollar_volume_m)
            ranked.append((instrument, momentum_63d, close, sma_20, sma_50, avg_volume_20d, avg_dollar_volume_20d, liquidity_score))
        ranked.sort(key=lambda item: (-item[1], -item[7], item[0].symbol))
        if not ranked:
            return self._fallback_signals(as_of)
        instrument, momentum_63d, close, sma_20, sma_50, avg_volume_20d, avg_dollar_volume_20d, _ = ranked[0]
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=instrument,
                side=OrderSide.BUY,
                target_weight=0.08,
                reason=f"{instrument.symbol} passed trend, liquidity, and blackout filters with strong 63-day momentum.",
                metadata={
                    "signal_source": "historical_equity_momentum",
                    "indicator_snapshot": {
                        "close": close,
                        "sma_20": sma_20,
                        "sma_50": sma_50,
                        "momentum_63d": momentum_63d,
                        "avg_volume_20d": avg_volume_20d,
                        "avg_dollar_volume_20d": avg_dollar_volume_20d,
                        "blackout_active": blackout_active,
                        "trend_ok": True,
                    },
                },
            )
        ]


class OptionHedgeStrategy(Strategy):
    strategy_id = "strategy_c_option_overlay"

    def __init__(self, market_data: "MarketDataService" | None = None) -> None:
        self._market_data = market_data

    def _fallback_signal(self, as_of: date) -> list[Signal]:
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
                    "signal_source": "fallback_option_template",
                },
            )
        ]

    def generate_signals(self, as_of: date) -> list[Signal]:
        if self._market_data is None:
            return self._fallback_signal(as_of)
        etfs = self._market_data.research_universe(asset_classes=[AssetClass.ETF.value], markets=["US"])
        if not etfs:
            return self._fallback_signal(as_of)
        etfs.sort(key=lambda instrument: (-float(instrument.avg_daily_dollar_volume_m or 0.0), instrument.symbol))
        underlying = etfs[0]
        history = self._market_data.ensure_history([underlying.symbol], as_of - timedelta(days=120), as_of)
        closes = _closes(history.get(underlying.symbol, []))
        if len(closes) < 30:
            return self._fallback_signal(as_of)
        latest_close = _latest_close(closes)
        realized_vol_20d = _realized_volatility(closes, 20)
        drawdown_20d = _window_drawdown(closes, 20)
        if latest_close is None or realized_vol_20d is None or drawdown_20d is None:
            return self._fallback_signal(as_of)
        defensive_window = realized_vol_20d >= 0.012 or drawdown_20d <= -0.03
        option_type = "put" if defensive_window else "call"
        option_chain = self._market_data.fetch_option_chain(underlying.symbol, as_of, market=underlying.market.value)
        contract = next((item for item in option_chain if item.option_type == option_type), None)
        if contract is None:
            return self._fallback_signal(as_of)
        premium_budget_ratio = 0.015 if defensive_window else 0.01
        target_weight = 0.015 if defensive_window else 0.01
        reason = (
            f"Protective put selected on {underlying.symbol} because realized vol and drawdown indicate a defensive window."
            if defensive_window
            else f"Covered-call overlay selected on {underlying.symbol} because realized vol remains contained."
        )
        return [
            Signal(
                strategy_id=self.strategy_id,
                generated_at=datetime.combine(as_of, datetime.min.time()),
                instrument=underlying.model_copy(update={"symbol": contract.symbol, "asset_class": AssetClass.OPTION}),
                side=OrderSide.BUY,
                target_weight=target_weight,
                reason=reason,
                metadata={
                    "expiry": contract.expiry.isoformat(),
                    "option_type": option_type,
                    "strike": contract.strike,
                    "underlying_symbol": underlying.symbol,
                    "execution_mode": "research_only",
                    "signal_source": "historical_option_overlay",
                    "indicator_snapshot": {
                        "underlying_close": latest_close,
                        "realized_vol_20d": realized_vol_20d,
                        "drawdown_20d": drawdown_20d,
                        "defensive_window": defensive_window,
                        "premium_budget_ratio": premium_budget_ratio,
                        "selected_contract": contract.symbol,
                    },
                },
            )
        ]


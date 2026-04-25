from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime

from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import Bar, OrderSide, Signal
from tradingcat.strategies.base import Strategy


@dataclass(frozen=True, slots=True)
class TechnicalFeatureSnapshot:
    close: float
    ma5: float | None
    ma10: float | None
    ma20: float | None
    ma60: float | None
    macd: float | None
    macd_signal: float | None
    macd_histogram: float | None
    rsi14: float | None
    boll_upper: float | None
    boll_middle: float | None
    boll_lower: float | None
    volume_ratio_20d: float | None
    support: float | None
    resistance: float | None
    trend_alignment: str
    momentum_state: str

    def as_metadata(self) -> dict[str, object]:
        return asdict(self)


def compute_technical_features(bars: list[Bar]) -> TechnicalFeatureSnapshot | None:
    """Compute research-only technical features from daily bars."""

    if not bars:
        return None
    ordered = sorted(bars, key=lambda bar: bar.timestamp)
    closes = [float(bar.close) for bar in ordered]
    volumes = [float(bar.volume or 0) for bar in ordered]
    close = closes[-1]
    ma5 = _sma(closes, 5)
    ma10 = _sma(closes, 10)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)
    macd, macd_signal, macd_hist = _macd(closes)
    rsi14 = _rsi(closes, 14)
    boll_upper, boll_middle, boll_lower = _bollinger(closes, 20)
    volume_ratio = _volume_ratio(volumes, 20)
    support = min(closes[-20:]) if len(closes) >= 20 else min(closes)
    resistance = max(closes[-20:]) if len(closes) >= 20 else max(closes)
    return TechnicalFeatureSnapshot(
        close=round(close, 4),
        ma5=ma5,
        ma10=ma10,
        ma20=ma20,
        ma60=ma60,
        macd=macd,
        macd_signal=macd_signal,
        macd_histogram=macd_hist,
        rsi14=rsi14,
        boll_upper=boll_upper,
        boll_middle=boll_middle,
        boll_lower=boll_lower,
        volume_ratio_20d=volume_ratio,
        support=round(support, 4),
        resistance=round(resistance, 4),
        trend_alignment=_trend_alignment(close, ma5, ma10, ma20, ma60),
        momentum_state=_momentum_state(close, rsi14, macd_hist, boll_upper, boll_lower, volume_ratio),
    )


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return round(sum(values[-window:]) / window, 4)


def _ema(values: list[float], span: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (span + 1)
    ema = [values[0]]
    for value in values[1:]:
        ema.append((value * alpha) + (ema[-1] * (1 - alpha)))
    return ema


def _macd(closes: list[float]) -> tuple[float | None, float | None, float | None]:
    if len(closes) < 26:
        return None, None, None
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif = [a - b for a, b in zip(ema12, ema26, strict=False)]
    dea = _ema(dif, 9)
    macd = dif[-1]
    signal = dea[-1]
    hist = macd - signal
    return round(macd, 4), round(signal, 4), round(hist, 4)


def _rsi(closes: list[float], window: int) -> float | None:
    if len(closes) <= window:
        return None
    gains = []
    losses = []
    for prev, curr in zip(closes[-window - 1 : -1], closes[-window:], strict=True):
        delta = curr - prev
        gains.append(max(delta, 0.0))
        losses.append(max(-delta, 0.0))
    avg_gain = sum(gains) / window
    avg_loss = sum(losses) / window
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 4)


def _bollinger(closes: list[float], window: int) -> tuple[float | None, float | None, float | None]:
    if len(closes) < window:
        return None, None, None
    sample = closes[-window:]
    middle = sum(sample) / window
    variance = sum((value - middle) ** 2 for value in sample) / window
    std = variance ** 0.5
    return round(middle + 2 * std, 4), round(middle, 4), round(middle - 2 * std, 4)


def _volume_ratio(volumes: list[float], window: int) -> float | None:
    if len(volumes) < window + 1:
        return None
    baseline = sum(volumes[-window - 1 : -1]) / window
    if baseline <= 0:
        return None
    return round(volumes[-1] / baseline, 4)


def _trend_alignment(close: float, ma5, ma10, ma20, ma60) -> str:
    if None not in {ma5, ma10, ma20, ma60}:
        if close > ma5 > ma10 > ma20 > ma60:
            return "bullish_alignment"
        if close < ma5 < ma10 < ma20 < ma60:
            return "bearish_alignment"
    return "mixed"


def _momentum_state(close: float, rsi14, macd_hist, boll_upper, boll_lower, volume_ratio) -> str:
    if rsi14 is not None and rsi14 >= 70:
        return "overbought"
    if rsi14 is not None and rsi14 <= 30:
        return "oversold"
    if boll_upper is not None and close > boll_upper and (volume_ratio or 0) >= 1.2:
        return "bollinger_volume_breakout"
    if boll_lower is not None and close < boll_lower:
        return "bollinger_breakdown"
    if macd_hist is not None and macd_hist > 0:
        return "positive_momentum"
    if macd_hist is not None and macd_hist < 0:
        return "negative_momentum"
    return "neutral"


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

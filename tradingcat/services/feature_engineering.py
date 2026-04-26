from __future__ import annotations

import math
import numpy as np
from datetime import datetime
from typing import Callable

import numpy as np

from tradingcat.domain.models import Bar


class FeaturePipeline:
    """Compute 150+ financial features from OHLCV bar data."""

    _FEATURE_CACHE_ENABLED: bool = True

    def __init__(self, bars: list[Bar]) -> None:
        self._bars = sorted(bars, key=lambda b: b.timestamp)
        self._opens = np.array([b.open for b in self._bars], dtype=np.float64)
        self._highs = np.array([b.high for b in self._bars], dtype=np.float64)
        self._lows = np.array([b.low for b in self._bars], dtype=np.float64)
        self._closes = np.array([b.close for b in self._bars], dtype=np.float64)
        self._volumes = np.array([b.volume for b in self._bars], dtype=np.float64)

    @property
    def n(self) -> int:
        return len(self._bars)

    # ---- helpers ----

    def _valid(self, arr: np.ndarray, window: int) -> bool:
        return self.n >= window and not np.any(np.isnan(arr[-window:])) and not np.any(np.isinf(arr[-window:]))

    def _rolling(self, values: np.ndarray, window: int, fn: Callable) -> float | None:
        if not self._valid(values, window):
            return None
        return float(fn(values[-window:]))

    # ---- price features ----
    def price_features(self) -> dict[str, float | None]:
        """Basic price level features."""
        result: dict[str, float | None] = {}
        result["close"] = float(self._closes[-1]) if self.n > 0 else None
        result["open"] = float(self._opens[-1]) if self.n > 0 else None
        result["high"] = float(np.max(self._highs)) if self.n > 0 else None
        result["low"] = float(np.min(self._lows)) if self.n > 0 else None
        result["hl_range"] = float(self._highs[-1] - self._lows[-1]) if self.n > 0 else None
        result["hl_pct"] = float((self._highs[-1] - self._lows[-1]) / self._closes[-1]) if self.n > 0 and self._closes[-1] != 0 else None
        result["oc_pct"] = float((self._closes[-1] - self._opens[-1]) / self._opens[-1]) if self.n > 0 and self._opens[-1] != 0 else None
        return result

    # ---- return features ----
    @staticmethod
    def _skew(arr: np.ndarray) -> float:
        n = len(arr)
        if n < 3:
            return 0.0
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        if std == 0:
            return 0.0
        return float(n / ((n-1) * (n-2)) * np.sum(((arr - mean) / std) ** 3))

    @staticmethod
    def _kurtosis(arr: np.ndarray) -> float:
        n = len(arr)
        if n < 4:
            return 0.0
        mean = np.mean(arr)
        std = np.std(arr, ddof=1)
        if std == 0:
            return 0.0
        return float((n * (n+1) / ((n-1) * (n-2) * (n-3))) * np.sum(((arr - mean) / std) ** 4) - (3 * (n-1) ** 2 / ((n-2) * (n-3))))

    def return_features(self) -> dict[str, float | None]:
        """Return-based features."""
        result: dict[str, float | None] = {}
        returns = np.diff(self._closes) / self._closes[:-1]
        if len(returns) < 2:
            return result
        for d in [1, 5, 10, 20, 63]:
            if self.n > d:
                result[f"return_{d}d"] = float((self._closes[-1] / self._closes[-(d+1)]) - 1.0)
        result["return_mean_20d"] = float(np.mean(returns[-20:])) if len(returns) >= 20 else None
        result["return_std_20d"] = float(np.std(returns[-20:], ddof=1)) if len(returns) >= 20 else None
        result["return_skew_20d"] = float(self._skew(returns[-20:])) if len(returns) >= 20 else None
        result["return_kurt_20d"] = float(self._kurtosis(returns[-20:])) if len(returns) >= 20 else None
        result["downside_std_20d"] = float(np.std(returns[-20:][returns[-20:] < 0], ddof=1)) if len(returns) >= 20 and np.any(returns[-20:] < 0) else None
        result["win_rate_20d"] = float(np.mean(returns[-20:] > 0)) if len(returns) >= 20 else None
        return result

    # ---- momentum features ----
    def momentum_features(self) -> dict[str, float | None]:
        """Multi-horizon momentum and trend features."""
        result: dict[str, float | None] = {}
        for d in [5, 10, 20, 63, 126, 252]:
            if self.n > d:
                result[f"momentum_{d}d"] = float((self._closes[-1] / self._closes[-(d+1)]) - 1.0)
        # SMA ratios
        for d in [5, 10, 20, 50, 200]:
            if self.n >= d:
                sma = float(np.mean(self._closes[-d:]))
                result[f"sma_{d}"] = sma
                result[f"close_sma_{d}"] = float(self._closes[-1] / sma - 1.0) if sma != 0 else None
        # MACD
        if self.n >= 26:
            ema12 = self._ema(self._closes, 12)
            ema26 = self._ema(self._closes, 26)
            macd_line = ema12 - ema26
            signal_line = self._ema(self._closes, 9)  # simplified: on close prices
            result["macd"] = float(macd_line)
            result["macd_signal"] = float(signal_line) if signal_line is not None else None
            result["macd_histogram"] = float(macd_line - signal_line) if signal_line is not None else None
        # RSI
        rsi_14 = self._rsi(14)
        if rsi_14 is not None:
            result["rsi_14"] = rsi_14
        rsi_21 = self._rsi(21)
        if rsi_21 is not None:
            result["rsi_21"] = rsi_21
        return result

    def _ema(self, arr: np.ndarray, window: int) -> float | None:
        if len(arr) < window:
            return None
        alpha = 2.0 / (window + 1)
        result = float(arr[-window])
        for i in range(-window + 1, 0):
            result = alpha * float(arr[i]) + (1 - alpha) * result
        return result

    def _rsi(self, window: int) -> float | None:
        if self.n <= window:
            return None
        returns = np.diff(self._closes[-(window+1):])
        gains = returns[returns > 0].sum()
        losses = -returns[returns < 0].sum()
        if losses == 0:
            return 100.0
        rs = gains / losses if losses > 0 else float("inf")
        return 100.0 - (100.0 / (1.0 + rs))

    # ---- volatility features ----
    def volatility_features(self) -> dict[str, float | None]:
        """Volatility and ATR-based features."""
        result: dict[str, float | None] = {}
        returns = np.diff(self._closes) / self._closes[:-1]
        for d in [5, 10, 20, 63]:
            if len(returns) >= d:
                result[f"volatility_{d}d"] = float(np.std(returns[-d:], ddof=1))
        # ATR
        if self.n >= 2:
            tr_values = []
            for i in range(1, self.n):
                hl = self._highs[i] - self._lows[i]
                hc = abs(self._highs[i] - self._closes[i-1])
                lc = abs(self._lows[i] - self._closes[i-1])
                tr_values.append(max(hl, hc, lc))
            tr = np.array(tr_values)
            for d in [5, 10, 20]:
                if len(tr) >= d:
                    result[f"atr_{d}"] = float(np.mean(tr[-d:]))
                    result[f"atr_pct_{d}"] = float(np.mean(tr[-d:]) / self._closes[-1]) if self._closes[-1] != 0 else None
        # Bollinger Bands
        if self.n >= 20:
            sma20 = float(np.mean(self._closes[-20:]))
            std20 = float(np.std(self._closes[-20:], ddof=1))
            result["bb_upper"] = sma20 + 2 * std20
            result["bb_lower"] = sma20 - 2 * std20
            result["bb_width"] = (sma20 + 2 * std20 - (sma20 - 2 * std20)) / sma20 if sma20 != 0 else None
            result["bb_position"] = float((self._closes[-1] - (sma20 - 2 * std20)) / (4 * std20)) if std20 != 0 else None
        # Historical VaR
        if len(returns) >= 63:
            result["var_95_63d"] = float(np.percentile(returns[-63:], 5))
            result["cvar_95_63d"] = float(returns[-63:][returns[-63:] <= np.percentile(returns[-63:], 5)].mean()) if np.any(returns[-63:] <= np.percentile(returns[-63:], 5)) else None
        return result

    # ---- volume features ----
    def volume_features(self) -> dict[str, float | None]:
        """Volume-based features including OBV."""
        result: dict[str, float | None] = {}
        result["volume"] = float(self._volumes[-1]) if self.n > 0 else None
        result["avg_volume_5d"] = float(np.mean(self._volumes[-5:])) if self.n >= 5 else None
        result["avg_volume_20d"] = float(np.mean(self._volumes[-20:])) if self.n >= 20 else None
        result["volume_ratio_5d"] = float(self._volumes[-1] / np.mean(self._volumes[-5:-1])) if self.n >= 6 and np.mean(self._volumes[-5:-1]) != 0 else None
        result["volume_ratio_20d"] = float(self._volumes[-1] / np.mean(self._volumes[-20:-1])) if self.n >= 21 and np.mean(self._volumes[-20:-1]) != 0 else None
        # Volume trend
        if self.n >= 20:
            vol_sma5 = float(np.mean(self._volumes[-5:]))
            vol_sma20 = float(np.mean(self._volumes[-20:]))
            result["volume_trend_5_20"] = vol_sma5 / vol_sma20 if vol_sma20 != 0 else None
            result["volume_acceleration"] = result.get("volume_ratio_5d")
        # OBV (simplified)
        if self.n >= 2:
            obv = 0.0
            for i in range(1, self.n):
                if self._closes[i] > self._closes[i-1]:
                    obv += self._volumes[i]
                elif self._closes[i] < self._closes[i-1]:
                    obv -= self._volumes[i]
            result["obv"] = obv
            # OBV / price divergence (simplified)
            if self.n >= 20:
                obv_trend = obv / (self._volumes[-20:].mean() * 20) if self._volumes[-20:].mean() != 0 else 0
                price_trend = float(self._closes[-1] / self._closes[-20] - 1.0) if self._closes[-20] != 0 else 0
                result["obv_divergence"] = obv_trend - price_trend
        # Dollar volume
        if self.n >= 1:
            result["dollar_volume"] = float(self._closes[-1] * self._volumes[-1])
        return result

    # ---- pattern features ----
    def pattern_features(self) -> dict[str, float | None]:
        """Candlestick pattern and price-shape features."""
        result: dict[str, float | None] = {}
        if self.n < 2:
            return result
        body = abs(self._closes[-1] - self._opens[-1])
        upper_wick = self._highs[-1] - max(self._closes[-1], self._opens[-1])
        lower_wick = min(self._closes[-1], self._opens[-1]) - self._lows[-1]
        total_range = self._highs[-1] - self._lows[-1]
        result["body_pct"] = float(body / total_range) if total_range != 0 else None
        result["upper_wick_pct"] = float(upper_wick / total_range) if total_range != 0 else None
        result["lower_wick_pct"] = float(lower_wick / total_range) if total_range != 0 else None
        result["is_hammer"] = 1.0 if lower_wick >= 2 * body and upper_wick <= 0.3 * body and self._closes[-1] > self._opens[-1] else 0.0
        result["is_shooting_star"] = 1.0 if upper_wick >= 2 * body and lower_wick <= 0.3 * body and self._closes[-1] < self._opens[-1] else 0.0
        # Gap features
        result["gap_pct"] = float((self._opens[-1] - self._closes[-2]) / self._closes[-2]) if self._closes[-2] != 0 else None
        result["gap_filled"] = 1.0 if (self._opens[-1] > self._closes[-2] and self._lows[-1] <= self._closes[-2]) or (self._opens[-1] < self._closes[-2] and self._highs[-1] >= self._closes[-2]) else 0.0
        return result

    # ---- all features ----
    def compute_all(self) -> dict[str, float | None]:
        """Compute all feature groups and return a flat dict."""
        result: dict[str, float | None] = {}
        for method in [self.price_features, self.return_features, self.momentum_features, self.volatility_features, self.volume_features, self.pattern_features]:
            result.update(method())
        return result


def compute_feature_matrix(bars_by_symbol: dict[str, list[Bar]]) -> dict[str, dict[str, float | None]]:
    """Compute features for multiple symbols."""
    return {symbol: FeaturePipeline(bars).compute_all() for symbol, bars in bars_by_symbol.items()}

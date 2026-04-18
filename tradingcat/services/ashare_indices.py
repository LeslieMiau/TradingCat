from __future__ import annotations

from datetime import date, timedelta
from statistics import mean

from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    AssetClass,
    Instrument,
    Market,
    MarketAwarenessAshareIndices,
    MarketAwarenessAshareIndexView,
    MarketAwarenessPriceVolumeState,
    MarketAwarenessSignalStatus,
)
from tradingcat.services.market_data import MarketDataService


def _sorted_bars(bars):
    return sorted(bars, key=lambda item: item.timestamp)


def _closes(bars) -> list[float]:
    return [float(bar.close) for bar in _sorted_bars(bars) if float(bar.close) > 0]


def _volumes(bars) -> list[float]:
    return [float(bar.volume) for bar in _sorted_bars(bars) if float(bar.volume) >= 0]


def _sma(values: list[float], window: int) -> float | None:
    if len(values) < window:
        return None
    return sum(values[-window:]) / window


def _return(values: list[float], lookback: int) -> float | None:
    if len(values) <= lookback:
        return None
    previous = values[-lookback - 1]
    if previous <= 0:
        return None
    return (values[-1] / previous) - 1.0


class AshareIndexObservationService:
    _INDEX_LABELS = {
        "SH000001": "上证指数",
        "SZ399001": "深证成指",
        "SZ399006": "创业板指",
    }

    def __init__(self, config: AppConfig, market_data: MarketDataService) -> None:
        self._config = config.market_awareness
        self._market_data = market_data

    def observe(self, as_of: date) -> MarketAwarenessAshareIndices:
        start = as_of - timedelta(days=max(self._config.long_trend_window + 40, 260))
        index_views: list[MarketAwarenessAshareIndexView] = []
        blockers: list[str] = []

        for symbol in self._config.cn_observation_index_symbols:
            instrument = Instrument(
                symbol=symbol,
                market=Market.CN,
                asset_class=AssetClass.STOCK,
                currency="CNY",
                name=self._INDEX_LABELS.get(symbol, symbol),
                tradable=False,
                tags=["observation_only", "cn_index"],
            )
            bars = self._market_data.bars_for_instrument(instrument, start, as_of)
            closes = _closes(bars)
            volumes = _volumes(bars)
            if len(closes) < self._config.long_trend_window:
                blockers.append(f"{symbol}: insufficient history for 200-day structure.")
                continue

            sma20 = _sma(closes, 20)
            sma50 = _sma(closes, 50)
            sma200 = _sma(closes, 200)
            ret_1d = _return(closes, 1)
            ret_5d = _return(closes, 5)
            ret_20d = _return(closes, 20)
            volume_ratio = self._volume_ratio(volumes)
            trend_status = self._trend_status(closes[-1], sma20, sma50, sma200, ret_20d)
            price_volume_state = self._price_volume_state(ret_5d, ret_20d, volume_ratio)
            score = self._score(trend_status, price_volume_state, ret_20d, volume_ratio)
            index_views.append(
                MarketAwarenessAshareIndexView(
                    label=self._INDEX_LABELS.get(symbol, symbol),
                    symbol=symbol,
                    trend_status=trend_status,
                    price_volume_state=price_volume_state,
                    score=round(score, 4),
                    close=round(closes[-1], 4),
                    return_1d=round(ret_1d, 4) if ret_1d is not None else None,
                    return_5d=round(ret_5d, 4) if ret_5d is not None else None,
                    return_20d=round(ret_20d, 4) if ret_20d is not None else None,
                    volume_ratio_20d=round(volume_ratio, 4) if volume_ratio is not None else None,
                    above_sma20=(closes[-1] > sma20) if sma20 is not None else None,
                    above_sma50=(closes[-1] > sma50) if sma50 is not None else None,
                    above_sma200=(closes[-1] > sma200) if sma200 is not None else None,
                    explanation=self._explanation(trend_status, price_volume_state, volume_ratio),
                )
            )

        degraded = len(index_views) < len(self._config.cn_observation_index_symbols)
        score = round(mean([item.score for item in index_views]), 4) if index_views else 0.0
        tone = (
            MarketAwarenessSignalStatus.SUPPORTIVE
            if score >= 0.2
            else MarketAwarenessSignalStatus.WARNING
            if score <= -0.15
            else MarketAwarenessSignalStatus.MIXED
        )
        explanation = (
            "A-share three-index tape is broadly supportive."
            if tone == MarketAwarenessSignalStatus.SUPPORTIVE
            else "A-share three-index tape is under pressure."
            if tone == MarketAwarenessSignalStatus.WARNING
            else "A-share three-index tape is mixed and needs confirmation."
        )
        if degraded:
            explanation = f"{explanation} Some indices are degraded."
        return MarketAwarenessAshareIndices(
            score=score,
            tone=tone,
            index_views=index_views,
            degraded=degraded,
            blockers=blockers,
            explanation=explanation,
        )

    @staticmethod
    def _volume_ratio(volumes: list[float], window: int = 20) -> float | None:
        if len(volumes) < window + 1:
            return None
        average = sum(volumes[-window - 1 : -1]) / window
        if average <= 0:
            return None
        return volumes[-1] / average

    @staticmethod
    def _trend_status(
        latest_close: float,
        sma20: float | None,
        sma50: float | None,
        sma200: float | None,
        ret_20d: float | None,
    ) -> MarketAwarenessSignalStatus:
        if None in {sma20, sma50, sma200, ret_20d}:
            return MarketAwarenessSignalStatus.BLOCKED
        assert sma20 is not None and sma50 is not None and sma200 is not None and ret_20d is not None
        if latest_close > sma20 > sma50 > sma200 and ret_20d > 0:
            return MarketAwarenessSignalStatus.SUPPORTIVE
        if latest_close < sma50 and latest_close < sma200 and ret_20d < 0:
            return MarketAwarenessSignalStatus.WARNING
        return MarketAwarenessSignalStatus.MIXED

    @staticmethod
    def _price_volume_state(
        ret_5d: float | None,
        ret_20d: float | None,
        volume_ratio: float | None,
    ) -> MarketAwarenessPriceVolumeState:
        if ret_5d is None or volume_ratio is None:
            return MarketAwarenessPriceVolumeState.DIVERGENCE
        if ret_5d > 0 and volume_ratio >= 1.05:
            return MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_UP
        if ret_5d > 0 and volume_ratio <= 0.95:
            return MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_DOWN
        if ret_5d < 0 and volume_ratio >= 1.05:
            return MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_UP
        if ret_5d < 0 and volume_ratio <= 0.95:
            return MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_DOWN
        if ret_20d is not None and ret_20d < 0 < ret_5d:
            return MarketAwarenessPriceVolumeState.REPAIR
        return MarketAwarenessPriceVolumeState.DIVERGENCE

    @staticmethod
    def _score(
        trend_status: MarketAwarenessSignalStatus,
        price_volume_state: MarketAwarenessPriceVolumeState,
        ret_20d: float | None,
        volume_ratio: float | None,
    ) -> float:
        score = 0.0
        if trend_status == MarketAwarenessSignalStatus.SUPPORTIVE:
            score += 0.4
        elif trend_status == MarketAwarenessSignalStatus.WARNING:
            score -= 0.4
        if price_volume_state == MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_UP:
            score += 0.35
        elif price_volume_state == MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_UP:
            score -= 0.35
        elif price_volume_state == MarketAwarenessPriceVolumeState.REPAIR:
            score += 0.1
        elif price_volume_state == MarketAwarenessPriceVolumeState.PRICE_UP_VOLUME_DOWN:
            score -= 0.05
        elif price_volume_state == MarketAwarenessPriceVolumeState.PRICE_DOWN_VOLUME_DOWN:
            score -= 0.1
        if ret_20d is not None:
            score += max(min(ret_20d * 2, 0.25), -0.25)
        if volume_ratio is not None and volume_ratio > 1.15:
            score += 0.05
        return max(min(score, 1.0), -1.0)

    @staticmethod
    def _explanation(
        trend_status: MarketAwarenessSignalStatus,
        price_volume_state: MarketAwarenessPriceVolumeState,
        volume_ratio: float | None,
    ) -> str:
        trend_text = (
            "trend aligned above 20/50/200-day structure"
            if trend_status == MarketAwarenessSignalStatus.SUPPORTIVE
            else "trend broke medium/long structure"
            if trend_status == MarketAwarenessSignalStatus.WARNING
            else "trend structure is mixed"
        )
        volume_text = f", volume ratio {volume_ratio:.2f}" if volume_ratio is not None else ""
        return f"{trend_text}; tape state {price_volume_state.value}{volume_text}."

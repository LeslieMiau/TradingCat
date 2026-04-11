from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import logging
import math
from statistics import mean

from tradingcat.adapters.market import sample_instruments
from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    AssetClass,
    Instrument,
    Market,
    MarketAwarenessAshareIndices,
    MarketAwarenessActionItem,
    MarketAwarenessActionSeverity,
    MarketAwarenessConfidence,
    MarketAwarenessDataQuality,
    MarketAwarenessDataStatus,
    MarketAwarenessEvidenceRow,
    MarketAwarenessFearGreed,
    MarketAwarenessMarketView,
    MarketAwarenessNewsObservation,
    MarketAwarenessParticipation,
    MarketAwarenessRegime,
    MarketAwarenessRiskPosture,
    MarketAwarenessSignalStatus,
    MarketAwarenessSnapshot,
    MarketAwarenessStrategyGuidance,
    MarketAwarenessStrategyStance,
    MarketAwarenessVolumePrice,
)
from tradingcat.services.ashare_indices import AshareIndexObservationService
from tradingcat.services.alpha_radar import AlphaRadarService
from tradingcat.services.fear_greed import FearGreedToolService
from tradingcat.services.macro_calendar import MacroCalendarService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.news_observation import NewsObservationService
from tradingcat.services.participation_decision import ParticipationDecisionService
from tradingcat.services.volume_price import VolumePriceToolService


logger = logging.getLogger(__name__)


def _sorted_bars(bars):
    return sorted(bars, key=lambda item: item.timestamp)


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


def _window_drawdown(closes: list[float], window: int = 20) -> float | None:
    if len(closes) < window:
        return None
    recent = closes[-window:]
    peak = max(recent)
    if peak <= 0:
        return None
    return round((recent[-1] / peak) - 1.0, 4)


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


def _clamp(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 4)


class MarketAwarenessService:
    _BREADTH_ASSET_CLASSES = {AssetClass.STOCK.value, AssetClass.ETF.value}
    _LIQUIDITY_ORDER = {"low": 0, "medium": 1, "high": 2}

    def __init__(
        self,
        config: AppConfig,
        market_data: MarketDataService,
        *,
        market_calendar: MarketCalendarService | None = None,
        macro_calendar: MacroCalendarService | None = None,
        alpha_radar: AlphaRadarService | None = None,
        news_observation: NewsObservationService | None = None,
        a_share_indices: AshareIndexObservationService | None = None,
        fear_greed_tool: FearGreedToolService | None = None,
        volume_price_tool: VolumePriceToolService | None = None,
        participation_decision: ParticipationDecisionService | None = None,
    ) -> None:
        self._app_config = config
        self._config = config.market_awareness
        self._market_data = market_data
        self._market_calendar = market_calendar
        self._macro_calendar = macro_calendar
        self._alpha_radar = alpha_radar
        self._news_observation = news_observation or NewsObservationService(config)
        self._a_share_indices = a_share_indices or AshareIndexObservationService(config, market_data)
        self._fear_greed_tool = fear_greed_tool or FearGreedToolService()
        self._volume_price_tool = volume_price_tool or VolumePriceToolService()
        self._participation_decision = participation_decision or ParticipationDecisionService(config)
        self._bootstrap_sample_keys = {
            self._instrument_key(instrument)
            for instrument in sample_instruments()
        }

    def snapshot(self, as_of: date | None = None) -> MarketAwarenessSnapshot:
        evaluation_date = as_of or date.today()
        benchmark_payload = self.load_benchmark_histories(evaluation_date)
        market_views: list[MarketAwarenessMarketView] = []
        missing_symbols = list(benchmark_payload["missing_symbols"])
        fallback_symbols = list(benchmark_payload["fallback_symbols"])
        stale_windows: list[str] = []
        blockers = list(benchmark_payload["blockers"])
        adapter_limitations: list[str] = []
        stress_detected = False
        cross_asset_scores: list[float] = []

        for market in (Market.US, Market.HK, Market.CN):
            market_view, market_meta = self._build_market_view(market, evaluation_date, benchmark_payload)
            market_views.append(market_view)
            missing_symbols.extend(market_meta["missing_symbols"])
            fallback_symbols.extend(market_meta["fallback_symbols"])
            stale_windows.extend(market_meta["stale_windows"])
            blockers.extend(market_meta["blockers"])
            adapter_limitations.extend(market_meta["adapter_limitations"])
            stress_detected = stress_detected or market_meta["stress_detected"]
            cross_asset_scores.append(float(market_meta["cross_asset_score"]))

        data_quality = self._build_data_quality(
            missing_symbols=missing_symbols,
            fallback_symbols=fallback_symbols,
            stale_windows=stale_windows,
            adapter_limitations=adapter_limitations,
            blockers=blockers,
        )
        overall_score = self._overall_score(market_views)
        overall_regime = self._classify_overall_regime(overall_score, market_views)
        confidence = self._overall_confidence(market_views, data_quality)
        risk_posture = self._risk_posture_from_regime(
            overall_regime,
            confidence,
            data_quality,
            stress_detected=stress_detected,
        )
        news_observation = self._observe_news(evaluation_date)
        a_share_indices = self._observe_a_share_indices(evaluation_date)
        fear_greed = self._observe_fear_greed(
            a_share_indices=a_share_indices,
            news_observation=news_observation,
            cross_asset_scores=cross_asset_scores,
        )
        volume_price = self._observe_volume_price(a_share_indices)
        participation = self._observe_participation(
            a_share_indices=a_share_indices,
            news_observation=news_observation,
            fear_greed=fear_greed,
            volume_price=volume_price,
        )

        return MarketAwarenessSnapshot(
            as_of=evaluation_date,
            overall_regime=overall_regime,
            confidence=confidence,
            risk_posture=risk_posture,
            overall_score=overall_score,
            market_views=market_views,
            evidence=self._overall_evidence(market_views, data_quality),
            actions=self._build_actions(risk_posture, market_views, data_quality, participation),
            strategy_guidance=self._strategy_guidance(risk_posture, market_views, data_quality, participation),
            data_quality=data_quality,
            news_observation=news_observation,
            a_share_indices=a_share_indices,
            fear_greed=fear_greed,
            volume_price=volume_price,
            participation=participation,
        )

    def benchmark_baskets(self) -> dict[str, dict[str, object]]:
        return {
            Market.US.value: self._market_basket(Market.US, self._config.us_benchmark_symbols),
            Market.HK.value: self._market_basket(Market.HK, self._config.hk_benchmark_symbols),
            Market.CN.value: self._market_basket(Market.CN, self._config.cn_benchmark_symbols),
            "cross_asset": {
                "symbols": list(self._config.cross_asset_reference_symbols),
            },
        }

    def load_benchmark_histories(self, as_of: date) -> dict[str, object]:
        lookback_days = max(260, self._config.long_trend_window + 60)
        start = as_of - timedelta(days=lookback_days)
        baskets = self.benchmark_baskets()
        markets: dict[str, dict[str, object]] = {}
        cross_asset = self._history_snapshot_for_symbols(
            list(baskets["cross_asset"]["symbols"]),
            start,
            as_of,
        )
        missing_symbols = list(cross_asset["missing_symbols"])
        fallback_symbols = list(cross_asset["fallback_symbols"])
        blockers = list(cross_asset["blockers"])
        for market in (Market.US, Market.HK, Market.CN):
            market_basket = dict(baskets[market.value])
            symbols = [market_basket["benchmark_symbol"], *market_basket["reference_symbols"]]
            history_payload = self._history_snapshot_for_symbols(symbols, start, as_of)
            markets[market.value] = {
                **market_basket,
                **history_payload,
            }
            missing_symbols.extend(history_payload["missing_symbols"])
            fallback_symbols.extend(history_payload["fallback_symbols"])
            blockers.extend(history_payload["blockers"])
        return {
            "as_of": as_of,
            "start": start,
            "lookback_days": lookback_days,
            "markets": markets,
            "cross_asset": cross_asset,
            "missing_symbols": sorted(set(missing_symbols)),
            "fallback_symbols": sorted(set(fallback_symbols)),
            "blockers": blockers,
        }

    def breadth_universe(self, market: Market, *, limit: int | None = None) -> dict[str, object]:
        eligible = self._eligible_breadth_instruments(market)
        custom_instruments = [
            instrument
            for instrument in eligible
            if self._instrument_key(instrument) not in self._bootstrap_sample_keys
        ]
        selected = self._select_breadth_constituents(custom_instruments or eligible, limit=limit)
        return {
            "market": market.value,
            "symbols": [instrument.symbol for instrument in selected],
            "instruments": selected,
            "source": "persisted_catalog" if custom_instruments else "bootstrap_sample",
            "fallback_used": not bool(custom_instruments),
            "blockers": [] if selected else [f"No eligible breadth instruments available for {market.value}."],
        }

    def select_breadth_constituents(self, market: Market, *, limit: int | None = None) -> list[Instrument]:
        return list(self.breadth_universe(market, limit=limit)["instruments"])

    def _observe_news(self, evaluation_date: date) -> MarketAwarenessNewsObservation:
        return self._news_observation.observe(evaluation_date)

    def _observe_a_share_indices(self, evaluation_date: date) -> MarketAwarenessAshareIndices:
        return self._a_share_indices.observe(evaluation_date)

    def _observe_fear_greed(
        self,
        *,
        a_share_indices: MarketAwarenessAshareIndices,
        news_observation: MarketAwarenessNewsObservation,
        cross_asset_scores: list[float],
    ) -> MarketAwarenessFearGreed:
        cross_asset_score = round(mean(cross_asset_scores), 4) if cross_asset_scores else 0.0
        return self._fear_greed_tool.observe(
            a_share_indices=a_share_indices,
            news_observation=news_observation,
            cross_asset_score=cross_asset_score,
        )

    def _observe_volume_price(self, a_share_indices: MarketAwarenessAshareIndices) -> MarketAwarenessVolumePrice:
        return self._volume_price_tool.observe(a_share_indices)

    def _observe_participation(
        self,
        *,
        a_share_indices: MarketAwarenessAshareIndices,
        news_observation: MarketAwarenessNewsObservation,
        fear_greed: MarketAwarenessFearGreed,
        volume_price: MarketAwarenessVolumePrice,
    ) -> MarketAwarenessParticipation:
        return self._participation_decision.observe(
            a_share_indices=a_share_indices,
            news_observation=news_observation,
            fear_greed=fear_greed,
            volume_price=volume_price,
        )

    def _build_market_view(
        self,
        market: Market,
        as_of: date,
        benchmark_payload: dict[str, object],
    ) -> tuple[MarketAwarenessMarketView, dict[str, object]]:
        market_payload = dict(benchmark_payload["markets"][market.value])
        benchmark_symbol = str(market_payload["benchmark_symbol"])
        history_by_symbol = dict(market_payload["history_by_symbol"])
        benchmark_closes = _closes(history_by_symbol.get(benchmark_symbol, []))

        trend = self._trend_signal(market, benchmark_symbol, benchmark_closes)
        momentum = self._momentum_signal(market, benchmark_symbol, benchmark_closes)
        drawdown = self._drawdown_signal(market, benchmark_symbol, benchmark_closes)
        volatility = self._volatility_signal(market, benchmark_symbol, benchmark_closes)
        breadth = self._breadth_signal(market, as_of)
        cross_asset = self._cross_asset_signal(market, benchmark_payload["cross_asset"], benchmark_closes)
        macro = self._macro_signal(market)
        alpha = self._alpha_signal(market)
        overlay_score = round(mean([cross_asset["score"], macro["score"], alpha["score"]]), 4)
        weighted_score = round(
            (trend["score"] * self._config.trend_weight)
            + (breadth["score"] * self._config.breadth_weight)
            + (momentum["score"] * self._config.momentum_weight)
            + (drawdown["score"] * self._config.drawdown_weight)
            + (volatility["score"] * self._config.volatility_weight)
            + (overlay_score * self._config.overlay_weight),
            4,
        )
        market_blockers = [
            *market_payload["blockers"],
            *breadth["blockers"],
        ]
        confidence = self._market_confidence(
            [
                trend["score"],
                momentum["score"],
                drawdown["score"],
                volatility["score"],
                breadth["score"],
                cross_asset["score"],
            ],
            degraded=bool(market_blockers or market_payload["missing_symbols"]),
        )
        regime = self._classify_regime(weighted_score)
        stress_detected = (
            (drawdown["value"] is not None and drawdown["value"] <= self._config.drawdown_caution_threshold)
            or (volatility["value"] is not None and volatility["value"] >= self._config.volatility_caution_threshold)
        )
        data_quality = self._build_data_quality(
            missing_symbols=[*market_payload["missing_symbols"], *breadth["missing_symbols"]],
            fallback_symbols=[*market_payload["fallback_symbols"], *breadth["fallback_symbols"]],
            stale_windows=breadth["stale_windows"],
            adapter_limitations=[*macro["adapter_limitations"], *alpha["adapter_limitations"]],
            blockers=market_blockers,
        )
        risk_posture = self._risk_posture_from_regime(
            regime,
            confidence,
            data_quality,
            stress_detected=stress_detected,
        )
        view = MarketAwarenessMarketView(
            market=market,
            benchmark_symbol=benchmark_symbol,
            reference_symbols=list(market_payload["reference_symbols"]),
            regime=regime,
            confidence=confidence,
            risk_posture=risk_posture,
            score=weighted_score,
            breadth_ratio=breadth["value"],
            momentum_21d=momentum["value"],
            drawdown_20d=drawdown["value"],
            realized_volatility_20d=volatility["value"],
            evidence=[
                trend["evidence"],
                momentum["evidence"],
                drawdown["evidence"],
                volatility["evidence"],
                breadth["evidence"],
                cross_asset["evidence"],
                macro["evidence"],
                alpha["evidence"],
            ],
        )
        return view, {
            "missing_symbols": [*market_payload["missing_symbols"], *breadth["missing_symbols"]],
            "fallback_symbols": [*market_payload["fallback_symbols"], *breadth["fallback_symbols"]],
            "stale_windows": breadth["stale_windows"],
            "blockers": market_blockers,
            "adapter_limitations": [*macro["adapter_limitations"], *alpha["adapter_limitations"]],
            "stress_detected": stress_detected,
            "cross_asset_score": cross_asset["score"],
        }

    def _trend_signal(self, market: Market, symbol: str, closes: list[float]) -> dict[str, object]:
        latest = _latest_close(closes)
        sma_short = _sma(closes, self._config.short_trend_window)
        sma_medium = _sma(closes, self._config.medium_trend_window)
        sma_long = _sma(closes, self._config.long_trend_window)
        averages = [value for value in [sma_short, sma_medium, sma_long] if value is not None]
        if latest is None or len(averages) < 3:
            return self._blocked_signal(
                market,
                "trend_alignment",
                "Trend alignment",
                f"{symbol} lacks enough local history for all configured moving averages.",
            )
        aligned = sum(1 for value in averages if latest >= value)
        score = round(((aligned / 3) * 2) - 1, 4)
        if aligned == 3:
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = f"{symbol} is above the short, medium, and long trend windows."
        elif aligned == 0:
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{symbol} is below all configured trend windows."
        else:
            status = MarketAwarenessSignalStatus.MIXED
            explanation = f"{symbol} is only above {aligned} of 3 configured trend windows."
        return {
            "score": score,
            "value": round(aligned / 3, 4),
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="trend_alignment",
                label="Trend alignment",
                status=status,
                value=round(aligned / 3, 4),
                unit="ratio",
                explanation=explanation,
            ),
        }

    def _momentum_signal(self, market: Market, symbol: str, closes: list[float]) -> dict[str, object]:
        windows = [21, 63, 126]
        momentums = [_momentum(closes, window) for window in windows]
        values = [value for value in momentums if value is not None]
        if len(values) < len(windows):
            return self._blocked_signal(
                market,
                "momentum",
                "Momentum",
                f"{symbol} lacks enough history for 21/63/126 day momentum checks.",
            )
        average_momentum = round(mean(values), 4)
        score = _clamp(average_momentum / max(self._config.momentum_support_threshold, 0.01))
        if average_momentum >= self._config.momentum_support_threshold:
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = f"{symbol} shows supportive average 21/63/126 day momentum."
        elif average_momentum <= self._config.momentum_warning_threshold:
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{symbol} momentum is negative across the configured horizons."
        else:
            status = MarketAwarenessSignalStatus.MIXED
            explanation = f"{symbol} momentum is mixed and not yet decisive."
        return {
            "score": score,
            "value": average_momentum,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="momentum",
                label="Momentum",
                status=status,
                value=average_momentum,
                unit="ratio",
                explanation=explanation,
            ),
        }

    def _drawdown_signal(self, market: Market, symbol: str, closes: list[float]) -> dict[str, object]:
        drawdown = _window_drawdown(closes, window=20)
        if drawdown is None:
            return self._blocked_signal(
                market,
                "drawdown",
                "Drawdown stress",
                f"{symbol} lacks enough history for rolling drawdown checks.",
            )
        if drawdown <= self._config.drawdown_risk_off_threshold:
            score = -1.0
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{symbol} drawdown breached the risk-off threshold."
        elif drawdown <= self._config.drawdown_caution_threshold:
            score = -0.5
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{symbol} drawdown moved into the caution zone."
        else:
            score = 0.5
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = f"{symbol} drawdown remains contained versus the caution threshold."
        return {
            "score": score,
            "value": drawdown,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="drawdown",
                label="Drawdown stress",
                status=status,
                value=drawdown,
                unit="ratio",
                explanation=explanation,
            ),
        }

    def _volatility_signal(self, market: Market, symbol: str, closes: list[float]) -> dict[str, object]:
        volatility = _realized_volatility(closes, window=20)
        if volatility is None:
            return self._blocked_signal(
                market,
                "realized_volatility",
                "Realized volatility",
                f"{symbol} lacks enough history for realized-volatility checks.",
            )
        if volatility >= self._config.volatility_stress_threshold:
            score = -1.0
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{symbol} realized volatility is above the stress line."
        elif volatility >= self._config.volatility_caution_threshold:
            score = -0.4
            status = MarketAwarenessSignalStatus.MIXED
            explanation = f"{symbol} realized volatility is elevated and needs confirmation."
        else:
            score = 0.5
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = f"{symbol} realized volatility remains below the caution line."
        return {
            "score": score,
            "value": volatility,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="realized_volatility",
                label="Realized volatility",
                status=status,
                value=volatility,
                unit="ratio",
                explanation=explanation,
            ),
        }

    def _breadth_signal(self, market: Market, as_of: date) -> dict[str, object]:
        universe = self.breadth_universe(market, limit=25)
        symbols = list(universe["symbols"])
        if not symbols:
            return {
                **self._blocked_signal(
                    market,
                    "breadth",
                    "Breadth",
                    f"No eligible breadth instruments are available for {market.value}.",
                ),
                "missing_symbols": [],
                "fallback_symbols": [],
                "stale_windows": [],
                "blockers": list(universe["blockers"]),
            }
        start = as_of - timedelta(days=max(140, self._config.medium_trend_window + 30))
        snapshot = self._history_snapshot_for_symbols(symbols, start, as_of)
        ready = 0
        supportive = 0
        stale_windows: list[str] = []
        for symbol in symbols:
            closes = _closes(snapshot["history_by_symbol"].get(symbol, []))
            latest = _latest_close(closes)
            sma_medium = _sma(closes, self._config.medium_trend_window)
            momentum_21d = _momentum(closes, 21)
            if latest is None or sma_medium is None or momentum_21d is None:
                stale_windows.append(f"{market.value}:{symbol}:breadth")
                continue
            ready += 1
            if latest >= sma_medium and momentum_21d > 0:
                supportive += 1
        if ready == 0:
            blockers = [*universe["blockers"], f"No usable breadth history is available for {market.value}."]
            return {
                **self._blocked_signal(
                    market,
                    "breadth",
                    "Breadth",
                    f"{market.value} breadth history is unavailable across the selected universe.",
                ),
                "missing_symbols": list(snapshot["missing_symbols"]),
                "fallback_symbols": list(snapshot["fallback_symbols"]),
                "stale_windows": stale_windows,
                "blockers": blockers,
            }
        ratio = round(supportive / ready, 4)
        if ratio >= self._config.breadth_support_ratio:
            score = 1.0
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = f"{market.value} breadth is healthy across the selected tradable universe."
        elif ratio < self._config.breadth_caution_ratio:
            score = -1.0
            status = MarketAwarenessSignalStatus.WARNING
            explanation = f"{market.value} breadth is below the caution threshold."
        else:
            score = 0.0
            status = MarketAwarenessSignalStatus.MIXED
            explanation = f"{market.value} breadth is mixed and still needs confirmation."
        return {
            "score": score,
            "value": ratio,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="breadth",
                label="Breadth",
                status=status,
                value=ratio,
                unit="ratio",
                explanation=explanation,
            ),
            "missing_symbols": list(snapshot["missing_symbols"]),
            "fallback_symbols": list(snapshot["fallback_symbols"]),
            "stale_windows": stale_windows,
            "blockers": list(universe["blockers"]),
        }

    def _cross_asset_signal(self, market: Market, cross_asset_payload: dict[str, object], benchmark_closes: list[float]) -> dict[str, object]:
        benchmark_momentum = _momentum(benchmark_closes, 21)
        defensive_momentums = []
        for bars in cross_asset_payload["history_by_symbol"].values():
            value = _momentum(_closes(bars), 21)
            if value is not None:
                defensive_momentums.append(value)
        if benchmark_momentum is None or not defensive_momentums:
            return self._blocked_signal(
                market,
                "cross_asset_confirmation",
                "Cross-asset confirmation",
                "Cross-asset overlays are unavailable or incomplete.",
            )
        defensive_average = round(mean(defensive_momentums), 4)
        spread = round(benchmark_momentum - defensive_average, 4)
        if spread >= 0.02:
            score = 0.75
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = "Equity leadership is outpacing defensive assets."
        elif spread <= -0.02:
            score = -0.75
            status = MarketAwarenessSignalStatus.WARNING
            explanation = "Defensive assets are outperforming the equity benchmark."
        else:
            score = 0.0
            status = MarketAwarenessSignalStatus.MIXED
            explanation = "Cross-asset leadership is mixed."
        return {
            "score": score,
            "value": spread,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="cross_asset_confirmation",
                label="Cross-asset confirmation",
                status=status,
                value=spread,
                unit="ratio",
                explanation=explanation,
            ),
        }

    def _macro_signal(self, market: Market) -> dict[str, object]:
        if self._macro_calendar is None:
            return self._neutral_signal(
                market,
                "macro_overlay",
                "Macro overlay",
                "Macro-calendar overlay is not wired, so posture stays price-led.",
            )
        country_map = {
            Market.US: {"US"},
            Market.HK: {"HK", "CN", "US"},
            Market.CN: {"CN", "US"},
        }
        relevant = []
        now = datetime.now(UTC)
        for event in self._macro_calendar.fetch_upcoming_events(days=3):
            if event.country.upper() not in country_map[market]:
                continue
            try:
                event_time = datetime.fromisoformat(event.time.replace("Z", "+00:00"))
            except ValueError:
                continue
            if event_time < now:
                continue
            relevant.append((event, event_time))
        if not relevant:
            return self._neutral_signal(
                market,
                "macro_overlay",
                "Macro overlay",
                "No near-term macro event is large enough to pressure the posture reading.",
            )
        high_soon = next(
            (
                item
                for item in relevant
                if item[0].impact.upper() == "HIGH" and item[1] <= now + timedelta(days=1)
            ),
            None,
        )
        if high_soon is not None:
            event = high_soon[0]
            return {
                "score": -1.0,
                "value": 1.0,
                "evidence": MarketAwarenessEvidenceRow(
                    market=market.value,
                    signal_key="macro_overlay",
                    label="Macro overlay",
                    status=MarketAwarenessSignalStatus.WARNING,
                    value=1.0,
                    unit="count",
                    explanation=f"High-impact macro event ahead: {event.country} {event.event}.",
                ),
                "adapter_limitations": [],
            }
        return self._neutral_signal(
            market,
            "macro_overlay",
            "Macro overlay",
            "Macro calendar is live, but there is no immediate high-impact pressure event.",
        )

    def _alpha_signal(self, market: Market) -> dict[str, object]:
        if market != Market.US or self._alpha_radar is None:
            return self._neutral_signal(
                market,
                "alpha_overlay",
                "Alpha-radar overlay",
                "Alpha-radar overlay is unavailable or not relevant for this market.",
            )
        try:
            flows = self._alpha_radar.fetch_simulated_flow(count=12)
        except Exception:
            logger.exception("Alpha radar overlay failed")
            neutral = self._neutral_signal(
                market,
                "alpha_overlay",
                "Alpha-radar overlay",
                "Alpha-radar overlay failed, so posture stays price-led.",
            )
            neutral["adapter_limitations"] = ["alpha_radar_overlay_failed"]
            return neutral
        directional = [item for item in flows if item.get("sentiment") in {"BULLISH", "BEARISH"}]
        if not directional:
            return self._neutral_signal(
                market,
                "alpha_overlay",
                "Alpha-radar overlay",
                "Alpha-radar flow was neutral, so it does not shift posture.",
            )
        bullish = sum(1 for item in directional if item.get("sentiment") == "BULLISH")
        bearish = sum(1 for item in directional if item.get("sentiment") == "BEARISH")
        balance = round((bullish - bearish) / max(1, len(directional)), 4)
        if balance >= 0.25:
            score = 0.5
            status = MarketAwarenessSignalStatus.SUPPORTIVE
            explanation = "Directional alpha-radar flow leans bullish."
        elif balance <= -0.25:
            score = -0.5
            status = MarketAwarenessSignalStatus.WARNING
            explanation = "Directional alpha-radar flow leans bearish."
        else:
            score = 0.0
            status = MarketAwarenessSignalStatus.MIXED
            explanation = "Directional alpha-radar flow is mixed."
        return {
            "score": score,
            "value": balance,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key="alpha_overlay",
                label="Alpha-radar overlay",
                status=status,
                value=balance,
                unit="balance",
                explanation=explanation,
            ),
            "adapter_limitations": [],
        }

    def _overall_score(self, market_views: list[MarketAwarenessMarketView]) -> float:
        if not market_views:
            return 0.0
        average_score = mean(view.score for view in market_views)
        weakest_score = min(view.score for view in market_views)
        return round((average_score * 0.7) + (weakest_score * 0.3), 4)

    def _classify_regime(self, score: float) -> MarketAwarenessRegime:
        if score >= 0.25:
            return MarketAwarenessRegime.BULLISH
        if score <= -0.35:
            return MarketAwarenessRegime.RISK_OFF
        if score <= -0.05:
            return MarketAwarenessRegime.CAUTION
        return MarketAwarenessRegime.NEUTRAL

    def _classify_overall_regime(
        self,
        overall_score: float,
        market_views: list[MarketAwarenessMarketView],
    ) -> MarketAwarenessRegime:
        if not market_views:
            return MarketAwarenessRegime.NEUTRAL
        if any(view.regime == MarketAwarenessRegime.RISK_OFF for view in market_views) and overall_score <= -0.15:
            return MarketAwarenessRegime.RISK_OFF
        if overall_score >= 0.25 and all(
            view.regime in {MarketAwarenessRegime.BULLISH, MarketAwarenessRegime.NEUTRAL}
            for view in market_views
        ):
            return MarketAwarenessRegime.BULLISH
        if overall_score <= -0.05 or any(
            view.regime in {MarketAwarenessRegime.CAUTION, MarketAwarenessRegime.RISK_OFF}
            for view in market_views
        ):
            return MarketAwarenessRegime.CAUTION
        return MarketAwarenessRegime.NEUTRAL

    def _market_confidence(self, scores: list[float], *, degraded: bool) -> MarketAwarenessConfidence:
        if degraded:
            return MarketAwarenessConfidence.LOW
        strong = sum(1 for score in scores if abs(score) >= 0.5)
        mixed = sum(1 for score in scores if abs(score) < 0.25)
        if strong >= 4 and mixed <= 1:
            return MarketAwarenessConfidence.HIGH
        if strong >= 3:
            return MarketAwarenessConfidence.MEDIUM
        return MarketAwarenessConfidence.LOW

    def _overall_confidence(
        self,
        market_views: list[MarketAwarenessMarketView],
        data_quality: MarketAwarenessDataQuality,
    ) -> MarketAwarenessConfidence:
        if data_quality.degraded:
            return MarketAwarenessConfidence.LOW
        regimes = {view.regime for view in market_views}
        if len(regimes) > 1:
            high = sum(1 for view in market_views if view.confidence == MarketAwarenessConfidence.HIGH)
            return MarketAwarenessConfidence.MEDIUM if high else MarketAwarenessConfidence.LOW
        high = sum(1 for view in market_views if view.confidence == MarketAwarenessConfidence.HIGH)
        low = sum(1 for view in market_views if view.confidence == MarketAwarenessConfidence.LOW)
        if high >= 2 and low == 0 and data_quality.status == MarketAwarenessDataStatus.COMPLETE:
            return MarketAwarenessConfidence.HIGH
        if high >= 1 and low <= 1:
            return MarketAwarenessConfidence.MEDIUM
        return MarketAwarenessConfidence.LOW

    def _risk_posture_from_regime(
        self,
        regime: MarketAwarenessRegime,
        confidence: MarketAwarenessConfidence,
        data_quality: MarketAwarenessDataQuality,
        *,
        stress_detected: bool,
    ) -> MarketAwarenessRiskPosture:
        if regime == MarketAwarenessRegime.RISK_OFF:
            return MarketAwarenessRiskPosture.PAUSE_NEW_ADDS
        if regime == MarketAwarenessRegime.CAUTION:
            if stress_detected or data_quality.degraded or confidence == MarketAwarenessConfidence.LOW:
                return MarketAwarenessRiskPosture.REDUCE_RISK
            return MarketAwarenessRiskPosture.HOLD_PACE
        if regime == MarketAwarenessRegime.BULLISH:
            if data_quality.status != MarketAwarenessDataStatus.COMPLETE and confidence != MarketAwarenessConfidence.HIGH:
                return MarketAwarenessRiskPosture.HOLD_PACE
            return MarketAwarenessRiskPosture.BUILD_RISK
        return MarketAwarenessRiskPosture.HOLD_PACE

    def _build_actions(
        self,
        risk_posture: MarketAwarenessRiskPosture,
        market_views: list[MarketAwarenessMarketView],
        data_quality: MarketAwarenessDataQuality,
        participation: MarketAwarenessParticipation,
    ) -> list[MarketAwarenessActionItem]:
        actions: list[MarketAwarenessActionItem] = []
        if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK:
            actions.extend(
                [
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.MEDIUM,
                        action_key="build_risk_on_confirmed_strength",
                        text="Build risk gradually where trend, momentum, and breadth are aligned.",
                        rationale="The posture engine sees supportive market structure and enough confirmation to add risk selectively.",
                        markets=[view.market.value for view in market_views if view.regime == MarketAwarenessRegime.BULLISH],
                    ),
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.LOW,
                        action_key="prefer_pullback_entries",
                        text="Prefer pullback or opening-range confirmation instead of chasing stretched moves.",
                        rationale="Even in bullish tape, execution quality matters more than forcing entries.",
                    ),
                ]
            )
        elif risk_posture == MarketAwarenessRiskPosture.HOLD_PACE:
            actions.extend(
                [
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.MEDIUM,
                        action_key="keep_adds_selective",
                        text="Keep adds selective and require confirmation from breadth before sizing up.",
                        rationale="The tape is not broken, but the posture engine does not see enough evidence for aggressive adds.",
                    ),
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.LOW,
                        action_key="review_watchlist",
                        text="Use the session to refresh the watchlist instead of rotating aggressively.",
                        rationale="Mixed conditions reward patience more than constant turnover.",
                    ),
                ]
            )
        elif risk_posture == MarketAwarenessRiskPosture.REDUCE_RISK:
            actions.extend(
                [
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.HIGH,
                        action_key="trim_weak_adds",
                        text="Trim weaker exposures and tighten the bar for any new adds.",
                        rationale="Caution posture with stress signals means the first job is to reduce avoidable downside.",
                    ),
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.MEDIUM,
                        action_key="raise_defense",
                        text="Favor defense, smaller size, and more confirmation before acting.",
                        rationale="Breadth or volatility pressure is already visible in the market inputs.",
                    ),
                ]
            )
        else:
            actions.extend(
                [
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.HIGH,
                        action_key="pause_new_adds",
                        text="Pause new adds and focus on protecting current exposure.",
                        rationale="The posture engine sees risk-off conditions and does not want fresh risk added into weakening tape.",
                    ),
                    MarketAwarenessActionItem(
                        severity=MarketAwarenessActionSeverity.MEDIUM,
                        action_key="review_hedges",
                        text="Review hedges, exits, and forced-risk inventory before the next session.",
                        rationale="Risk-off posture shifts the focus from opportunity capture to capital preservation.",
                    ),
                ]
            )

        if data_quality.status != MarketAwarenessDataStatus.COMPLETE:
            actions.append(
                MarketAwarenessActionItem(
                    severity=MarketAwarenessActionSeverity.MEDIUM,
                    action_key="respect_data_gaps",
                    text="Treat the posture as conservative guidance until missing or fallback-driven inputs are refreshed.",
                    rationale="The snapshot relied on degraded or fallback data, so sizing should stay conservative.",
                )
            )

        actions.append(
            MarketAwarenessActionItem(
                severity=(
                    MarketAwarenessActionSeverity.MEDIUM
                    if participation.decision.value in {"participate", "selective"}
                    else MarketAwarenessActionSeverity.HIGH
                    if participation.decision.value == "avoid"
                    else MarketAwarenessActionSeverity.LOW
                ),
                action_key=f"participation_{participation.decision.value}",
                text=(
                    "Probability and payoff both justify participation, but scale in instead of forcing size."
                    if participation.decision.value == "participate"
                    else "Only participate selectively where setup quality is clearly above average."
                    if participation.decision.value == "selective"
                    else "Wait for better tape confirmation before committing fresh risk."
                    if participation.decision.value == "wait"
                    else "Avoid fresh participation until both win probability and payoff improve."
                ),
                rationale=f"Participation engine: probability {participation.probability:.2f}, odds {participation.odds:.2f}.",
                markets=["CN"],
            )
        )
        actions.extend(self._market_timing_actions(market_views))
        return actions

    def _market_timing_actions(self, market_views: list[MarketAwarenessMarketView]) -> list[MarketAwarenessActionItem]:
        if self._market_calendar is None:
            return []
        actions: list[MarketAwarenessActionItem] = []
        for view in market_views:
            session = self._market_calendar.get_session(view.market)
            if session.phase == "pre_open":
                text = f"Wait for {view.market.value} open confirmation before acting."
            elif session.phase == "open":
                text = f"Use live breadth confirmation before adding risk in {view.market.value}."
            else:
                text = f"{view.market.value} is closed; treat this as a planning signal, not a chase signal."
            actions.append(
                MarketAwarenessActionItem(
                    severity=MarketAwarenessActionSeverity.LOW,
                    action_key=f"{view.market.value.lower()}_session_timing",
                    text=text,
                    rationale=f"Current session phase: {session.phase}.",
                    markets=[view.market.value],
                )
            )
        return actions

    def _strategy_guidance(
        self,
        risk_posture: MarketAwarenessRiskPosture,
        market_views: list[MarketAwarenessMarketView],
        data_quality: MarketAwarenessDataQuality,
        participation: MarketAwarenessParticipation,
    ) -> list[MarketAwarenessStrategyGuidance]:
        us_view = next((view for view in market_views if view.market == Market.US), None)
        hk_view = next((view for view in market_views if view.market == Market.HK), None)
        etf_rationale = "US trend and breadth are supportive enough for rotation adds." if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK else "Keep ETF rotation patient until confirmation improves."
        equity_rationale = "HK/CN momentum sleeves can stay active when breadth holds." if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK else "Breadth deterioration means stock momentum adds should stay selective."
        option_rationale = "Option overlays should stay light when markets are supportive." if risk_posture in {MarketAwarenessRiskPosture.BUILD_RISK, MarketAwarenessRiskPosture.HOLD_PACE} else "Use option overlays defensively when posture turns cautious or risk-off."
        if data_quality.status != MarketAwarenessDataStatus.COMPLETE:
            etf_rationale = f"{etf_rationale} Data quality is not complete, so keep sizing conservative."
            equity_rationale = f"{equity_rationale} Data quality is not complete, so tighten confirmation filters."
            option_rationale = f"{option_rationale} Data quality is not complete, so prefer simpler defensive structures."
        participation_line = (
            f" Participation decision is {participation.decision.value} with probability {participation.probability:.2f} and odds {participation.odds:.2f}."
        )
        etf_rationale = f"{etf_rationale}{participation_line}"
        equity_rationale = f"{equity_rationale}{participation_line}"
        option_rationale = f"{option_rationale}{participation_line}"
        return [
            MarketAwarenessStrategyGuidance(
                strategy_id="strategy_a_etf_rotation",
                stance=(
                    MarketAwarenessStrategyStance.OFFENSE
                    if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK
                    else MarketAwarenessStrategyStance.BALANCED
                    if risk_posture == MarketAwarenessRiskPosture.HOLD_PACE
                    else MarketAwarenessStrategyStance.DEFENSIVE
                ),
                summary=(
                    "Lean into broad ETF winners when leadership is confirmed."
                    if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK
                    else "Keep broad ETF adds selective and size them gradually."
                    if risk_posture == MarketAwarenessRiskPosture.HOLD_PACE
                    else "Favor defensive rotation and skip marginal ETF adds."
                ),
                rationale=etf_rationale,
                action_key="etf_rotation_posture",
            ),
            MarketAwarenessStrategyGuidance(
                strategy_id="strategy_b_equity_momentum",
                stance=(
                    MarketAwarenessStrategyStance.BALANCED
                    if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK
                    else MarketAwarenessStrategyStance.DEFENSIVE
                ),
                summary=(
                    "New stock adds can stay active, but only with breadth confirmation."
                    if risk_posture == MarketAwarenessRiskPosture.BUILD_RISK
                    else "Tighten stock filters and skip lower-quality breakouts."
                ),
                rationale=equity_rationale if hk_view is not None else "Use breadth and volatility as the gating signals for stock momentum adds.",
                action_key="equity_momentum_posture",
            ),
            MarketAwarenessStrategyGuidance(
                strategy_id="strategy_c_option_overlay",
                stance=(
                    MarketAwarenessStrategyStance.BALANCED
                    if risk_posture in {MarketAwarenessRiskPosture.BUILD_RISK, MarketAwarenessRiskPosture.HOLD_PACE}
                    else MarketAwarenessStrategyStance.HEDGED
                ),
                summary=(
                    "Keep option overlays tactical and budget-aware."
                    if risk_posture in {MarketAwarenessRiskPosture.BUILD_RISK, MarketAwarenessRiskPosture.HOLD_PACE}
                    else "Increase defensive overlay priority and avoid expanding directional option risk."
                ),
                rationale=option_rationale if us_view is not None else option_rationale,
                action_key="option_overlay_posture",
            ),
        ]

    def _overall_evidence(
        self,
        market_views: list[MarketAwarenessMarketView],
        data_quality: MarketAwarenessDataQuality,
    ) -> list[MarketAwarenessEvidenceRow]:
        rows = [
            MarketAwarenessEvidenceRow(
                market="overall",
                signal_key=f"{view.market.value.lower()}_summary",
                label=f"{view.market.value} market summary",
                status=self._status_from_regime(view.regime),
                value=view.score,
                unit="score",
                explanation=f"{view.market.value} is {view.regime.value} with {view.confidence.value} confidence.",
            )
            for view in market_views
        ]
        if data_quality.status != MarketAwarenessDataStatus.COMPLETE:
            rows.append(
                MarketAwarenessEvidenceRow(
                    market="overall",
                    signal_key="data_quality",
                    label="Data quality",
                    status=MarketAwarenessSignalStatus.WARNING if data_quality.degraded else MarketAwarenessSignalStatus.MIXED,
                    value=float(len(data_quality.missing_symbols) or len(data_quality.blockers) or len(data_quality.adapter_limitations)),
                    unit="count",
                    explanation="Snapshot quality is reduced by missing or fallback-driven inputs.",
                )
            )
        return rows

    def _build_data_quality(
        self,
        *,
        missing_symbols: list[str],
        fallback_symbols: list[str],
        stale_windows: list[str],
        adapter_limitations: list[str],
        blockers: list[str],
    ) -> MarketAwarenessDataQuality:
        unique_missing = sorted(set(missing_symbols))
        unique_fallback = sorted(set(fallback_symbols))
        unique_stale = sorted(set(stale_windows))
        unique_limitations = sorted(set(adapter_limitations))
        unique_blockers = list(dict.fromkeys(blockers))
        if unique_missing or unique_blockers:
            status = MarketAwarenessDataStatus.DEGRADED
            complete = False
            degraded = True
        elif unique_fallback or unique_stale or unique_limitations:
            status = MarketAwarenessDataStatus.FALLBACK
            complete = False
            degraded = False
        else:
            status = MarketAwarenessDataStatus.COMPLETE
            complete = True
            degraded = False
        return MarketAwarenessDataQuality(
            status=status,
            complete=complete,
            degraded=degraded,
            fallback_driven=bool(unique_fallback),
            missing_symbols=unique_missing,
            stale_windows=unique_stale,
            adapter_limitations=unique_limitations,
            blockers=unique_blockers,
        )

    def _history_snapshot_for_symbols(self, symbols: list[str], start: date, end: date) -> dict[str, object]:
        history_by_symbol: dict[str, list[object]] = {}
        history_source_by_symbol: dict[str, str] = {}
        fallback_symbols: list[str] = []
        missing_symbols: list[str] = []
        blockers: list[str] = []
        with self._market_data.local_history_only():
            local_snapshot = self._market_data.local_history_snapshot(symbols, start, end)
            for symbol in symbols:
                bars = local_snapshot.get(symbol, [])
                if bars:
                    history_by_symbol[symbol] = bars
                    history_source_by_symbol[symbol] = "local"
                    continue
                fallback_snapshot = self._market_data.ensure_history([symbol], start, end)
                fallback_bars = fallback_snapshot.get(symbol, [])
                if fallback_bars:
                    history_by_symbol[symbol] = fallback_bars
                    history_source_by_symbol[symbol] = "fallback"
                    fallback_symbols.append(symbol)
                    continue
                history_source_by_symbol[symbol] = "missing"
                missing_symbols.append(symbol)
                blockers.append(f"Missing benchmark history for {symbol} between {start.isoformat()} and {end.isoformat()}.")
        return {
            "history_by_symbol": history_by_symbol,
            "history_source_by_symbol": history_source_by_symbol,
            "fallback_symbols": fallback_symbols,
            "missing_symbols": missing_symbols,
            "blockers": blockers,
        }

    def _eligible_breadth_instruments(self, market: Market) -> list[Instrument]:
        cross_asset_symbols = {symbol.upper() for symbol in self._config.cross_asset_reference_symbols}
        instruments = self._market_data.list_instruments(
            markets=[market.value],
            asset_classes=sorted(self._BREADTH_ASSET_CLASSES),
            enabled_only=True,
            tradable_only=True,
            liquid_only=True,
            minimum_liquidity_bucket="medium",
        )
        return [
            instrument
            for instrument in instruments
            if instrument.symbol.upper() not in cross_asset_symbols
            and "defensive_bond" not in instrument.tags
            and "real_asset" not in instrument.tags
        ]

    def _select_breadth_constituents(self, instruments: list[Instrument], *, limit: int | None = None) -> list[Instrument]:
        ranked = sorted(
            instruments,
            key=lambda instrument: (
                -self._LIQUIDITY_ORDER.get(instrument.liquidity_bucket, 0),
                -float(instrument.avg_daily_dollar_volume_m or 0.0),
                instrument.asset_class.value,
                instrument.symbol,
            ),
        )
        if limit is None:
            return ranked
        return ranked[:limit]

    def _blocked_signal(
        self,
        market: Market,
        signal_key: str,
        label: str,
        explanation: str,
    ) -> dict[str, object]:
        return {
            "score": -1.0,
            "value": None,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key=signal_key,
                label=label,
                status=MarketAwarenessSignalStatus.BLOCKED,
                value=None,
                unit=None,
                explanation=explanation,
            ),
        }

    def _neutral_signal(
        self,
        market: Market,
        signal_key: str,
        label: str,
        explanation: str,
    ) -> dict[str, object]:
        return {
            "score": 0.0,
            "value": 0.0,
            "evidence": MarketAwarenessEvidenceRow(
                market=market.value,
                signal_key=signal_key,
                label=label,
                status=MarketAwarenessSignalStatus.MIXED,
                value=0.0,
                unit="score",
                explanation=explanation,
            ),
            "adapter_limitations": [],
        }

    @staticmethod
    def _instrument_key(instrument: Instrument) -> str:
        return f"{instrument.market.value}:{instrument.symbol}"

    @staticmethod
    def _market_basket(market: Market, symbols: list[str]) -> dict[str, object]:
        normalized = [symbol.upper() for symbol in symbols]
        benchmark_symbol = normalized[0]
        return {
            "market": market.value,
            "benchmark_symbol": benchmark_symbol,
            "reference_symbols": normalized[1:],
        }

    @staticmethod
    def _status_from_regime(regime: MarketAwarenessRegime) -> MarketAwarenessSignalStatus:
        if regime == MarketAwarenessRegime.BULLISH:
            return MarketAwarenessSignalStatus.SUPPORTIVE
        if regime == MarketAwarenessRegime.NEUTRAL:
            return MarketAwarenessSignalStatus.MIXED
        return MarketAwarenessSignalStatus.WARNING

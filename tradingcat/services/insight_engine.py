"""Insight Engine — orchestrates detectors, persists insights, publishes events.

Responsibilities (Round 1):
1. Pull the watchlist (enabled + tradable instruments + portfolio holdings).
2. Resolve a per-market benchmark from MarketAwareness baskets.
3. Fetch enough bar history for each detector's required lookback.
4. Run detectors, dedupe by stable id, persist to InsightStore.
5. Publish an ``EventType.INSIGHT`` event so consumers (alerts UI, future
   notifiers) can react without re-querying the store.

Round 2 / 3 will plug in ``SectorDivergenceDetector`` and ``FlowAnomalyDetector``
behind the same orchestration.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Iterable

from tradingcat.domain.models import (
    Bar,
    Insight,
    Instrument,
    Market,
)
from tradingcat.repositories.insight_store import InsightStore
from tradingcat.services.insight_detectors import (
    CorrelationBreakDetector,
    SectorDivergenceDetector,
)
from tradingcat.services.market_awareness import MarketAwarenessService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.realtime import Event, EventBus, EventType


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InsightEngineRunResult:
    as_of: date
    produced: list[str]
    suppressed_duplicates: int
    expired: int


class InsightEngine:
    def __init__(
        self,
        *,
        store: InsightStore,
        market_data: MarketDataService,
        market_awareness: MarketAwarenessService,
        event_bus: EventBus | None = None,
        correlation_detector: CorrelationBreakDetector | None = None,
        sector_detector: SectorDivergenceDetector | None = None,
        portfolio_symbols_provider=None,
    ) -> None:
        self._store = store
        self._market_data = market_data
        self._market_awareness = market_awareness
        self._event_bus = event_bus
        self._correlation_detector = correlation_detector or CorrelationBreakDetector()
        self._sector_detector = sector_detector or SectorDivergenceDetector()
        # Optional callable returning current portfolio symbols. Engine treats
        # them as part of the watchlist even if not in the persisted catalog.
        self._portfolio_symbols_provider = portfolio_symbols_provider

    @property
    def store(self) -> InsightStore:
        return self._store

    def list_active(self, **kwargs) -> list[Insight]:
        return self._store.list(**kwargs)

    def run(self, *, as_of: date | None = None, now: datetime | None = None) -> InsightEngineRunResult:
        evaluation_date = as_of or date.today()
        triggered_at = now or datetime.now(timezone.utc)

        expired = self._store.expire_stale(now=triggered_at)

        watchlist = self._collect_watchlist()
        if not watchlist:
            logger.info("insight_engine: watchlist is empty; nothing to evaluate")
            return InsightEngineRunResult(
                as_of=evaluation_date, produced=[], suppressed_duplicates=0, expired=expired
            )

        benchmarks = self._resolve_benchmarks()
        bars_by_symbol = self._fetch_bars(watchlist, benchmarks, evaluation_date)

        candidate_insights: list[Insight] = []
        candidate_insights.extend(
            self._correlation_detector.detect(
                as_of=evaluation_date,
                watchlist=watchlist,
                bars_by_symbol=bars_by_symbol,
                benchmark_by_market=benchmarks,
                now=triggered_at,
            )
        )
        candidate_insights.extend(
            self._sector_detector.detect(
                as_of=evaluation_date,
                watchlist=watchlist,
                bars_by_symbol=bars_by_symbol,
                benchmark_by_market=benchmarks,
                now=triggered_at,
            )
        )

        produced: list[str] = []
        suppressed = 0
        for insight in candidate_insights:
            existing = self._store.get(insight.id)
            if existing is not None and existing.user_action.value != "pending":
                # User already acted on this id; do not overwrite their state.
                suppressed += 1
                continue
            if existing is not None:
                suppressed += 1  # same id — refresh evidence but do not double-count
            self._store.upsert(insight)
            self._publish(insight)
            produced.append(insight.id)

        return InsightEngineRunResult(
            as_of=evaluation_date,
            produced=produced,
            suppressed_duplicates=suppressed,
            expired=expired,
        )

    # --- internals -----------------------------------------------------------

    def _collect_watchlist(self) -> list[Instrument]:
        instruments = self._market_data.list_instruments(
            enabled_only=True,
            tradable_only=True,
        )
        seen: set[tuple[str, str]] = set()
        out: list[Instrument] = []
        for instrument in instruments:
            key = (instrument.symbol, instrument.market.value)
            if key in seen:
                continue
            seen.add(key)
            out.append(instrument)

        if self._portfolio_symbols_provider is not None:
            try:
                extra_symbols: Iterable[str] = self._portfolio_symbols_provider() or []
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.warning("insight_engine: portfolio symbol provider failed: %s", exc)
                extra_symbols = []
            for symbol in extra_symbols:
                instrument = self._market_data.get_instrument(symbol, strict=False)
                if instrument is None:
                    continue
                key = (instrument.symbol, instrument.market.value)
                if key in seen:
                    continue
                seen.add(key)
                out.append(instrument)
        return out

    def _resolve_benchmarks(self) -> dict[Market, str]:
        baskets = self._market_awareness.benchmark_baskets()
        resolved: dict[Market, str] = {}
        for market in (Market.US, Market.HK, Market.CN):
            payload = baskets.get(market.value) or {}
            symbol = payload.get("benchmark_symbol")
            if isinstance(symbol, str) and symbol:
                resolved[market] = symbol
        return resolved

    def _fetch_bars(
        self,
        watchlist: list[Instrument],
        benchmarks: dict[Market, str],
        as_of: date,
    ) -> dict[str, list[Bar]]:
        lookback = max(
            self._correlation_detector.required_lookback_days(),
            self._sector_detector.required_lookback_days(),
        )
        # Calendar days × 1.6 buffers weekends/holidays so we still see ~lookback
        # trading days after gaps.
        start = as_of - timedelta(days=int(lookback * 1.6) + 5)
        symbols: set[str] = {benchmark for benchmark in benchmarks.values()}
        symbols.update(instrument.symbol for instrument in watchlist)

        bars_by_symbol: dict[str, list[Bar]] = {}
        for symbol in sorted(symbols):
            try:
                bars = self._market_data.get_bars(symbol, start, as_of)
            except Exception as exc:  # noqa: BLE001 — defensive
                logger.warning("insight_engine: get_bars failed for %s: %s", symbol, exc)
                bars = []
            bars_by_symbol[symbol] = bars
        return bars_by_symbol

    def _publish(self, insight: Insight) -> None:
        if self._event_bus is None:
            return
        try:
            self._event_bus.publish(
                Event(
                    type=EventType.INSIGHT,
                    data={
                        "insight_id": insight.id,
                        "kind": insight.kind.value,
                        "severity": insight.severity.value,
                    },
                )
            )
        except Exception as exc:  # noqa: BLE001 — bus failure shouldn't break engine
            logger.warning("insight_engine: event publish failed: %s", exc)

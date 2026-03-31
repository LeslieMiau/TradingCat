from __future__ import annotations

import asyncio
from contextlib import contextmanager
import logging
from datetime import date, timedelta
import math

from tradingcat.adapters.base import MarketDataAdapter
from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import Bar, CorporateAction, FxRate, Instrument
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository


logger = logging.getLogger(__name__)


class MarketDataService:
    _COVERAGE_THRESHOLD = 0.95
    _LIQUIDITY_ORDER = {"low": 0, "medium": 1, "high": 2}
    _BOOTSTRAP_SAMPLE_KEYS = {
        f"{instrument.market.value}:{instrument.symbol}"
        for instrument in sample_instruments()
    }

    def __init__(
        self,
        adapter: MarketDataAdapter,
        instruments: InstrumentCatalogRepository,
        history: HistoricalMarketDataRepository,
    ) -> None:
        self._adapter = adapter
        self._instruments = instruments
        self._history = history
        self._catalog = instruments.load()
        self._catalog_version = instruments.version_token()
        self._local_history_only_depth = 0
        if not self._catalog:
            self.seed_catalog(sample_instruments())

    def seed_catalog(self, seed_instruments: list[Instrument]) -> None:
        changed = False
        for instrument in seed_instruments:
            key = self._key(instrument)
            if key not in self._catalog:
                self._catalog[key] = instrument
                changed = True
        if changed:
            self._instruments.save(self._catalog)
            self._catalog_version = self._instruments.version_token()

    def reset_cache(self) -> None:
        self._history.clear()
        self._instruments.clear()
        self._catalog = {}
        self._catalog_version = self._instruments.version_token()
        self.seed_catalog(sample_instruments())

    @contextmanager
    def local_history_only(self):
        self._local_history_only_depth += 1
        try:
            yield self
        finally:
            self._local_history_only_depth = max(0, self._local_history_only_depth - 1)

    def upsert_instruments(self, instruments: list[Instrument]) -> dict[str, object]:
        self._refresh_catalog_if_needed()
        changed = False
        for instrument in instruments:
            key = self._key(instrument)
            if self._catalog.get(key) != instrument:
                self._catalog[key] = instrument
                changed = True
        if changed:
            self._instruments.save(self._catalog)
            self._catalog_version = self._instruments.version_token()
        return {
            "instrument_count": len(self._catalog),
            "updated_symbols": sorted(instrument.symbol for instrument in instruments),
            "changed": changed,
        }

    def list_instruments(
        self,
        *,
        markets: list[str] | None = None,
        asset_classes: list[str] | None = None,
        enabled_only: bool = False,
        tradable_only: bool = False,
        liquid_only: bool = False,
        minimum_liquidity_bucket: str = "medium",
    ) -> list[Instrument]:
        self._refresh_catalog_if_needed()
        market_filter = {item.upper() for item in (markets or [])}
        asset_class_filter = {item.lower() for item in (asset_classes or [])}
        minimum_rank = self._liquidity_rank(minimum_liquidity_bucket)
        instruments = []
        for instrument in self._catalog.values():
            if market_filter and instrument.market.value not in market_filter:
                continue
            if asset_class_filter and instrument.asset_class.value not in asset_class_filter:
                continue
            if enabled_only and not instrument.enabled:
                continue
            if tradable_only and not instrument.tradable:
                continue
            if liquid_only and self._liquidity_rank(instrument.liquidity_bucket) < minimum_rank:
                continue
            instruments.append(instrument)
        return sorted(instruments, key=lambda item: (item.market.value, item.asset_class.value, item.symbol))

    def research_universe(
        self,
        *,
        markets: list[str] | None = None,
        asset_classes: list[str] | None = None,
        minimum_liquidity_bucket: str = "medium",
    ) -> list[Instrument]:
        instruments = self.list_instruments(
            markets=markets,
            asset_classes=asset_classes,
            enabled_only=True,
            tradable_only=True,
            liquid_only=True,
            minimum_liquidity_bucket=minimum_liquidity_bucket,
        )
        custom_instruments = [
            instrument
            for instrument in instruments
            if self._key(instrument) not in self._BOOTSTRAP_SAMPLE_KEYS
        ]
        return custom_instruments or instruments

    def diagnostic_targets(self, symbols: list[str] | None = None) -> list[Instrument]:
        explicit_targets = [instrument for instrument in self.list_instruments() if not symbols or instrument.symbol in symbols]
        if explicit_targets:
            return explicit_targets
        research_targets = self.research_universe()
        if research_targets:
            return research_targets
        return sample_instruments()

    def get_instrument(self, symbol: str, strict: bool = True) -> Instrument | None:
        return self._resolve_instrument(symbol, strict=strict)

    def fetch_quotes(self, instruments_or_symbols: list[Instrument] | list[str]) -> dict[str, float]:
        instruments = self._resolve_instruments(instruments_or_symbols)
        if not instruments:
            return {}
        try:
            return self._adapter.fetch_quotes(instruments)
        except Exception:
            logger.exception("Failed to fetch quotes", extra={"symbols": [instrument.symbol for instrument in instruments]})
            return {}

    async def fetch_quotes_async(self, instruments_or_symbols: list[Instrument] | list[str]) -> dict[str, float]:
        return await asyncio.to_thread(self.fetch_quotes, instruments_or_symbols)

    def fetch_option_chain(self, underlying: str, as_of: date, *, market: str | None = None):
        self._refresh_catalog_if_needed()
        normalized_market = None
        if market:
            normalized_market = next((item.market for item in self._catalog.values() if item.market.value == market.upper()), None)
        return self._adapter.fetch_option_chain(underlying, as_of, market=normalized_market)

    def fetch_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        instrument = self._resolve_instrument(symbol)
        try:
            return self._adapter.fetch_bars(instrument, start, end)
        except Exception:
            logger.exception(
                "Failed to fetch bars",
                extra={"symbol": symbol, "start": start.isoformat(), "end": end.isoformat()},
            )
            return []

    async def fetch_bars_async(self, symbol: str, start: date, end: date) -> list[Bar]:
        return await asyncio.to_thread(self.fetch_bars, symbol, start, end)

    async def get_bars_async(self, symbol: str, start: date, end: date) -> list[Bar]:
        return await asyncio.to_thread(self.get_bars, symbol, start, end)

    def sync_history(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        start_date = start or (date.today() - timedelta(days=30))
        end_date = end or date.today()
        targets = [item for item in self.list_instruments() if not symbols or item.symbol in symbols]
        synced: list[dict[str, object]] = []
        failures: list[dict[str, object]] = []

        for instrument in targets:
            try:
                bars = self._adapter.fetch_bars(instrument, start_date, end_date)
                self._history.save_bars(instrument, bars)
                actions = self._adapter.fetch_corporate_actions(instrument, start_date, end_date) if include_corporate_actions else []
                if include_corporate_actions:
                    self._history.save_corporate_actions(instrument, actions)
                synced.append(
                    {
                        "symbol": instrument.symbol,
                        "market": instrument.market,
                        "bar_count": len(bars),
                        "corporate_action_count": len(actions),
                    }
                )
            except Exception as exc:
                logger.exception("History sync failed", extra={"symbol": instrument.symbol, "market": instrument.market.value})
                failures.append(
                    {
                        "symbol": instrument.symbol,
                        "market": instrument.market,
                        "error": str(exc),
                    }
                )

        return {
            "start": start_date,
            "end": end_date,
            "instrument_count": len(targets),
            "reports": synced,
            "failure_count": len(failures),
            "failures": failures,
        }

    def summarize_history_coverage(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, object]:
        start_date = start or (date.today() - timedelta(days=30))
        end_date = end or date.today()
        targets = [item for item in self.list_instruments() if not symbols or item.symbol in symbols]
        expected_dates = self._expected_trading_dates(start_date, end_date)
        observed_dates_by_market: dict[str, list[str]] = {}
        for instrument in targets:
            bars = self._history.load_bars(instrument, start_date, end_date)
            available_dates = sorted({bar.timestamp.date().isoformat() for bar in bars})
            if available_dates:
                observed_dates_by_market.setdefault(instrument.market.value, [])
                observed_dates_by_market[instrument.market.value].extend(available_dates)
        normalized_observed_by_market = {
            market: sorted(set(days))
            for market, days in observed_dates_by_market.items()
        }

        reports: list[dict[str, object]] = []
        for instrument in targets:
            bars = self._history.load_bars(instrument, start_date, end_date)
            available_dates = sorted({bar.timestamp.date().isoformat() for bar in bars})
            market_expected_dates = normalized_observed_by_market.get(instrument.market.value)
            expected_dates_for_instrument = market_expected_dates or [current.isoformat() for current in expected_dates]
            missing_dates = [current for current in expected_dates_for_instrument if current not in available_dates]
            coverage_ratio = (
                round(len(available_dates) / len(expected_dates_for_instrument), 4)
                if expected_dates_for_instrument
                else 1.0
            )
            reports.append(
                {
                    "symbol": instrument.symbol,
                    "market": instrument.market,
                    "bar_count": len(available_dates),
                    "expected_count": len(expected_dates_for_instrument),
                    "coverage_ratio": coverage_ratio,
                    "missing_count": len(missing_dates),
                    "missing_preview": missing_dates[:10],
                    "first_bar_date": available_dates[0] if available_dates else None,
                    "last_bar_date": available_dates[-1] if available_dates else None,
                }
            )

        minimum_coverage_ratio = round(min((float(report["coverage_ratio"]) for report in reports), default=1.0), 4)
        complete = sum(1 for report in reports if float(report["coverage_ratio"]) >= self._COVERAGE_THRESHOLD)
        missing_symbols = [
            str(report["symbol"])
            for report in reports
            if float(report["coverage_ratio"]) < self._COVERAGE_THRESHOLD or int(report["missing_count"]) > 0
        ]
        missing_windows = [
            {
                "symbol": report["symbol"],
                "market": report["market"],
                "missing_count": report["missing_count"],
                "missing_preview": report["missing_preview"],
                "first_missing_date": report["missing_preview"][0] if report["missing_preview"] else None,
                "last_missing_date": report["missing_preview"][-1] if report["missing_preview"] else None,
            }
            for report in reports
            if int(report["missing_count"]) > 0
        ]
        blockers = self._coverage_blockers(
            minimum_coverage_ratio=minimum_coverage_ratio,
            missing_symbols=missing_symbols,
            start_date=start_date,
            end_date=end_date,
        )
        return {
            "start": start_date,
            "end": end_date,
            "instrument_count": len(targets),
            "expected_trading_days": len(expected_dates),
            "complete_instruments": complete,
            "minimum_coverage_ratio": minimum_coverage_ratio,
            "minimum_required_ratio": self._COVERAGE_THRESHOLD,
            "missing_symbols": missing_symbols,
            "missing_windows": missing_windows,
            "blocked": bool(blockers),
            "blocker_count": len(blockers),
            "blockers": blockers,
            "reports": reports,
        }

    def repair_history_gaps(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        coverage_before = self.summarize_history_coverage(symbols=symbols, start=start, end=end)
        repair_targets = [report for report in coverage_before["reports"] if int(report["missing_count"]) > 0]
        if not repair_targets:
            recheck = self._repair_recheck(coverage_before, coverage_before)
            return {
                "start": coverage_before["start"],
                "end": coverage_before["end"],
                "instrument_count": 0,
                "reports": [],
                "repaired_symbols": [],
                "repair_count": 0,
                "coverage_before": coverage_before,
                "coverage_after": coverage_before,
                "recheck": recheck,
            }
        repaired_symbols = [str(report["symbol"]) for report in repair_targets]
        sync = self.sync_history(
            symbols=repaired_symbols,
            start=coverage_before["start"],
            end=coverage_before["end"],
            include_corporate_actions=include_corporate_actions,
        )
        coverage_after = self.summarize_history_coverage(symbols=repaired_symbols, start=sync["start"], end=sync["end"])
        return {
            **sync,
            "repaired_symbols": repaired_symbols,
            "repair_count": len(repaired_symbols),
            "coverage_before": coverage_before,
            "coverage_after": coverage_after,
            "recheck": self._repair_recheck(coverage_before, coverage_after),
        }

    def _coverage_blockers(
        self,
        *,
        minimum_coverage_ratio: float,
        missing_symbols: list[str],
        start_date: date,
        end_date: date,
    ) -> list[str]:
        if not missing_symbols:
            return []
        return [
            f"Minimum history coverage is {minimum_coverage_ratio:.2%}, below the {self._COVERAGE_THRESHOLD:.0%} requirement.",
            f"Missing history detected for: {', '.join(missing_symbols[:5])}.",
            f"Run POST /data/history/sync for the affected symbols between {start_date.isoformat()} and {end_date.isoformat()}, then recheck GET /data/history/coverage.",
        ]

    def _repair_recheck(self, before: dict[str, object], after: dict[str, object]) -> dict[str, object]:
        before_reports = {
            str(report["symbol"]): report
            for report in before.get("reports", [])
        }
        after_reports = {
            str(report["symbol"]): report
            for report in after.get("reports", [])
        }
        improved_symbols = []
        remaining_symbols = list(after.get("missing_symbols", []))
        for symbol, after_report in after_reports.items():
            before_report = before_reports.get(symbol, {})
            if int(after_report.get("missing_count", 0)) < int(before_report.get("missing_count", 0)):
                improved_symbols.append(symbol)
        return {
            "ready": not remaining_symbols,
            "improved_symbols": sorted(improved_symbols),
            "improved_count": len(improved_symbols),
            "remaining_symbols": remaining_symbols,
            "remaining_count": len(remaining_symbols),
            "minimum_coverage_ratio_before": round(float(before.get("minimum_coverage_ratio", 0.0)), 4),
            "minimum_coverage_ratio_after": round(float(after.get("minimum_coverage_ratio", 0.0)), 4),
        }

    def get_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        instrument = self._resolve_instrument(symbol)
        return self._history.load_bars(instrument, start, end)

    def get_corporate_actions(self, symbol: str, start: date, end: date) -> list[dict]:
        instrument = self._resolve_instrument(symbol)
        return self._history.load_corporate_actions(instrument, start, end)

    def summarize_corporate_actions_coverage(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        *,
        fetch_missing: bool = True,
    ) -> dict[str, object]:
        start_date = start or (date.today() - timedelta(days=30))
        end_date = end or date.today()
        targets = [item for item in self.list_instruments() if not symbols or item.symbol in symbols]
        actions_by_symbol: dict[str, list[CorporateAction]] = {}
        reports: list[dict[str, object]] = []
        available_symbols: list[str] = []
        confirmed_none_symbols: list[str] = []
        missing_symbols: list[str] = []

        for instrument in targets:
            actions = self._history.load_corporate_actions(instrument, start_date, end_date)
            error: str | None = None
            if not actions and fetch_missing:
                try:
                    fetched_actions = self._adapter.fetch_corporate_actions(instrument, start_date, end_date)
                    self._history.save_corporate_actions(instrument, fetched_actions)
                    actions = self._history.load_corporate_actions(instrument, start_date, end_date)
                except Exception as exc:
                    logger.exception(
                        "Failed to fetch corporate actions",
                        extra={"symbol": instrument.symbol, "market": instrument.market.value},
                    )
                    error = str(exc)

            actions_by_symbol[instrument.symbol] = self._deserialize_corporate_actions(instrument, actions, start_date)

            if actions:
                status = "available"
                available_symbols.append(instrument.symbol)
            elif error or not fetch_missing:
                status = "missing"
                missing_symbols.append(instrument.symbol)
            else:
                status = "confirmed_none"
                confirmed_none_symbols.append(instrument.symbol)

            effective_dates = [
                str(
                    action.get("ex_div_date")
                    or action.get("record_date")
                    or action.get("effective_date")
                )
                for action in actions
                if action.get("ex_div_date") or action.get("record_date") or action.get("effective_date")
            ]
            reports.append(
                {
                    "symbol": instrument.symbol,
                    "market": instrument.market,
                    "status": status,
                    "action_count": len(actions),
                    "first_effective_date": min(effective_dates) if effective_dates else None,
                    "last_effective_date": max(effective_dates) if effective_dates else None,
                    "error": error,
                }
            )

        blockers = self._corporate_action_blockers(missing_symbols)
        return {
            "start": start_date,
            "end": end_date,
            "instrument_count": len(targets),
            "ready": not missing_symbols,
            "status": "blocked" if missing_symbols else "ready",
            "available_symbols": available_symbols,
            "confirmed_none_symbols": confirmed_none_symbols,
            "missing_symbols": missing_symbols,
            "blocker_count": len(blockers),
            "blockers": blockers,
            "reports": reports,
            "actions_by_symbol": actions_by_symbol,
        }

    def sync_fx_rates(
        self,
        base_currency: str = "CNY",
        quote_currencies: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
    ) -> dict[str, object]:
        start_date = start or (date.today() - timedelta(days=30))
        end_date = end or date.today()
        currencies = sorted(
            {
                instrument.currency.upper()
                for instrument in self.list_instruments()
                if instrument.currency.upper() != base_currency.upper()
            }
        )
        if quote_currencies:
            currencies = [currency.upper() for currency in quote_currencies if currency.upper() != base_currency.upper()]
        collected: list[FxRate] = []
        source = "synthetic"
        for quote_currency in currencies:
            adapter_rates: list[FxRate] = []
            if hasattr(self._adapter, "fetch_fx_rates"):
                try:
                    adapter_rates = self._adapter.fetch_fx_rates(base_currency.upper(), quote_currency, start_date, end_date)
                except Exception:
                    logger.exception("Adapter fetch_fx_rates failed for %s/%s, falling back to synthetic", base_currency, quote_currency)
            if adapter_rates:
                collected.extend(adapter_rates)
                source = "adapter"
            else:
                collected.extend(self._generate_fx_series(base_currency.upper(), quote_currency, start_date, end_date))
        self._history.save_fx_rates(collected)
        return {
            "base_currency": base_currency.upper(),
            "quote_currencies": currencies,
            "rate_count": len(collected),
            "source": source,
            "start": start_date,
            "end": end_date,
        }

    def get_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        return self._history.load_fx_rates(base_currency.upper(), quote_currency.upper(), start, end)

    def summarize_fx_coverage(
        self,
        base_currency: str,
        quote_currencies: list[str] | None,
        start: date,
        end: date,
        *,
        fetch_missing: bool = True,
    ) -> dict[str, object]:
        normalized = sorted({currency.upper() for currency in (quote_currencies or []) if currency.upper() != base_currency.upper()})
        if not normalized:
            return {
                "base_currency": base_currency.upper(),
                "quote_currencies": [],
                "ready": True,
                "status": "ready",
                "missing_quote_currencies": [],
                "blocker_count": 0,
                "blockers": [],
                "reports": [],
                "rates_by_pair": {},
                "start": start,
                "end": end,
            }

        rates_by_pair: dict[str, list[FxRate]] = {}
        reports: list[dict[str, object]] = []
        available_quote_currencies: list[str] = []
        missing_quote_currencies: list[str] = []

        for quote_currency in normalized:
            rates = self._history.load_fx_rates(base_currency.upper(), quote_currency, start, end)
            if not rates and fetch_missing:
                self.sync_fx_rates(base_currency=base_currency.upper(), quote_currencies=[quote_currency], start=start, end=end)
                rates = self._history.load_fx_rates(base_currency.upper(), quote_currency, start, end)

            pair = f"{quote_currency}/{base_currency.upper()}"
            if rates:
                rates_by_pair[pair] = rates
                available_quote_currencies.append(quote_currency)
                status = "available"
            else:
                missing_quote_currencies.append(quote_currency)
                status = "missing"

            reports.append(
                {
                    "pair": pair,
                    "base_currency": base_currency.upper(),
                    "quote_currency": quote_currency,
                    "status": status,
                    "rate_count": len(rates),
                    "first_date": rates[0].date if rates else None,
                    "last_date": rates[-1].date if rates else None,
                }
            )

        blockers = self._fx_blockers(base_currency.upper(), missing_quote_currencies)
        return {
            "base_currency": base_currency.upper(),
            "quote_currencies": normalized,
            "available_quote_currencies": available_quote_currencies,
            "missing_quote_currencies": missing_quote_currencies,
            "ready": not missing_quote_currencies,
            "status": "blocked" if missing_quote_currencies else "ready",
            "blocker_count": len(blockers),
            "blockers": blockers,
            "reports": reports,
            "rates_by_pair": rates_by_pair,
            "start": start,
            "end": end,
        }

    def ensure_history(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
        if self._local_history_only_depth > 0:
            return self.local_history_snapshot(symbols, start, end)
        return self._load_history(symbols, start, end, persist=True, fetch_missing=True)

    def history_snapshot(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
        return self._load_history(symbols, start, end, persist=False, fetch_missing=True)

    def local_history_snapshot(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
        return self._load_history(symbols, start, end, persist=False, fetch_missing=False)

    def _load_history(
        self,
        symbols: list[str],
        start: date,
        end: date,
        *,
        persist: bool,
        fetch_missing: bool,
    ) -> dict[str, list[Bar]]:
        targets = [self._resolve_instrument(symbol) for symbol in symbols if self._resolve_instrument(symbol, strict=False) is not None]
        loaded: dict[str, list[Bar]] = {}
        missing_symbols: list[str] = []

        for instrument in targets:
            bars = self._history.load_bars(instrument, start, end)
            if not bars or self._history_too_sparse_for_window(bars, start, end):
                missing_symbols.append(instrument.symbol)
            else:
                loaded[instrument.symbol] = bars

        if missing_symbols:
            if persist:
                self.sync_history(symbols=missing_symbols, start=start, end=end, include_corporate_actions=True)
                for symbol in missing_symbols:
                    instrument = self._resolve_instrument(symbol)
                    bars = self._history.load_bars(instrument, start, end)
                    if bars:
                        loaded[symbol] = bars
            elif fetch_missing:
                for symbol in missing_symbols:
                    bars = self.fetch_bars(symbol, start, end)
                    if bars:
                        loaded[symbol] = bars

        return loaded

    def _history_too_sparse_for_window(self, bars: list[Bar], start: date, end: date) -> bool:
        expected_trading_days = len(self._expected_trading_dates(start, end))
        if expected_trading_days < 20:
            return False
        observed_dates = {bar.timestamp.date().isoformat() for bar in bars}
        return len(observed_dates) < max(20, int(expected_trading_days * 0.5))

    def ensure_corporate_actions(self, symbols: list[str], start: date, end: date) -> dict[str, list[CorporateAction]]:
        coverage = self.summarize_corporate_actions_coverage(symbols=symbols, start=start, end=end)
        return dict(coverage.get("actions_by_symbol", {}))

    def ensure_fx_rates(self, base_currency: str, quote_currencies: list[str], start: date, end: date) -> dict[str, list[FxRate]]:
        coverage = self.summarize_fx_coverage(base_currency=base_currency, quote_currencies=quote_currencies, start=start, end=end)
        return dict(coverage.get("rates_by_pair", {}))

    def _resolve_instrument(self, symbol: str, strict: bool = True) -> Instrument | None:
        self._refresh_catalog_if_needed()
        matches = [instrument for instrument in self._catalog.values() if instrument.symbol == symbol]
        if not matches:
            if strict:
                raise KeyError(f"Unknown instrument symbol: {symbol}")
            return None
        return matches[0]

    def _refresh_catalog_if_needed(self) -> None:
        current_version = self._instruments.version_token()
        if current_version == self._catalog_version:
            return
        self._catalog = self._instruments.load()
        self._catalog_version = current_version
        if not self._catalog:
            self.seed_catalog(sample_instruments())

    def _resolve_instruments(self, instruments_or_symbols: list[Instrument] | list[str]) -> list[Instrument]:
        resolved: list[Instrument] = []
        for item in instruments_or_symbols:
            if isinstance(item, Instrument):
                resolved.append(item)
                continue
            instrument = self._resolve_instrument(str(item), strict=False)
            if instrument is not None:
                resolved.append(instrument)
        return resolved

    def _key(self, instrument: Instrument) -> str:
        return f"{instrument.market.value}:{instrument.symbol}"

    def _liquidity_rank(self, bucket: str) -> int:
        return self._LIQUIDITY_ORDER.get(str(bucket).lower(), self._LIQUIDITY_ORDER["medium"])

    def _expected_trading_dates(self, start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        return days

    def _generate_fx_series(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        from tradingcat.adapters.yfinance_adapter import YFinanceMarketDataAdapter
        if isinstance(self._adapter, YFinanceMarketDataAdapter):
            real = self._fetch_fx_from_yfinance(base_currency, quote_currency, start, end)
            if real:
                return real
        return self._synthetic_fx_series(base_currency, quote_currency, start, end)

    def _fetch_fx_from_yfinance(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        try:
            import yfinance as yf
        except ImportError:
            return []
        ticker = f"{quote_currency.upper()}{base_currency.upper()}=X"
        try:
            df = yf.download(ticker, start=start.isoformat(), end=(end + timedelta(days=1)).isoformat(), progress=False)
            if df.empty:
                return []
            if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
                df = df.droplevel(level=1, axis=1)
            rates: list[FxRate] = []
            for idx, row in df.iterrows():
                rate_date = idx.date() if hasattr(idx, "date") else idx
                close = float(row["Close"])
                if close <= 0 or math.isnan(close):
                    continue
                rates.append(FxRate(
                    base_currency=base_currency.upper(),
                    quote_currency=quote_currency.upper(),
                    date=rate_date,
                    rate=round(close, 6),
                ))
            if rates:
                logger.info("Fetched %d real FX rates for %s from yfinance", len(rates), ticker)
            return rates
        except Exception:
            logger.warning("YFinance FX fetch failed for %s, falling back to synthetic", ticker, exc_info=True)
            return []

    def _synthetic_fx_series(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        anchor_rates = {
            ("CNY", "USD"): 7.10,
            ("CNY", "HKD"): 0.91,
            ("USD", "HKD"): 7.80,
        }
        pair = (base_currency.upper(), quote_currency.upper())
        inverse_pair = (quote_currency.upper(), base_currency.upper())
        if pair in anchor_rates:
            base_rate = anchor_rates[pair]
        elif inverse_pair in anchor_rates:
            base_rate = 1.0 / anchor_rates[inverse_pair]
        else:
            base_rate = 1.0

        rates: list[FxRate] = []
        seed = sum(ord(char) for char in f"{base_currency}/{quote_currency}") % 11
        current = date(start.year, start.month, 1)
        month_index = 0
        while current <= end:
            effective_date = self._month_effective_date(current, start, end)
            seasonal = math.sin((month_index + 1 + seed) / 3) * 0.003
            rate = round(base_rate * (1 + seasonal), 6)
            rates.append(
                FxRate(
                    base_currency=base_currency.upper(),
                    quote_currency=quote_currency.upper(),
                    date=effective_date,
                    rate=rate,
                )
            )
            month_index += 1
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)
        return rates

    def _month_effective_date(self, month_start: date, start: date, end: date) -> date:
        if month_start.month == 12:
            next_month = date(month_start.year + 1, 1, 1)
        else:
            next_month = date(month_start.year, month_start.month + 1, 1)
        candidate = min(end, next_month - timedelta(days=1))
        candidate = max(start, candidate)
        while candidate.weekday() >= 5 and candidate > month_start:
            candidate -= timedelta(days=1)
        return candidate

    def _deserialize_corporate_actions(self, instrument: Instrument, actions: list[dict], start: date) -> list[CorporateAction]:
        return [
            CorporateAction(
                instrument=instrument,
                effective_date=date.fromisoformat(
                    str(
                        action.get("ex_div_date")
                        or action.get("record_date")
                        or action.get("effective_date")
                        or start.isoformat()
                    )
                ),
                action_type=str(action.get("action") or action.get("action_type") or "unknown"),
                cash_amount=float(action.get("cash_amount") or action.get("dividend_amount") or 0.0),
                ratio=float(action.get("ratio") or action.get("split_ratio") or 1.0),
                currency=str(action.get("currency") or instrument.currency),
                metadata={key: value for key, value in action.items() if key not in {"action", "action_type"}},
            )
            for action in actions
        ]

    def _corporate_action_blockers(self, missing_symbols: list[str]) -> list[str]:
        if not missing_symbols:
            return []
        joined = ", ".join(sorted(dict.fromkeys(missing_symbols)))
        return [
            f"Corporate action coverage is unavailable for: {joined}.",
            "Run POST /data/history/sync with include_corporate_actions=true for the affected symbols, then recheck GET /data/history/corporate-actions.",
        ]

    def _fx_blockers(self, base_currency: str, missing_quote_currencies: list[str]) -> list[str]:
        if not missing_quote_currencies:
            return []
        joined = ", ".join(sorted(dict.fromkeys(missing_quote_currencies)))
        return [
            f"FX coverage into {base_currency} is unavailable for: {joined}.",
            f"Run POST /data/fx/sync for the missing quote currencies against {base_currency}, then recheck GET /data/fx/rates.",
        ]

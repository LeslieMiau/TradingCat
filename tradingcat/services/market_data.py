from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
import math

from tradingcat.adapters.base import MarketDataAdapter
from tradingcat.adapters.market import sample_instruments
from tradingcat.domain.models import Bar, CorporateAction, FxRate, Instrument
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository


logger = logging.getLogger(__name__)


class MarketDataService:
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

    def reset_cache(self) -> None:
        self._history.clear()
        self._instruments.clear()
        self._catalog = {}
        self.seed_catalog(sample_instruments())

    def list_instruments(self) -> list[Instrument]:
        return sorted(self._catalog.values(), key=lambda item: (item.market.value, item.symbol))

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

        complete = sum(1 for report in reports if float(report["coverage_ratio"]) >= 0.95)
        return {
            "start": start_date,
            "end": end_date,
            "instrument_count": len(targets),
            "expected_trading_days": len(expected_dates),
            "complete_instruments": complete,
            "reports": reports,
        }

    def repair_history_gaps(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        coverage = self.summarize_history_coverage(symbols=symbols, start=start, end=end)
        repair_targets = [report for report in coverage["reports"] if int(report["missing_count"]) > 0]
        if not repair_targets:
            return {
                "start": coverage["start"],
                "end": coverage["end"],
                "instrument_count": 0,
                "reports": [],
                "repaired_symbols": [],
                "repair_count": 0,
            }
        repaired_symbols = [str(report["symbol"]) for report in repair_targets]
        sync = self.sync_history(
            symbols=repaired_symbols,
            start=coverage["start"],
            end=coverage["end"],
            include_corporate_actions=include_corporate_actions,
        )
        return {
            **sync,
            "repaired_symbols": repaired_symbols,
            "repair_count": len(repaired_symbols),
        }

    def get_bars(self, symbol: str, start: date, end: date) -> list[Bar]:
        instrument = self._resolve_instrument(symbol)
        return self._history.load_bars(instrument, start, end)

    def get_corporate_actions(self, symbol: str, start: date, end: date) -> list[dict]:
        instrument = self._resolve_instrument(symbol)
        return self._history.load_corporate_actions(instrument, start, end)

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
        generated: list[FxRate] = []
        for quote_currency in currencies:
            generated.extend(self._generate_fx_series(base_currency.upper(), quote_currency, start_date, end_date))
        self._history.save_fx_rates(generated)
        return {
            "base_currency": base_currency.upper(),
            "quote_currencies": currencies,
            "rate_count": len(generated),
            "start": start_date,
            "end": end_date,
        }

    def get_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        return self._history.load_fx_rates(base_currency.upper(), quote_currency.upper(), start, end)

    def ensure_history(self, symbols: list[str], start: date, end: date) -> dict[str, list[Bar]]:
        targets = [self._resolve_instrument(symbol) for symbol in symbols if self._resolve_instrument(symbol, strict=False) is not None]
        loaded: dict[str, list[Bar]] = {}
        missing_symbols: list[str] = []

        for instrument in targets:
            bars = self._history.load_bars(instrument, start, end)
            if not bars:
                missing_symbols.append(instrument.symbol)
            else:
                loaded[instrument.symbol] = bars

        if missing_symbols:
            self.sync_history(symbols=missing_symbols, start=start, end=end, include_corporate_actions=True)
            for symbol in missing_symbols:
                instrument = self._resolve_instrument(symbol)
                bars = self._history.load_bars(instrument, start, end)
                if bars:
                    loaded[symbol] = bars

        return loaded

    def ensure_corporate_actions(self, symbols: list[str], start: date, end: date) -> dict[str, list[CorporateAction]]:
        targets = [self._resolve_instrument(symbol) for symbol in symbols if self._resolve_instrument(symbol, strict=False) is not None]
        loaded: dict[str, list[CorporateAction]] = {}

        for instrument in targets:
            actions = self._history.load_corporate_actions(instrument, start, end)
            if not actions:
                self.sync_history(symbols=[instrument.symbol], start=start, end=end, include_corporate_actions=True)
                actions = self._history.load_corporate_actions(instrument, start, end)
            loaded[instrument.symbol] = [
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
        return loaded

    def ensure_fx_rates(self, base_currency: str, quote_currencies: list[str], start: date, end: date) -> dict[str, list[FxRate]]:
        loaded: dict[str, list[FxRate]] = {}
        missing: list[str] = []
        for quote_currency in sorted({currency.upper() for currency in quote_currencies if currency.upper() != base_currency.upper()}):
            rates = self._history.load_fx_rates(base_currency.upper(), quote_currency, start, end)
            if not rates:
                missing.append(quote_currency)
            else:
                loaded[f"{quote_currency}/{base_currency.upper()}"] = rates
        if missing:
            self.sync_fx_rates(base_currency=base_currency.upper(), quote_currencies=missing, start=start, end=end)
            for quote_currency in missing:
                rates = self._history.load_fx_rates(base_currency.upper(), quote_currency, start, end)
                if rates:
                    loaded[f"{quote_currency}/{base_currency.upper()}"] = rates
        return loaded

    def _resolve_instrument(self, symbol: str, strict: bool = True) -> Instrument | None:
        matches = [instrument for instrument in self._catalog.values() if instrument.symbol == symbol]
        if not matches:
            if strict:
                raise KeyError(f"Unknown instrument symbol: {symbol}")
            return None
        return matches[0]

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

    def _expected_trading_dates(self, start: date, end: date) -> list[date]:
        days: list[date] = []
        current = start
        while current <= end:
            if current.weekday() < 5:
                days.append(current)
            current += timedelta(days=1)
        return days

    def _generate_fx_series(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
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

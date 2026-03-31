"""Yahoo Finance market data adapter using yfinance library."""

from __future__ import annotations

import logging
import math
from datetime import UTC, date, datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

from tradingcat.domain.models import AssetClass, Bar, Instrument, Market, OptionContract


# Symbol mapping: TradingCat symbol → Yahoo Finance ticker
_YAHOO_TICKER_MAP = {
    # HK stocks: append .HK
    ("HK", "0700"): "0700.HK",
    # CN A-shares: SH/SZ suffix
    ("CN", "300308"): "300308.SZ",
    ("CN", "603986"): "603986.SS",
    ("CN", "510300"): "510300.SS",
    # US symbols: use as-is
}


def _to_yahoo_ticker(instrument: Instrument) -> str:
    """Convert TradingCat instrument to Yahoo Finance ticker."""
    key = (instrument.market.value, instrument.symbol)
    if key in _YAHOO_TICKER_MAP:
        return _YAHOO_TICKER_MAP[key]
    if instrument.market == Market.HK:
        return f"{instrument.symbol}.HK"
    if instrument.market == Market.CN:
        # Default: assume Shanghai (.SS) for 6xxxxx, Shenzhen (.SZ) otherwise
        if instrument.symbol.startswith("6"):
            return f"{instrument.symbol}.SS"
        return f"{instrument.symbol}.SZ"
    return instrument.symbol


class YFinanceMarketDataAdapter:
    """Fetches real market data from Yahoo Finance."""

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        ticker = _to_yahoo_ticker(instrument)
        # yfinance end date is exclusive, add 1 day
        df = yf.download(
            ticker,
            start=start.isoformat(),
            end=(end + timedelta(days=1)).isoformat(),
            auto_adjust=True,
            progress=False,
        )
        if df.empty:
            return []

        # Handle multi-level columns from yfinance
        if hasattr(df.columns, "levels") and len(df.columns.levels) > 1:
            df = df.droplevel(level=1, axis=1)

        bars: list[Bar] = []
        for idx, row in df.iterrows():
            ts = idx.to_pydatetime() if hasattr(idx, "to_pydatetime") else idx
            if not isinstance(ts, datetime):
                ts = datetime.combine(ts, datetime.min.time(), tzinfo=UTC)
            elif ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=ts,
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row.get("Volume", 0)),
                )
            )
        return bars

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        quotes: dict[str, float] = {}
        for instrument in instruments:
            ticker = _to_yahoo_ticker(instrument)
            try:
                info = yf.Ticker(ticker).fast_info
                price = info["lastPrice"]
                if price is None or (isinstance(price, float) and math.isnan(price)):
                    logger.warning("YFinance returned NaN/None price for %s, using 0.0", ticker)
                    quotes[instrument.symbol] = 0.0
                else:
                    quotes[instrument.symbol] = float(price)
            except Exception:
                logger.warning("YFinance fetch_quotes failed for %s", ticker, exc_info=True)
                quotes[instrument.symbol] = 0.0
        return quotes

    def fetch_option_chain(self, underlying: str, as_of: date, *, market: Market | None = None) -> list[OptionContract]:
        ticker = underlying
        if market == Market.HK:
            ticker = f"{underlying}.HK"
        try:
            t = yf.Ticker(ticker)
            expiry_strings = t.options
            if not expiry_strings:
                logger.info("No option expiries found for %s", ticker)
                return []
            # Pick the nearest expiry at least 14 days out.
            target = as_of + timedelta(days=14)
            chosen_expiry: str | None = None
            for exp in expiry_strings:
                exp_date = date.fromisoformat(exp)
                if exp_date >= target:
                    chosen_expiry = exp
                    break
            if chosen_expiry is None:
                chosen_expiry = expiry_strings[-1]
            chain = t.option_chain(chosen_expiry)
            expiry_date = date.fromisoformat(chosen_expiry)
            mkt = market or Market.US
            contracts: list[OptionContract] = []
            for _, row in chain.calls.iterrows():
                contracts.append(OptionContract(
                    symbol=str(row.get("contractSymbol", f"{underlying}-C-{row['strike']}")),
                    underlying=underlying,
                    strike=float(row["strike"]),
                    expiry=expiry_date,
                    option_type="call",
                    market=mkt,
                ))
            for _, row in chain.puts.iterrows():
                contracts.append(OptionContract(
                    symbol=str(row.get("contractSymbol", f"{underlying}-P-{row['strike']}")),
                    underlying=underlying,
                    strike=float(row["strike"]),
                    expiry=expiry_date,
                    option_type="put",
                    market=mkt,
                ))
            logger.info("Fetched %d option contracts for %s expiry %s", len(contracts), ticker, chosen_expiry)
            return contracts
        except Exception:
            logger.warning("YFinance fetch_option_chain failed for %s", ticker, exc_info=True)
            return []

    def fetch_corporate_actions(self, instrument: Instrument, start: date, end: date) -> list[dict]:
        ticker = _to_yahoo_ticker(instrument)
        try:
            t = yf.Ticker(ticker)
            dividends = t.dividends
            if dividends.empty:
                return []
            actions = []
            for dt_idx, amount in dividends.items():
                action_date = dt_idx.date() if hasattr(dt_idx, "date") else dt_idx
                if start <= action_date <= end:
                    actions.append({
                        "effective_date": action_date.isoformat(),
                        "action_type": "dividend",
                        "cash_amount": float(amount),
                    })
            return actions
        except Exception:
            logger.warning("YFinance fetch_corporate_actions failed for %s", ticker, exc_info=True)
            return []

    def fetch_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list:
        return []

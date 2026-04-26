from __future__ import annotations

import logging
from datetime import date

from tradingcat.adapters.base import MarketDataAdapter
from tradingcat.adapters.cn.akshare import AkshareUnavailable
from tradingcat.domain.models import Bar, FxRate, Instrument, Market, OptionContract


logger = logging.getLogger(__name__)


class CompositeMarketDataAdapter:
    """Market-data router that sends CN instruments to AKShare with fallback."""

    def __init__(
        self,
        *,
        akshare_inner: MarketDataAdapter,
        us_hk_inner: MarketDataAdapter,
    ) -> None:
        self._akshare_inner = akshare_inner
        self._us_hk_inner = us_hk_inner

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        if instrument.market != Market.CN:
            return self._us_hk_inner.fetch_bars(instrument, start, end)

        try:
            bars = self._akshare_inner.fetch_bars(instrument, start, end)
        except AkshareUnavailable as exc:
            logger.info("AKShare unavailable for %s, falling back: %s", instrument.symbol, exc)
            return self._us_hk_inner.fetch_bars(instrument, start, end)
        except Exception as exc:
            logger.warning("AKShare fetch_bars failed for %s, falling back: %s", instrument.symbol, exc)
            return self._us_hk_inner.fetch_bars(instrument, start, end)

        if bars:
            return bars
        logger.info("AKShare returned no bars for %s, falling back", instrument.symbol)
        return self._us_hk_inner.fetch_bars(instrument, start, end)

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        cn_instruments = [instrument for instrument in instruments if instrument.market == Market.CN]
        other_instruments = [instrument for instrument in instruments if instrument.market != Market.CN]

        quotes: dict[str, float] = {}
        if other_instruments:
            quotes.update(self._us_hk_inner.fetch_quotes(other_instruments))
        if not cn_instruments:
            return quotes

        try:
            cn_quotes = self._akshare_inner.fetch_quotes(cn_instruments)
        except AkshareUnavailable as exc:
            logger.info("AKShare quotes unavailable, falling back: %s", exc)
            cn_quotes = {}
        except Exception as exc:
            logger.warning("AKShare fetch_quotes failed, falling back: %s", exc)
            cn_quotes = {}

        missing = [
            instrument
            for instrument in cn_instruments
            if instrument.symbol not in cn_quotes or cn_quotes[instrument.symbol] <= 0
        ]
        if not cn_quotes:
            quotes.update(self._us_hk_inner.fetch_quotes(cn_instruments))
            return quotes
        if missing:
            quotes.update(self._us_hk_inner.fetch_quotes(missing))
        quotes.update(cn_quotes)
        return quotes

    def fetch_option_chain(
        self,
        underlying: str,
        as_of: date,
        *,
        market: Market | None = None,
    ) -> list[OptionContract]:
        return self._us_hk_inner.fetch_option_chain(underlying, as_of, market=market)

    def fetch_corporate_actions(
        self,
        instrument: Instrument,
        start: date,
        end: date,
    ) -> list[dict]:
        return self._us_hk_inner.fetch_corporate_actions(instrument, start, end)

    def fetch_fx_rates(
        self,
        base_currency: str,
        quote_currency: str,
        start: date,
        end: date,
    ) -> list[FxRate]:
        return self._us_hk_inner.fetch_fx_rates(base_currency, quote_currency, start, end)

"""US market data via Polygon.io free tier.

Polygon free tier: 5 API calls/minute, delayed data, no WebSocket.
Provides ``/v2/aggs/ticker/*/prev`` (previous-day OHLCV) and
``/v2/snapshot/locale/us/markets/stocks/tickers`` (snapshot).

Registration at https://polygon.io/ — a free ``Stocks Starter`` API key
is sufficient.
"""
from __future__ import annotations

import logging
from typing import Any

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_POLYGON_BASE = "https://api.polygon.io"


class PolygonClient:
    """US stock snapshot and aggregate client.

    Uses the free-tier Polygon API. The ``api_key`` is required (register
    at polygon.io). Rate-limited to 5 calls/min — the client caches
    aggressively and batch-queries when possible.
    """

    def __init__(
        self,
        api_key: str,
        http: SentimentHttpClient | Any | None = None,
        *,
        timeout_seconds: float = 10.0,
        cache_ttl_seconds: int = 300,
    ) -> None:
        self.source = "polygon"
        self._api_key = api_key.strip()
        self._http = http or SentimentHttpClient(
            timeout_seconds=timeout_seconds,
            retries=1,
            default_ttl_seconds=cache_ttl_seconds,
            negative_ttl_seconds=120,
            rate_per_minute=5,
        )

    def fetch_quotes(self, tickers: list[str]) -> dict[str, float]:
        """Fetch last-trade price for each ticker via the prev-day agg.

        Returns a dict of ``{symbol: price}`` for tickers this client
        could resolve. Relies on ``/v2/aggs/ticker/*/prev`` per-ticker
        — free-tier callers should keep the ticker list short (1-3).
        """
        quotes: dict[str, float] = {}
        for ticker in tickers:
            price = self._fetch_prev_close(ticker)
            if price is not None:
                quotes[ticker] = price
        return quotes

    def _fetch_prev_close(self, ticker: str) -> float | None:
        params: dict[str, str] = {
            "adjusted": "true",
            "apiKey": self._api_key,
        }
        url = f"{_POLYGON_BASE}/v2/aggs/ticker/{ticker.upper()}/prev"
        payload = self._http.get_json(url, params=params)
        if payload is None:
            return None

        results = payload.get("results")
        if not isinstance(results, list) or not results:
            return None

        try:
            close_price = results[0].get("c")
            return float(close_price) if close_price is not None else None
        except (TypeError, ValueError, KeyError):
            logger.debug("Polygon prev-close parse failed for %s", ticker)
            return None

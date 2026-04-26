"""Crypto price data via CoinGecko public API.

Free tier: ~30 calls/minute without an API key, higher with a free
``demo`` key at https://www.coingecko.com/en/api.  No authentication
is required for basic price lookups.
"""
from __future__ import annotations

import logging
from typing import Any

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


_COINGECKO_BASE = "https://api.coingecko.com/api/v3"
_DEMO_BASE = "https://api.coingecko.com/api/v3"

# Common crypto symbols → CoinGecko IDs.
# Extend this list when the strategy needs additional coins.
_SYMBOL_TO_ID: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "BNB": "binancecoin",
    "SOL": "solana",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOGE": "dogecoin",
    "DOT": "polkadot",
    "AVAX": "avalanche-2",
    "MATIC": "matic-network",
    "LINK": "chainlink",
    "UNI": "uniswap",
    "ATOM": "cosmos",
    "LTC": "litecoin",
    "BCH": "bitcoin-cash",
    "TRX": "tron",
    "NEAR": "near",
    "OP": "optimism",
    "ARB": "arbitrum",
    "PEPE": "pepe",
    "SHIB": "shiba-inu",
}

_ID_TO_SYMBOL = {v: k for k, v in _SYMBOL_TO_ID.items()}


class CoinGeckoClient:
    """Cryptocurrency price client backed by the CoinGecko API.

    Handles both demo (free) and pro API tiers. The free tier without
    a key is heavily rate-limited; registering for a free demo key at
    coingecko.com raises the limit meaningfully.
    """

    def __init__(
        self,
        http: SentimentHttpClient | Any | None = None,
        *,
        api_key: str | None = None,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 120,
    ) -> None:
        self.source = "coingecko"
        self._http = http or SentimentHttpClient(
            timeout_seconds=timeout_seconds,
            retries=1,
            default_ttl_seconds=cache_ttl_seconds,
            negative_ttl_seconds=30,
            rate_per_minute=10,
        )
        self._api_key = (api_key or "").strip() or None
        self._base = _COINGECKO_BASE

    def fetch_quotes(self, symbols: list[str]) -> dict[str, float]:
        """Fetch current USD prices for the given crypto symbols.

        *symbols* may include ``-USD`` suffixes (e.g. ``BTC-USD``). Only
        symbols with a known CoinGecko ID mapping are queried.
        """
        ids: list[str] = []
        sym_map: dict[str, str] = {}
        for raw in symbols:
            sym = raw.upper().removesuffix("-USD").removesuffix("-USDT")
            coin_id = _SYMBOL_TO_ID.get(sym)
            if coin_id:
                ids.append(coin_id)
                sym_map[coin_id] = sym

        if not ids:
            return {}

        params: dict[str, Any] = {
            "ids": ",".join(ids),
            "vs_currencies": "usd",
        }
        if self._api_key:
            params["x_cg_demo_api_key"] = self._api_key

        payload = self._http.get_json(f"{self._base}/simple/price", params=params)
        if payload is None:
            return {}

        quotes: dict[str, float] = {}
        for coin_id, price_data in payload.items():
            if not isinstance(price_data, dict):
                continue
            usd_price = price_data.get("usd")
            if usd_price is not None:
                try:
                    sym = sym_map.get(coin_id, coin_id.upper())
                    quotes[sym] = float(usd_price)
                except (TypeError, ValueError):
                    continue
        return quotes

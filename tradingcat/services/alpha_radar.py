from __future__ import annotations

import logging
import random
from datetime import datetime, timedelta, timezone

from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, Instrument, Market
from tradingcat.services.market_data import MarketDataService


logger = logging.getLogger(__name__)


class AlphaRadarService:
    def __init__(self, config: AppConfig, market_data: MarketDataService) -> None:
        self._config = config
        self._market_data = market_data
        self._symbols = list(config.alpha_radar_symbols)

    def fetch_simulated_flow(self, count: int = 15) -> list[dict[str, object]]:
        try:
            prices = self._market_data.fetch_quotes(self._quote_instruments())
        except Exception:
            logger.exception("AlphaRadar quote fetch failed; using synthetic fallback prices")
            prices = {symbol: 100.0 + random.uniform(-5, 5) for symbol in self._symbols}
        return self._build_flows(prices, count)

    async def fetch_simulated_flow_async(self, count: int = 15) -> list[dict[str, object]]:
        prices = await self._market_data.fetch_quotes_async(self._quote_instruments())
        if not prices:
            logger.warning("AlphaRadar received no live prices; using synthetic fallback prices")
            prices = {symbol: 100.0 + random.uniform(-5, 5) for symbol in self._symbols}
        return self._build_flows(prices, count)

    def _quote_instruments(self) -> list[Instrument]:
        return [Instrument(symbol=symbol, market=Market.US, asset_class=AssetClass.STOCK) for symbol in self._symbols]

    def _build_flows(self, prices: dict[str, float], count: int) -> list[dict[str, object]]:
        flows: list[dict[str, object]] = []
        now = datetime.now(timezone.utc)

        for _ in range(count):
            symbol = random.choice(self._symbols)
            price = prices.get(symbol, 100.0)
            is_option = random.random() > 0.4

            if is_option:
                flow_type = random.choice(["SWEEP", "SPLIT"])
                sentiment = random.choice(["BULLISH", "BEARISH"])
                premium = random.uniform(250_000, 5_000_000)
                expiration = now + timedelta(days=random.choice([0, 1, 7, 30, 90]))
                strike_offset = random.uniform(-0.1, 0.1) * price
                strike = round(price + strike_offset, 1)
                option_type = "CALL" if sentiment == "BULLISH" else "PUT"
                status = "OTM" if ((sentiment == "BULLISH" and strike > price) or (sentiment == "BEARISH" and strike <= price)) else "ITM"
                flows.append(
                    {
                        "timestamp": (now - timedelta(minutes=random.randint(0, 120))).isoformat(),
                        "symbol": symbol,
                        "type": flow_type,
                        "option_type": option_type,
                        "sentiment": sentiment,
                        "strike": strike,
                        "expiration": expiration.strftime("%Y-%m-%d"),
                        "premium": round(premium, 2),
                        "spot_price": price,
                        "status": status,
                    }
                )
                continue

            premium = random.uniform(1_000_000, 20_000_000)
            flows.append(
                {
                    "timestamp": (now - timedelta(minutes=random.randint(0, 120))).isoformat(),
                    "symbol": symbol,
                    "type": "BLOCK",
                    "option_type": "EQUITY",
                    "sentiment": "NEUTRAL",
                    "strike": None,
                    "expiration": None,
                    "premium": round(premium, 2),
                    "spot_price": price,
                    "status": "DARK_POOL",
                    "volume": int(premium / price) if price > 0 else 0,
                }
            )

        flows.sort(key=lambda item: item["timestamp"], reverse=True)
        return flows

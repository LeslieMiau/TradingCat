from __future__ import annotations

import random
from datetime import datetime, time, timedelta, timezone

from tradingcat.config import AppConfig
from tradingcat.services.market_data import MarketDataService

class AlphaRadarService:
    def __init__(self, config: AppConfig, market_data: MarketDataService) -> None:
        self._config = config
        self._market_data = market_data
        self._symbols = ["SPY", "QQQ", "NVDA", "TSLA", "AAPL", "MSFT", "AMD"]
        
    def fetch_simulated_flow(self, count: int = 15) -> list[dict[str, object]]:
        """
        Generates simulated institutional block trades and options sweeps (Smart Money Flow).
        In a real institutional environment, this would hook into a WebSocket feed from CheddarFlow or UnusualWhales.
        """
        try:
            prices = self._market_data.fetch_quotes(self._symbols)
        except Exception:
            prices = {s: 100.0 + random.uniform(-5, 5) for s in self._symbols}
            
        flows = []
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
                
                # Determine OTM/ITM
                if sentiment == "BULLISH":
                    option_type = "CALL"
                    status = "OTM" if strike > price else "ITM"
                else:
                    option_type = "PUT"
                    status = "ITM" if strike > price else "OTM"
                    
                flows.append({
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
                })
            else:
                # Dark Pool Equity Block
                flow_type = "BLOCK"
                premium = random.uniform(1_000_000, 20_000_000)
                volume = int(premium / price)
                sentiment = "NEUTRAL"
                
                flows.append({
                    "timestamp": (now - timedelta(minutes=random.randint(0, 120))).isoformat(),
                    "symbol": symbol,
                    "type": flow_type,
                    "option_type": "EQUITY",
                    "sentiment": sentiment,
                    "strike": None,
                    "expiration": None,
                    "premium": round(premium, 2),
                    "spot_price": price,
                    "status": "DARK_POOL",
                    "volume": volume,
                })
                
        # Sort by most recent
        flows.sort(key=lambda x: x["timestamp"], reverse=True)
        return flows

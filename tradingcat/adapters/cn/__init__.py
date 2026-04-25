"""China A-share market data adapters.

Currently exposes:
- ``AkshareMarketDataAdapter``: pulls A-share K-line / quote data from
  AKShare. Optional dependency — guarded behind ``AkshareConfig.enabled``.

Planned (later rounds): BaoStock (free, no token), Tushare (premium fields).
"""

from tradingcat.adapters.cn.akshare import (
    AKSHARE_AVAILABLE,
    AkshareMarketDataAdapter,
    AkshareUnavailable,
)

__all__ = [
    "AKSHARE_AVAILABLE",
    "AkshareMarketDataAdapter",
    "AkshareUnavailable",
]

"""China A-share market data adapters.

Currently exposes:
- ``AkshareMarketDataAdapter``: pulls A-share K-line / quote data from
  AKShare. Optional dependency — guarded behind ``AkshareConfig.enabled``.
- ``BaostockMarketDataAdapter``: pulls free A-share daily bars from BaoStock.
  Optional dependency — guarded behind ``BaostockConfig.enabled``.

Planned (later rounds): Tushare (premium fields).
"""

from tradingcat.adapters.cn.akshare import (
    AKSHARE_AVAILABLE,
    AkshareMarketDataAdapter,
    AkshareUnavailable,
)
from tradingcat.adapters.cn.baostock import (
    BAOSTOCK_AVAILABLE,
    BaostockMarketDataAdapter,
    BaostockUnavailable,
)

__all__ = [
    "AKSHARE_AVAILABLE",
    "BAOSTOCK_AVAILABLE",
    "AkshareMarketDataAdapter",
    "AkshareUnavailable",
    "BaostockMarketDataAdapter",
    "BaostockUnavailable",
]

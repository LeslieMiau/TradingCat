"""China A-share market data adapters.

Currently exposes:
- ``AkshareMarketDataAdapter``: pulls A-share K-line / quote data from
  AKShare. Optional dependency — guarded behind ``AkshareConfig.enabled``.
- ``BaostockMarketDataAdapter``: pulls free A-share daily bars from BaoStock.
  Optional dependency — guarded behind ``BaostockConfig.enabled``.
- ``TushareMarketDataAdapter``: pulls token-gated A-share daily bars and
  research datasets from Tushare Pro. Optional dependency — guarded behind
  ``TushareConfig.enabled``.

Planned (later rounds): factory fallback ordering across these CN sources.
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
from tradingcat.adapters.cn.tushare import (
    TUSHARE_AVAILABLE,
    TushareMarketDataAdapter,
    TushareUnavailable,
)

__all__ = [
    "AKSHARE_AVAILABLE",
    "BAOSTOCK_AVAILABLE",
    "TUSHARE_AVAILABLE",
    "AkshareMarketDataAdapter",
    "AkshareUnavailable",
    "BaostockMarketDataAdapter",
    "BaostockUnavailable",
    "TushareMarketDataAdapter",
    "TushareUnavailable",
]

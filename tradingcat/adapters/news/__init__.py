"""News-source adapters for research and market awareness.

Adapters in this package are advisory/research inputs only. They do not create
signals, orders, approvals, or trading decisions.
"""

from tradingcat.adapters.news.alpha_vantage import AlphaVantageNewsClient
from tradingcat.adapters.news.cls import CLSNewsClient
from tradingcat.adapters.news.eastmoney import EastMoneyNewsClient, EastMoneyNewsUnavailable, NewsItem
from tradingcat.adapters.news.finnhub import FinnhubNewsClient
from tradingcat.adapters.news.hkrss import HkRssNewsClient
from tradingcat.adapters.news.providers import (
    AlphaVantageNewsProvider,
    CLSNewsProvider,
    EastMoneyNewsProvider,
    FinnhubNewsProvider,
    TushareNewsProvider,
)
from tradingcat.adapters.news.tushare_news import TushareNewsClient, TushareNewsUnavailable

__all__ = [
    "AlphaVantageNewsClient",
    "AlphaVantageNewsProvider",
    "CLSNewsClient",
    "CLSNewsProvider",
    "EastMoneyNewsClient",
    "EastMoneyNewsProvider",
    "EastMoneyNewsUnavailable",
    "FinnhubNewsClient",
    "FinnhubNewsProvider",
    "HkRssNewsClient",
    "NewsItem",
    "TushareNewsClient",
    "TushareNewsProvider",
    "TushareNewsUnavailable",
]

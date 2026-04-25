"""News-source adapters for research and market awareness.

Adapters in this package are advisory/research inputs only. They do not create
signals, orders, approvals, or trading decisions.
"""

from tradingcat.adapters.news.eastmoney import EastMoneyNewsClient, EastMoneyNewsUnavailable, NewsItem
from tradingcat.adapters.news.cls import CLSNewsClient
from tradingcat.adapters.news.finnhub import FinnhubNewsClient
from tradingcat.adapters.news.alpha_vantage import AlphaVantageNewsClient

__all__ = [
    "AlphaVantageNewsClient",
    "CLSNewsClient",
    "EastMoneyNewsClient",
    "EastMoneyNewsUnavailable",
    "FinnhubNewsClient",
    "NewsItem",
]

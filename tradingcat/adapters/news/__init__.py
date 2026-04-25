"""News-source adapters for research and market awareness.

Adapters in this package are advisory/research inputs only. They do not create
signals, orders, approvals, or trading decisions.
"""

from tradingcat.adapters.news.eastmoney import EastMoneyNewsClient, EastMoneyNewsUnavailable, NewsItem

__all__ = [
    "EastMoneyNewsClient",
    "EastMoneyNewsUnavailable",
    "NewsItem",
]

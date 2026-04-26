from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.adapters.news.alpha_vantage import AlphaVantageNewsClient
from tradingcat.adapters.news.cls import CLSNewsClient
from tradingcat.adapters.news.finnhub import FinnhubNewsClient
from tradingcat.config import AlphaVantageNewsConfig, CLSNewsConfig, FinnhubNewsConfig


class _FakeHttp:
    def __init__(self, payloads=None, *, error: Exception | None = None) -> None:
        self.payloads = list(payloads or [])
        self.error = error
        self.calls: list[dict] = []

    def get_json(self, url, *, params=None, headers=None, ttl_seconds=None):
        self.calls.append({"url": url, "params": params, "headers": headers, "ttl_seconds": ttl_seconds})
        if self.error is not None:
            raise self.error
        return self.payloads.pop(0) if self.payloads else None


def test_cls_news_parses_roll_data_and_observation_items():
    http = _FakeHttp(
        [
            {
                "data": {
                    "roll_data": [
                        {
                            "title": "财联社：半导体板块午后拉升",
                            "shareurl": "https://www.cls.cn/detail/1",
                            "ctime": 1704160800,
                            "stock": [{"code": "300308"}],
                        }
                    ]
                }
            }
        ]
    )
    client = CLSNewsClient(http=http, page_size=10, ttl_seconds=120, user_agent="UA")

    items = client.fetch_items(limit=1)

    assert items[0]["source"] == "cls"
    assert items[0]["title"] == "财联社：半导体板块午后拉升"
    assert items[0]["published_at"] == datetime(2024, 1, 2, 2, 0, tzinfo=UTC)
    assert items[0]["symbols"] == ["300308"]
    assert http.calls[0]["params"]["limit"] == "1"
    assert http.calls[0]["headers"] == {"User-Agent": "UA"}
    assert http.calls[0]["ttl_seconds"] == 120


def test_cls_news_returns_empty_on_error_or_bad_shape():
    assert CLSNewsClient(http=_FakeHttp([{"data": {"roll_data": [{"url": "missing title"}]}}])).fetch_items() == []
    assert CLSNewsClient(http=_FakeHttp(error=RuntimeError("down"))).fetch_items() == []


def test_finnhub_news_requires_token_and_symbols_then_parses_company_news():
    assert FinnhubNewsClient(http=_FakeHttp(), token="", symbols=["AAPL"]).fetch_items() == []
    assert FinnhubNewsClient(http=_FakeHttp(), token="token", symbols=[]).fetch_items() == []

    http = _FakeHttp(
        [
            {
                "data": [
                    {
                        "headline": "Apple supplier news",
                        "url": "https://example.com/aapl",
                        "summary": "supply chain",
                        "datetime": 1704160800,
                        "source": "Reuters",
                    }
                ]
            }
        ]
    )
    client = FinnhubNewsClient(http=http, token="token", symbols=["AAPL"], lookback_days=3, page_size=5)

    items = client.fetch_items(limit=2)

    assert items[0]["source"] == "finnhub"
    assert items[0]["symbols"] == ["AAPL"]
    assert http.calls[0]["params"]["symbol"] == "AAPL"
    assert http.calls[0]["params"]["token"] == "token"


def test_alpha_vantage_news_requires_key_and_parses_sentiment_feed():
    assert AlphaVantageNewsClient(http=_FakeHttp(), api_key="", tickers=["MSFT"]).fetch_items() == []
    assert AlphaVantageNewsClient(http=_FakeHttp(), api_key="key", tickers=[]).fetch_items() == []

    http = _FakeHttp(
        [
            {
                "feed": [
                    {
                        "title": "Microsoft AI demand rises",
                        "url": "https://example.com/msft",
                        "summary": "AI demand",
                        "time_published": "20240102T093000",
                        "source": "AV",
                        "ticker_sentiment": [{"ticker": "MSFT"}, {"ticker": "NVDA"}],
                    }
                ]
            }
        ]
    )
    client = AlphaVantageNewsClient(http=http, api_key="key", tickers=["MSFT", "NVDA"], page_size=5, ttl_seconds=240)

    items = client.fetch_items(limit=1)

    assert items[0]["source"] == "alpha_vantage"
    assert items[0]["symbols"] == ["MSFT", "NVDA"]
    assert items[0]["published_at"] == datetime(2024, 1, 2, 9, 30, tzinfo=UTC)
    assert http.calls[0]["params"]["function"] == "NEWS_SENTIMENT"
    assert http.calls[0]["params"]["tickers"] == "MSFT,NVDA"
    assert http.calls[0]["params"]["apikey"] == "key"
    assert http.calls[0]["ttl_seconds"] == 240


def test_news_source_config_from_env():
    cls_cfg = CLSNewsConfig.from_env(
        {
            "TRADINGCAT_CLS_NEWS_ENABLED": "true",
            "TRADINGCAT_CLS_NEWS_PAGE_SIZE": "7",
            "TRADINGCAT_CLS_NEWS_CACHE_TTL_SECONDS": "60",
        }
    )
    assert cls_cfg.enabled is True
    assert cls_cfg.page_size == 7
    assert cls_cfg.cache_ttl_seconds == 60

    finnhub_cfg = FinnhubNewsConfig.from_env(
        {
            "TRADINGCAT_FINNHUB_NEWS_ENABLED": "true",
            "TRADINGCAT_FINNHUB_TOKEN": "fh",
            "TRADINGCAT_FINNHUB_NEWS_SYMBOLS": "AAPL, msft",
        }
    )
    assert finnhub_cfg.enabled is True
    assert finnhub_cfg.token == "fh"
    assert finnhub_cfg.symbols == ["AAPL", "MSFT"]

    av_cfg = AlphaVantageNewsConfig.from_env(
        {
            "TRADINGCAT_ALPHA_VANTAGE_NEWS_ENABLED": "true",
            "TRADINGCAT_ALPHA_VANTAGE_API_KEY": "av",
            "TRADINGCAT_ALPHA_VANTAGE_NEWS_TICKERS": "SPY,qqq",
        }
    )
    assert av_cfg.enabled is True
    assert av_cfg.api_key == "av"
    assert av_cfg.tickers == ["SPY", "QQQ"]

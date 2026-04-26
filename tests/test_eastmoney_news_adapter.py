"""Unit tests for the East Money news adapter (Round 05)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tradingcat.adapters.news.eastmoney import EastMoneyNewsClient
from tradingcat.config import EastMoneyNewsConfig


class _FakeHttp:
    def __init__(self, payload=None, *, error: Exception | None = None) -> None:
        self.payload = payload
        self.error = error
        self.calls: list[dict] = []

    def get_json(self, url, *, params=None, headers=None, ttl_seconds=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "headers": headers,
                "ttl_seconds": ttl_seconds,
            }
        )
        if self.error is not None:
            raise self.error
        return self.payload


def test_fetch_news_parses_common_eastmoney_shape():
    http = _FakeHttp(
        {
            "data": {
                "list": [
                    {
                        "title": "A股 三大指数 集体反弹",
                        "url": "https://finance.eastmoney.com/a/2024010201.html",
                        "showTime": "2024-01-02 09:30:00",
                        "summary": "市场情绪回暖",
                        "symbols": "600000, 159915",
                    },
                    {
                        "newsTitle": "政策利好推动科技板块",
                        "infoCode": "2024010202",
                        "publishTime": "2024-01-02T02:00:00+00:00",
                        "digest": "科技股走强",
                        "stock_list": [{"code": "300308"}],
                    },
                ]
            }
        }
    )
    client = EastMoneyNewsClient(http=http, column="351", page_size=20, ttl_seconds=300, user_agent="UA")

    items = client.fetch_news(limit=2)

    assert len(items) == 2
    assert items[0].source == "eastmoney"
    assert items[0].title == "A股 三大指数 集体反弹"
    assert items[0].published_at == datetime(2024, 1, 2, 1, 30, tzinfo=UTC)
    assert items[0].symbols == ["600000", "159915"]
    assert items[1].url == "https://finance.eastmoney.com/a/2024010202.html"
    assert items[1].symbols == ["300308"]
    assert http.calls[0]["params"]["column"] == "351"
    assert http.calls[0]["params"]["page_size"] == "2"
    assert http.calls[0]["headers"] == {"User-Agent": "UA"}
    assert http.calls[0]["ttl_seconds"] == 300


def test_fetch_items_returns_news_observation_shape():
    http = _FakeHttp(
        {
            "data": [
                {
                    "Art_Title": "人民币 汇率 稳定",
                    "Art_Url": "https://finance.eastmoney.com/a/1.html",
                    "Art_ShowTime": "2024/01/02 10:00:00",
                    "Art_Description": "宏观消息",
                }
            ]
        }
    )
    client = EastMoneyNewsClient(http=http)

    items = client.fetch_items(limit=1)

    assert items == [
        {
            "source": "eastmoney",
            "title": "人民币 汇率 稳定",
            "url": "https://finance.eastmoney.com/a/1.html",
            "published_at": datetime(2024, 1, 2, 2, 0, tzinfo=UTC),
            "summary": "宏观消息",
            "symbols": [],
        }
    ]


def test_fetch_news_returns_empty_on_http_none_error_or_bad_shape():
    assert EastMoneyNewsClient(http=_FakeHttp(None)).fetch_news() == []
    assert EastMoneyNewsClient(http=_FakeHttp({"data": {"list": [{"url": "missing title"}]}})).fetch_news() == []
    assert EastMoneyNewsClient(http=_FakeHttp(error=RuntimeError("network down"))).fetch_news() == []


def test_fetch_news_supports_result_data_shape_and_limit():
    http = _FakeHttp(
        {
            "result": {
                "data": {
                    "items": [
                        {"TITLE": "第一条", "URL": "https://example.com/1", "DATE": "20240102"},
                        {"TITLE": "第二条", "URL": "https://example.com/2", "DATE": "20240103"},
                    ]
                }
            }
        }
    )
    client = EastMoneyNewsClient(http=http, page_size=10)

    items = client.fetch_news(limit=1)

    assert [item.title for item in items] == ["第一条"]
    assert http.calls[0]["params"]["page_size"] == "1"


def test_config_defaults_disabled():
    cfg = EastMoneyNewsConfig()
    assert cfg.enabled is False
    assert cfg.column == "351"
    assert cfg.page_size == 20
    assert cfg.cache_ttl_seconds == 600


def test_config_from_env_parses_flags():
    cfg = EastMoneyNewsConfig.from_env(
        {
            "TRADINGCAT_EASTMONEY_NEWS_ENABLED": "true",
            "TRADINGCAT_EASTMONEY_NEWS_COLUMN": "350",
            "TRADINGCAT_EASTMONEY_NEWS_PAGE_SIZE": "8",
            "TRADINGCAT_EASTMONEY_NEWS_CACHE_TTL_SECONDS": "120",
            "TRADINGCAT_EASTMONEY_NEWS_TIMEOUT_SECONDS": "2.5",
            "TRADINGCAT_EASTMONEY_NEWS_USER_AGENT": "Custom UA",
        }
    )
    assert cfg.enabled is True
    assert cfg.column == "350"
    assert cfg.page_size == 8
    assert cfg.cache_ttl_seconds == 120
    assert cfg.timeout_seconds == 2.5
    assert cfg.user_agent == "Custom UA"


def test_config_rejects_invalid_numbers():
    with pytest.raises(ValueError):
        EastMoneyNewsConfig(page_size=0)
    with pytest.raises(ValueError):
        EastMoneyNewsConfig(cache_ttl_seconds=0)
    with pytest.raises(ValueError):
        EastMoneyNewsConfig(timeout_seconds=0)

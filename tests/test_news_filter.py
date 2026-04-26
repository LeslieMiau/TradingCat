from __future__ import annotations

from datetime import UTC, datetime, timedelta

from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency
from tradingcat.services.news_filter import NewsFilterService


def test_news_filter_dedupes_urls_strips_tracking_and_ranks_relevance():
    now = datetime(2024, 1, 2, 12, tzinfo=UTC)
    service = NewsFilterService()
    items = [
        {
            "source": "eastmoney",
            "title": "重大 政策 刺激 A股 600000 银行板块",
            "url": "HTTPS://Example.com/a?utm_source=x&id=1",
            "published_at": now - timedelta(minutes=20),
            "symbols": ["600000"],
        },
        {
            "source": "google_news_macro",
            "title": "重大 政策 刺激 A股 600000 银行板块",
            "url": "https://example.com/a?id=1&utm_campaign=y",
            "published_at": now - timedelta(hours=4),
            "symbols": ["600000"],
        },
        {
            "source": "finnhub",
            "title": "Microsoft earnings announce AI revenue growth",
            "url": "https://example.com/msft",
            "published_at": now - timedelta(hours=1),
            "symbols": ["MSFT"],
        },
    ]

    filtered = service.filter_items(items, target_symbols={"600000"}, now=now)

    assert len(filtered) == 2
    assert filtered[0].symbols == ["600000"]
    assert filtered[0].url == "https://example.com/a?id=1"
    assert filtered[0].urgency == NewsUrgency.HIGH
    assert filtered[0].event_class == NewsEventClass.POLICY
    assert filtered[0].relevance == 1.0
    assert filtered[0].quality_score > filtered[1].quality_score


def test_news_filter_filters_short_denied_and_invalid_items():
    service = NewsFilterService(deny_sources={"spam"}, min_title_chars=10)
    filtered = service.filter_items(
        [
            {"source": "spam", "title": "重大政策刺激市场", "url": "https://example.com/spam"},
            {"source": "eastmoney", "title": "太短", "url": "https://example.com/short"},
            {"source": "", "title": "missing source"},
            {"source": "cls", "title": "财联社 行业 板块 出现明显放量", "url": ""},
        ],
        now=datetime(2024, 1, 2, tzinfo=UTC),
    )

    assert len(filtered) == 1
    assert filtered[0].source == "cls"
    assert filtered[0].event_class == NewsEventClass.INDUSTRY


def test_news_filter_accepts_news_item_instances_and_limit():
    now = datetime(2024, 1, 2, 12, tzinfo=UTC)
    service = NewsFilterService(allow_sources={"cls", "eastmoney"})
    filtered = service.filter_items(
        [
            NewsItem(
                source="cls",
                title="突发 停牌 公司 300308 发布重大事项",
                url="https://example.com/1",
                published_at=now - timedelta(minutes=5),
                symbols=["300308"],
            ),
            NewsItem(
                source="finnhub",
                title="US market macro update",
                url="https://example.com/2",
                published_at=now,
            ),
        ],
        target_symbols={"300308"},
        now=now,
        limit=1,
    )

    assert len(filtered) == 1
    assert filtered[0].urgency == NewsUrgency.HIGH
    assert filtered[0].event_class == NewsEventClass.CRISIS

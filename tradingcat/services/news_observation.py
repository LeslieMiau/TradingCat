from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
import logging
from math import isfinite
from time import monotonic
from typing import Protocol

from tradingcat.adapters.news import (
    AlphaVantageNewsClient,
    CLSNewsClient,
    EastMoneyNewsClient,
    FinnhubNewsClient,
    TushareNewsClient,
)
from tradingcat.adapters.news.providers import (
    AlphaVantageNewsProvider,
    CLSNewsProvider,
    EastMoneyNewsProvider,
    FinnhubNewsProvider,
    TushareNewsProvider,
)
from tradingcat.config import AppConfig
from tradingcat.domain.models import (
    MarketAwarenessNewsItem,
    MarketAwarenessNewsObservation,
    MarketAwarenessSignalStatus,
)


logger = logging.getLogger(__name__)


class NewsFeedProvider(Protocol):
    source: str

    def fetch_items(self, *, limit: int = 12) -> list[dict[str, object]]: ...


class NewsObservationService:
    _EXCLUDED_SYMBOLS = {"A", "AN", "AND", "THE", "FOR", "ETF", "USD", "CNY", "HKD", "CPI", "PMI"}

    def __init__(self, config: AppConfig, providers: list[NewsFeedProvider] | None = None) -> None:
        self._config = config.market_awareness
        self._providers = providers or self._default_providers(config)
        self._cache_expires_at = 0.0
        self._cached_observation = MarketAwarenessNewsObservation(
            degraded=True,
            blockers=["News observation has not been fetched yet."],
            explanation="News observation cache has not been primed yet.",
            tone=MarketAwarenessSignalStatus.BLOCKED,
        )

    @staticmethod
    def _default_providers(config: AppConfig) -> list[NewsFeedProvider]:
        providers: list[NewsFeedProvider] = []

        # CLS (free, highest quality)
        cls_cfg = config.cls_news
        if cls_cfg.enabled:
            providers.append(
                CLSNewsProvider(
                    CLSNewsClient(
                        page_size=cls_cfg.page_size,
                        ttl_seconds=cls_cfg.cache_ttl_seconds,
                        user_agent=cls_cfg.user_agent,
                    ),
                )
            )

        # EastMoney (free)
        em_cfg = config.eastmoney_news
        if em_cfg.enabled:
            providers.append(
                EastMoneyNewsProvider(
                    EastMoneyNewsClient(
                        column=em_cfg.column,
                        page_size=em_cfg.page_size,
                        ttl_seconds=em_cfg.cache_ttl_seconds,
                        user_agent=em_cfg.user_agent,
                    ),
                )
            )

        # Finnhub (requires token)
        fn_cfg = config.finnhub_news
        if fn_cfg.enabled and fn_cfg.token:
            providers.append(
                FinnhubNewsProvider(
                    FinnhubNewsClient(
                        token=fn_cfg.token,
                        symbols=fn_cfg.symbols,
                        lookback_days=fn_cfg.lookback_days,
                        page_size=fn_cfg.page_size,
                        ttl_seconds=fn_cfg.cache_ttl_seconds,
                    ),
                )
            )

        # Alpha Vantage (requires api_key)
        av_cfg = config.alpha_vantage_news
        if av_cfg.enabled and av_cfg.api_key:
            providers.append(
                AlphaVantageNewsProvider(
                    AlphaVantageNewsClient(
                        api_key=av_cfg.api_key,
                        tickers=av_cfg.tickers,
                        page_size=av_cfg.page_size,
                        cache_ttl_seconds=av_cfg.cache_ttl_seconds,
                    ),
                )
            )

        # TuShare news (requires token)
        ts_cfg = config.tushare_news  # type: ignore[union-attr]
        if getattr(config, "tushare_news", None) and ts_cfg.enabled and ts_cfg.token:
            providers.append(
                TushareNewsProvider(
                    TushareNewsClient(
                        token=ts_cfg.token,
                        page_size=min(ts_cfg.page_size, 40),
                        ttl_seconds=ts_cfg.cache_ttl_seconds,
                    ),
                )
            )

        return providers

    def observe(self, as_of: datetime | None = None) -> MarketAwarenessNewsObservation:
        _ = as_of
        now = monotonic()
        if now < self._cache_expires_at:
            return self._cached_observation

        blockers: list[str] = []
        raw_items: list[dict[str, object]] = []
        for provider in self._providers:
            try:
                raw_items.extend(provider.fetch_items())
            except Exception as exc:
                logger.warning("News provider fetch failed for %s", provider.source, exc_info=True)
                blockers.append(f"{provider.source}: {exc}")

        normalized = self._dedupe_items([self._normalize_item(item) for item in raw_items if item.get("title")])
        key_items = sorted(normalized, key=lambda item: item.importance, reverse=True)[:6]
        dominant_topics = [topic for topic, _ in Counter(item.topic for item in normalized).most_common(3)]
        score = round(sum(self._tone_score(item.tone) * item.importance for item in key_items), 4)
        if key_items:
            score = round(score / max(sum(item.importance for item in key_items), 1.0), 4)
        tone = self._aggregate_tone(score, bool(key_items), bool(blockers))
        degraded = bool(blockers)
        explanation = self._explanation(tone, dominant_topics, degraded, len(key_items))
        observation = MarketAwarenessNewsObservation(
            score=score,
            tone=tone,
            dominant_topics=dominant_topics,
            key_items=key_items,
            degraded=degraded,
            blockers=blockers,
            explanation=explanation,
        )
        self._cached_observation = observation
        self._cache_expires_at = now + self._config.news_cache_ttl_seconds
        return observation

    def _normalize_item(self, raw_item: dict[str, object]) -> MarketAwarenessNewsItem:
        title = str(raw_item.get("title") or "").strip()
        normalized_title = title.replace(" - Google News", "").strip()
        text = normalized_title.lower()
        topic = self._topic(text)
        tone = self._tone(text)
        importance = self._importance(raw_item.get("published_at"), topic, tone)
        return MarketAwarenessNewsItem(
            source=str(raw_item.get("source") or "unknown"),
            title=normalized_title,
            topic=topic,
            tone=tone,
            importance=importance,
            published_at=raw_item.get("published_at") if isinstance(raw_item.get("published_at"), datetime) else None,
            url=str(raw_item.get("url") or "") or None,
            markets=self._markets(text),
            symbols=self._symbols(normalized_title),
        )

    def _dedupe_items(self, items: list[MarketAwarenessNewsItem]) -> list[MarketAwarenessNewsItem]:
        deduped: dict[str, MarketAwarenessNewsItem] = {}
        for item in items:
            key = f"{item.title.casefold()}|{item.url or ''}"
            existing = deduped.get(key)
            if existing is None or item.importance > existing.importance:
                deduped[key] = item
        return list(deduped.values())

    @staticmethod
    def _topic(text: str) -> str:
        topic_keywords = {
            "macro": {"fed", "inflation", "rates", "cpi", "jobs", "pmi", "宏观", "通胀", "经济"},
            "policy": {"policy", "regulation", "tariff", "stimulus", "政策", "监管", "关税", "刺激"},
            "liquidity": {"liquidity", "flow", "volume", "spread", "资金", "流动性", "成交"},
            "risk": {"risk", "selloff", "default", "fraud", "downgrade", "风险", "暴跌", "违约"},
            "technology": {"chip", "software", "cloud", "ai", "半导体", "科技", "人工智能"},
        }
        for topic, keywords in topic_keywords.items():
            if any(keyword in text for keyword in keywords):
                return topic
        return "macro"

    @staticmethod
    def _tone(text: str) -> MarketAwarenessSignalStatus:
        supportive = {"support", "stimulus", "cut", "breakout", "rebound", "新高", "反弹", "回升", "修复", "放量上攻"}
        warning = {"selloff", "tightening", "downgrade", "default", "fraud", "volatility", "risk", "下挫", "暴跌", "收紧", "风险"}
        if any(keyword in text for keyword in warning):
            return MarketAwarenessSignalStatus.WARNING
        if any(keyword in text for keyword in supportive):
            return MarketAwarenessSignalStatus.SUPPORTIVE
        return MarketAwarenessSignalStatus.MIXED

    def _importance(self, published_at: object, topic: str, tone: MarketAwarenessSignalStatus) -> float:
        importance = 0.35
        if topic in {"macro", "policy", "risk"}:
            importance += 0.2
        if tone == MarketAwarenessSignalStatus.WARNING:
            importance += 0.15
        if tone == MarketAwarenessSignalStatus.SUPPORTIVE:
            importance += 0.05
        if isinstance(published_at, datetime):
            age_hours = max((datetime.now(UTC) - published_at.astimezone(UTC)).total_seconds() / 3600, 0.0)
            if isfinite(age_hours):
                importance += 0.2 if age_hours <= 6 else 0.1 if age_hours <= 24 else 0.0
        return round(min(max(importance, 0.1), 1.0), 4)

    @staticmethod
    def _markets(text: str) -> list[str]:
        markets = []
        if any(keyword in text for keyword in {"a股", "上证", "深证", "创业板", "china", "csi 300"}):
            markets.append("CN")
        if any(keyword in text for keyword in {"hong kong", "hang seng", "hk"}):
            markets.append("HK")
        if any(keyword in text for keyword in {"nasdaq", "s&p", "dow", "wall street", "us market", "u.s."}):
            markets.append("US")
        return markets or ["CN"]

    def _symbols(self, title: str) -> list[str]:
        symbols: list[str] = []
        for token in title.replace("/", " ").replace(",", " ").split():
            cleaned = token.strip("()[]:;.")
            if cleaned.isdigit() and len(cleaned) == 6:
                symbols.append(cleaned)
                continue
            if cleaned.isupper() and 2 <= len(cleaned) <= 5 and cleaned not in self._EXCLUDED_SYMBOLS:
                symbols.append(cleaned)
        return sorted(set(symbols))[:5]

    @staticmethod
    def _tone_score(tone: MarketAwarenessSignalStatus) -> float:
        if tone == MarketAwarenessSignalStatus.SUPPORTIVE:
            return 1.0
        if tone == MarketAwarenessSignalStatus.WARNING:
            return -1.0
        return 0.0

    @staticmethod
    def _aggregate_tone(score: float, has_items: bool, has_blockers: bool) -> MarketAwarenessSignalStatus:
        if not has_items and has_blockers:
            return MarketAwarenessSignalStatus.BLOCKED
        if score >= 0.18:
            return MarketAwarenessSignalStatus.SUPPORTIVE
        if score <= -0.12:
            return MarketAwarenessSignalStatus.WARNING
        return MarketAwarenessSignalStatus.MIXED

    @staticmethod
    def _explanation(
        tone: MarketAwarenessSignalStatus,
        dominant_topics: list[str],
        degraded: bool,
        item_count: int,
    ) -> str:
        if tone == MarketAwarenessSignalStatus.BLOCKED:
            return "Public news feeds were unavailable, so the observation is degraded."
        if not item_count:
            return "当前资讯集合中没有保留下高信号标题。"
        prefix = "News flow leans supportive." if tone == MarketAwarenessSignalStatus.SUPPORTIVE else "News flow leans cautious." if tone == MarketAwarenessSignalStatus.WARNING else "News flow is mixed."
        topic_text = f" Dominant topics: {', '.join(dominant_topics)}." if dominant_topics else ""
        degrade_text = " Some feeds degraded, so confidence is capped." if degraded else ""
        return f"{prefix}{topic_text}{degrade_text}"

from __future__ import annotations

import math
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from tradingcat.domain.news import NewsEventClass, NewsItem, NewsUrgency


_TRACKING_PREFIXES = ("utm_",)
_TRACKING_KEYS = {"spm", "from", "source", "campaign", "fbclid", "gclid"}


class NewsFilterService:
    """Deterministic news quality, relevance, and dedupe pipeline."""

    _SOURCE_QUALITY = {
        "cls": 0.92,
        "eastmoney": 0.86,
        "finnhub": 0.84,
        "alpha_vantage": 0.82,
        "google_news_cn_market": 0.65,
        "google_news_macro": 0.65,
    }

    def __init__(
        self,
        *,
        allow_sources: set[str] | None = None,
        deny_sources: set[str] | None = None,
        min_title_chars: int = 10,
    ) -> None:
        self._allow_sources = {source.casefold() for source in allow_sources} if allow_sources else None
        self._deny_sources = {source.casefold() for source in deny_sources or set()}
        self._min_title_chars = max(1, int(min_title_chars))

    def filter_items(
        self,
        items: list[NewsItem | dict[str, object]],
        *,
        target_symbols: set[str] | None = None,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> list[NewsItem]:
        now = now or datetime.now(UTC)
        target_symbols = {symbol.upper() for symbol in target_symbols or set()}
        candidates: list[NewsItem] = []
        for raw in items:
            item = self._coerce(raw)
            if item is None or not self._source_allowed(item.source):
                continue
            if len(_normalise_title(item.title)) < self._min_title_chars:
                continue
            enriched = self._enrich(item, target_symbols=target_symbols, now=now)
            candidates.append(enriched)

        deduped = self._dedupe(candidates)
        ranked = sorted(
            deduped,
            key=lambda item: (item.quality_score * 0.65 + item.relevance * 0.35, item.published_at or datetime.min.replace(tzinfo=UTC)),
            reverse=True,
        )
        return ranked[:limit] if limit is not None else ranked

    def _coerce(self, raw: NewsItem | dict[str, object]) -> NewsItem | None:
        if isinstance(raw, NewsItem):
            return raw
        try:
            return NewsItem.model_validate(raw)
        except Exception:
            return None

    def _source_allowed(self, source: str) -> bool:
        normalized = source.casefold()
        if normalized in self._deny_sources:
            return False
        if self._allow_sources is not None and normalized not in self._allow_sources:
            return False
        return True

    def _enrich(self, item: NewsItem, *, target_symbols: set[str], now: datetime) -> NewsItem:
        symbols = sorted({symbol.upper() for symbol in item.symbols})
        urgency = _classify_urgency(item.title)
        event_class = _classify_event(item.title)
        relevance = _score_relevance(item.title, symbols, target_symbols)
        source_quality = self._SOURCE_QUALITY.get(item.source.casefold(), 0.55)
        freshness = _freshness_score(item.published_at, now)
        urgency_boost = 0.12 if urgency == NewsUrgency.HIGH else 0.06 if urgency == NewsUrgency.MEDIUM else 0.0
        quality_score = min(max(source_quality * 0.55 + freshness * 0.25 + relevance * 0.20 + urgency_boost, 0.0), 1.0)
        return item.model_copy(
            update={
                "url": _normalise_url(item.url),
                "symbols": symbols,
                "urgency": urgency,
                "event_class": event_class,
                "relevance": round(relevance, 4),
                "quality_score": round(quality_score, 4),
            }
        )

    @staticmethod
    def _dedupe(items: list[NewsItem]) -> list[NewsItem]:
        deduped: dict[str, NewsItem] = {}
        for item in items:
            key = _dedupe_key(item)
            existing = deduped.get(key)
            if existing is None or item.quality_score > existing.quality_score:
                deduped[key] = item
        return list(deduped.values())


def _normalise_url(url: str | None) -> str | None:
    if not url:
        return None
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key not in _TRACKING_KEYS and not key.startswith(_TRACKING_PREFIXES)
    ]
    normalized = urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path.rstrip("/"),
            urlencode(query),
            "",
        )
    )
    return normalized or None


def _normalise_title(title: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\u4e00-\u9fff]+", " ", title.casefold())).strip()


def _dedupe_key(item: NewsItem) -> str:
    normalized_url = _normalise_url(item.url)
    if normalized_url:
        return f"url:{normalized_url}"
    return f"title:{_normalise_title(item.title)}"


def _classify_urgency(title: str) -> NewsUrgency:
    text = title.casefold()
    if any(keyword in text for keyword in {"突发", "紧急", "暂停", "停牌", "重大", "breaking", "urgent", "halt"}):
        return NewsUrgency.HIGH
    if any(keyword in text for keyword in {"财报", "业绩", "发布", "宣布", "并购", "收购", "earnings", "announce", "merger"}):
        return NewsUrgency.MEDIUM
    return NewsUrgency.LOW


def _classify_event(title: str) -> NewsEventClass:
    text = title.casefold()
    checks = [
        (NewsEventClass.EARNINGS, {"财报", "业绩", "earnings"}),
        (NewsEventClass.GUIDANCE, {"指引", "预期", "guidance"}),
        (NewsEventClass.M_AND_A, {"并购", "收购", "merger", "acquisition"}),
        (NewsEventClass.POLICY, {"政策", "刺激", "policy", "stimulus"}),
        (NewsEventClass.REGULATORY, {"监管", "处罚", "regulation", "regulatory"}),
        (NewsEventClass.CRISIS, {"突发", "危机", "违约", "停牌", "crisis", "default", "halt"}),
        (NewsEventClass.INDUSTRY, {"行业", "板块", "产业", "industry", "sector"}),
        (NewsEventClass.MANAGEMENT, {"管理层", "董事", "ceo", "cfo"}),
        (NewsEventClass.MACRO, {"宏观", "利率", "通胀", "cpi", "fed", "inflation"}),
    ]
    for event_class, keywords in checks:
        if any(keyword in text for keyword in keywords):
            return event_class
    return NewsEventClass.OTHER


def _score_relevance(title: str, symbols: list[str], target_symbols: set[str]) -> float:
    if not target_symbols:
        return 0.3
    symbol_set = set(symbols)
    if symbol_set & target_symbols:
        return 1.0
    title_upper = title.upper()
    if any(symbol in title_upper for symbol in target_symbols):
        return 0.9
    return 0.3


def _freshness_score(published_at: datetime | None, now: datetime) -> float:
    if published_at is None:
        return 0.35
    age_hours = max((now - published_at.astimezone(UTC)).total_seconds() / 3600.0, 0.0)
    if not math.isfinite(age_hours):
        return 0.35
    if age_hours <= 0.5:
        return 1.0
    if age_hours <= 2:
        return 0.85
    if age_hours <= 24:
        return 0.6
    if age_hours <= 72:
        return 0.35
    return 0.15

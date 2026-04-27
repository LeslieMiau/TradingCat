"""Detect when important news mentions a watched symbol.

Trigger:
- A news item in the observation has importance >= min_importance
- The item's extracted symbols intersect with the watchlist, OR
  the item title contains a watchlist symbol as a fallback (HK 4-digit codes)
- News tone is WARNING (supportive-only news is rarely actionable)

Severity:
- WARNING + risk/policy topic → urgent
- WARNING (other topics) → notable
- SUPPORTIVE + importance >= 0.6 → notable (highly important positive news)
- SUPPORTIVE < 0.6 or MIXED → skip
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Counter

from tradingcat.domain.models import (
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    Instrument,
    MarketAwarenessSignalStatus,
)


logger = logging.getLogger(__name__)


# Import at runtime to avoid circular dependency at module level
_MarketAwarenessNewsObservation = None
_MarketAwarenessNewsItem = None


def _lazy_imports():
    global _MarketAwarenessNewsObservation, _MarketAwarenessNewsItem
    if _MarketAwarenessNewsObservation is None:
        from tradingcat.domain.models import (
            MarketAwarenessNewsItem,
            MarketAwarenessNewsObservation,
        )
        _MarketAwarenessNewsObservation = MarketAwarenessNewsObservation  # noqa: used for type hint
        _MarketAwarenessNewsItem = MarketAwarenessNewsItem  # noqa: used for type hint


@dataclass(frozen=True)
class NewsDrivenConfig:
    min_importance: float = 0.4
    expires_hours: int = 36


def _stable_id(symbol: str, headline: str, as_of: date) -> str:
    raw = f"news_driven:{symbol}:{hashlib.sha1(headline.encode('utf-8')).hexdigest()[:12]}:{as_of.isoformat()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _match_symbols(item_title: str, item_symbols: list[str], watchlist: list[Instrument]) -> list[str]:
    """Return watchlist symbols that match this news item.

    Priority:
    1. Direct match via ``item.symbols`` (CN 6-digit codes, US 2-5 char tickers).
    2. Fallback: HK 4-digit codes found as substrings in the title.
    """
    watchlist_symbols = {inst.symbol for inst in watchlist}
    matched: set[str] = set()

    # Direct match from pre-extracted symbols
    for sym in item_symbols:
        if sym in watchlist_symbols:
            matched.add(sym)

    # Fallback: HK 4-digit codes appearing in title
    # These are typically numeric strings like "0700", "9988" (4 digits)
    title_lower = item_title.lower()
    for sym in watchlist_symbols:
        if sym in matched:
            continue
        if sym.isdigit() and len(sym) <= 5 and sym in title_lower:
            matched.add(sym)

    return sorted(matched)


def _aggregate_for_symbol(
    key_items: list,
    symbol: str,
) -> dict:
    """Aggregate news stats for *symbol* across all key items."""
    count = 0
    tone_scores: list[float] = []
    for item in key_items:
        title = getattr(item, "title", "") or ""
        item_syms = getattr(item, "symbols", []) or []
        if symbol in item_syms or (symbol.isdigit() and symbol in title):
            count += 1
            tone = getattr(item, "tone", None)
            if tone == MarketAwarenessSignalStatus.WARNING:
                tone_scores.append(-1.0)
            elif tone == MarketAwarenessSignalStatus.SUPPORTIVE:
                tone_scores.append(1.0)
            else:
                tone_scores.append(0.0)
    net_score = round(sum(tone_scores) / max(len(tone_scores), 1), 4) if tone_scores else 0.0
    return {"count": count, "net_tone_score": net_score}


class NewsDrivenDetector:
    """Emit insights when important news mentions a watched symbol."""

    def __init__(self, config: NewsDrivenConfig | None = None) -> None:
        self._config = config or NewsDrivenConfig()
        _lazy_imports()

    @property
    def config(self) -> NewsDrivenConfig:
        return self._config

    def required_lookback_days(self) -> int:
        return 0

    def detect(
        self,
        *,
        as_of: date,
        watchlist: list[Instrument],
        news_observation: object | None = None,
        now: datetime | None = None,
    ) -> list[Insight]:
        triggered_at = now or datetime.now(timezone.utc)
        if news_observation is None:
            return []

        key_items = getattr(news_observation, "key_items", []) or []
        if not key_items:
            return []

        degraded = getattr(news_observation, "degraded", False)
        blockers = getattr(news_observation, "blockers", []) or []

        out: list[Insight] = []
        seen_symbols: set[str] = set()

        for item in key_items:
            importance = getattr(item, "importance", 0.0) or 0.0
            if importance < self._config.min_importance:
                continue

            title = getattr(item, "title", "") or ""
            if not title:
                continue

            item_syms = getattr(item, "symbols", []) or []
            matched = _match_symbols(title, item_syms, watchlist)
            if not matched:
                continue

            tone = getattr(item, "tone", None)
            topic = getattr(item, "topic", "") or ""

            severity = self._resolve_severity(tone, topic, importance)
            if severity is None:
                continue

            confidence = self._compute_confidence(importance, tone, topic)

            for symbol in matched:
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)

                agg = _aggregate_for_symbol(key_items, symbol)
                evidence = self._build_evidence(
                    item=item,
                    symbol=symbol,
                    tone=tone,
                    topic=topic,
                    agg=agg,
                    degraded=degraded,
                    blockers=blockers,
                    triggered_at=triggered_at,
                )

                headline = self._build_headline(symbol, tone, topic, title)

                out.append(
                    Insight(
                        id=_stable_id(symbol, title, as_of),
                        kind=InsightKind.NEWS_DRIVEN,
                        severity=severity,
                        headline=headline,
                        subjects=[symbol],
                        causal_chain=evidence,
                        confidence=round(confidence, 4),
                        triggered_at=triggered_at,
                        expires_at=triggered_at + timedelta(hours=self._config.expires_hours),
                    )
                )

        return out

    def _resolve_severity(
        self,
        tone: object | None,
        topic: str,
        importance: float,
    ) -> InsightSeverity | None:
        if tone == MarketAwarenessSignalStatus.WARNING:
            if topic in ("risk", "policy"):
                return InsightSeverity.URGENT
            return InsightSeverity.NOTABLE
        if tone == MarketAwarenessSignalStatus.SUPPORTIVE and importance >= 0.6:
            return InsightSeverity.NOTABLE
        return None

    def _compute_confidence(
        self,
        importance: float,
        tone: object | None,
        topic: str,
    ) -> float:
        c = importance  # 0.4–1.0 range
        if tone == MarketAwarenessSignalStatus.WARNING:
            c += 0.1
        if topic in ("risk", "policy"):
            c += 0.1
        return min(c, 1.0)

    def _build_headline(
        self,
        symbol: str,
        tone: object | None,
        topic: str,
        title: str,
    ) -> str:
        """Build a concise headline ≤ 60 chars.

        Truncate the original title and prefix with tone indicator.
        """
        prefix = ""
        if tone == MarketAwarenessSignalStatus.WARNING and topic in ("risk", "policy"):
            prefix = "⚠ "
        elif tone == MarketAwarenessSignalStatus.WARNING:
            prefix = "⚠ "
        elif tone == MarketAwarenessSignalStatus.SUPPORTIVE:
            prefix = "✓ "

        # Truncate title to fit headline ≤ ~60 chars
        max_title_len = 55 - len(prefix)
        display_title = title if len(title) <= max_title_len else title[: max_title_len - 3] + "..."

        return f"{prefix}{symbol} {display_title}"

    def _build_evidence(
        self,
        *,
        item: object,
        symbol: str,
        tone: object | None,
        topic: str,
        agg: dict,
        degraded: bool,
        blockers: list[str],
        triggered_at: datetime,
    ) -> list[InsightEvidence]:
        title = getattr(item, "title", "") or ""
        source_name = getattr(item, "source", "") or ""
        published_at = getattr(item, "published_at", None)
        url = getattr(item, "url", None)

        # Evidence 1: news item details
        ev1 = InsightEvidence(
            source=f"news:{source_name}",
            fact=f"资讯: {title}",
            value={
                "source": source_name,
                "url": url or "",
                "published_at": published_at.isoformat() if isinstance(published_at, datetime) else "",
            },
            observed_at=triggered_at,
        )

        # Evidence 2: why it matters
        tone_label = tone.value if hasattr(tone, "value") else str(tone or "unknown")
        ev2 = InsightEvidence(
            source="insight_engine:news_driven",
            fact=f"{symbol} 出现在该资讯中(情感={tone_label}, 话题={topic})",
            value={
                "matched_symbol": symbol,
                "tone": tone_label,
                "topic": topic,
                "importance": round(getattr(item, "importance", 0.0) or 0.0, 4),
            },
            observed_at=triggered_at,
        )

        # Evidence 3: aggregate context
        ev3 = InsightEvidence(
            source="insight_engine:news_driven",
            fact=f"今日 {symbol} 相关资讯 {agg['count']} 条, 净情感分 {agg['net_tone_score']:+.2f}",
            value={
                "symbol_news_count": agg["count"],
                "net_tone_score": agg["net_tone_score"],
            },
            observed_at=triggered_at,
        )

        # Evidence 4: data health
        health_label = "数据源部分降级" if degraded else "数据源正常"
        ev4 = InsightEvidence(
            source="insight_engine:news_driven",
            fact=health_label + (f"({'; '.join(blockers)})" if blockers else ""),
            value={
                "degraded": degraded,
                "blockers": blockers,
            },
            observed_at=triggered_at,
        )

        return [ev1, ev2, ev3, ev4]

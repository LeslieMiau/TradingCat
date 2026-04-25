from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from tradingcat.domain.models import Instrument
from tradingcat.domain.news import NewsItem
from tradingcat.strategies.research_candidates import TechnicalFeatureSnapshot


@dataclass(frozen=True, slots=True)
class UniverseCandidate:
    instrument: Instrument
    score: float
    technical_score: float
    fundamental_score: float
    news_score: float
    reasons: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["instrument"] = self.instrument.model_dump(mode="json")
        return payload


class UniverseScreener:
    """Research-only multi-dimensional universe screener."""

    def __init__(
        self,
        *,
        technical_weight: float = 0.4,
        fundamental_weight: float = 0.35,
        news_weight: float = 0.25,
    ) -> None:
        total = technical_weight + fundamental_weight + news_weight
        if total <= 0:
            total = 1.0
        self._technical_weight = technical_weight / total
        self._fundamental_weight = fundamental_weight / total
        self._news_weight = news_weight / total

    def screen(
        self,
        instruments: list[Instrument],
        *,
        technical: dict[str, TechnicalFeatureSnapshot | dict[str, Any]] | None = None,
        fundamentals: dict[str, dict[str, Any]] | None = None,
        news: list[NewsItem | dict[str, Any]] | None = None,
        limit: int | None = None,
    ) -> list[UniverseCandidate]:
        technical = technical or {}
        fundamentals = fundamentals or {}
        news_by_symbol = self._news_by_symbol(news or [])
        candidates = [
            self._score_instrument(
                instrument,
                technical=technical.get(instrument.symbol),
                fundamentals=fundamentals.get(instrument.symbol, {}),
                news_items=news_by_symbol.get(instrument.symbol, []),
            )
            for instrument in instruments
        ]
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        return ranked[:limit] if limit is not None else ranked

    def _score_instrument(
        self,
        instrument: Instrument,
        *,
        technical: TechnicalFeatureSnapshot | dict[str, Any] | None,
        fundamentals: dict[str, Any],
        news_items: list[NewsItem],
    ) -> UniverseCandidate:
        technical_score, technical_reasons, technical_meta = _score_technical(technical)
        fundamental_score, fundamental_reasons = _score_fundamental(fundamentals)
        news_score, news_reasons = _score_news(news_items)
        score = (
            technical_score * self._technical_weight
            + fundamental_score * self._fundamental_weight
            + news_score * self._news_weight
        )
        return UniverseCandidate(
            instrument=instrument,
            score=round(score, 4),
            technical_score=technical_score,
            fundamental_score=fundamental_score,
            news_score=news_score,
            reasons=[*technical_reasons, *fundamental_reasons, *news_reasons],
            metadata={
                "execution_mode": "research_only",
                "technical": technical_meta,
                "fundamentals": fundamentals,
                "news_count": len(news_items),
            },
        )

    @staticmethod
    def _news_by_symbol(items: list[NewsItem | dict[str, Any]]) -> dict[str, list[NewsItem]]:
        grouped: dict[str, list[NewsItem]] = {}
        for raw in items:
            try:
                item = raw if isinstance(raw, NewsItem) else NewsItem.model_validate(raw)
            except Exception:
                continue
            for symbol in item.symbols:
                grouped.setdefault(symbol.upper(), []).append(item)
        return grouped


def _score_technical(snapshot: TechnicalFeatureSnapshot | dict[str, Any] | None) -> tuple[float, list[str], dict[str, Any]]:
    if snapshot is None:
        return 0.4, ["technical data missing"], {}
    data = snapshot.as_metadata() if isinstance(snapshot, TechnicalFeatureSnapshot) else dict(snapshot)
    score = 0.45
    reasons: list[str] = []
    if data.get("trend_alignment") == "bullish_alignment":
        score += 0.25
        reasons.append("bullish MA alignment")
    if data.get("trend_alignment") == "bearish_alignment":
        score -= 0.20
        reasons.append("bearish MA alignment")
    momentum = data.get("momentum_state")
    if momentum in {"positive_momentum", "bollinger_volume_breakout"}:
        score += 0.20
        reasons.append(str(momentum))
    if momentum in {"oversold"}:
        score += 0.10
        reasons.append("oversold rebound setup")
    if momentum in {"overbought", "negative_momentum", "bollinger_breakdown"}:
        score -= 0.12
        reasons.append(str(momentum))
    if (data.get("volume_ratio_20d") or 0) >= 1.5:
        score += 0.08
        reasons.append("volume expansion")
    return round(_clamp(score), 4), reasons, data


def _score_fundamental(row: dict[str, Any]) -> tuple[float, list[str]]:
    if not row:
        return 0.4, ["fundamental data missing"]
    score = 0.45
    reasons: list[str] = []
    pe = _float(row.get("pe") or row.get("pe_ttm"))
    pb = _float(row.get("pb"))
    roe = _float(row.get("roe") or row.get("roe_dt"))
    growth = _float(row.get("revenue_growth") or row.get("netprofit_yoy") or row.get("or_yoy"))
    debt = _float(row.get("debt_to_assets"))
    if pe is not None and 0 < pe <= 25:
        score += 0.12
        reasons.append("reasonable PE")
    if pb is not None and 0 < pb <= 3:
        score += 0.08
        reasons.append("reasonable PB")
    if roe is not None and roe >= 10:
        score += 0.18
        reasons.append("strong ROE")
    if growth is not None and growth >= 15:
        score += 0.15
        reasons.append("growth above threshold")
    if debt is not None and debt >= 75:
        score -= 0.12
        reasons.append("high leverage")
    return round(_clamp(score), 4), reasons


def _score_news(items: list[NewsItem]) -> tuple[float, list[str]]:
    if not items:
        return 0.4, ["news data missing"]
    best = max(items, key=lambda item: item.quality_score * 0.6 + item.relevance * 0.4)
    score = best.quality_score * 0.6 + best.relevance * 0.4
    return round(_clamp(score), 4), [f"news: {best.event_class.value}/{best.urgency.value}"]


def _float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)

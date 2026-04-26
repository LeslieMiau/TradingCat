"""Unified news models for research/advisory pipelines."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class NewsUrgency(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class NewsEventClass(str, Enum):
    EARNINGS = "earnings"
    GUIDANCE = "guidance"
    M_AND_A = "m_and_a"
    POLICY = "policy"
    REGULATORY = "regulatory"
    CRISIS = "crisis"
    INDUSTRY = "industry"
    MANAGEMENT = "management"
    MACRO = "macro"
    OTHER = "other"


class NewsItem(BaseModel):
    source: str
    title: str
    url: str | None = None
    published_at: datetime | None = None
    summary: str = ""
    symbols: list[str] = Field(default_factory=list)
    urgency: NewsUrgency = NewsUrgency.LOW
    event_class: NewsEventClass = NewsEventClass.OTHER
    relevance: float = 0.3
    quality_score: float = 0.5
    raw: dict[str, object] = Field(default_factory=dict)

    @field_validator("relevance", "quality_score")
    @classmethod
    def _score_bounds(cls, value: float) -> float:
        return min(max(float(value), 0.0), 1.0)

    @field_validator("source", "title")
    @classmethod
    def _required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("news source/title cannot be empty")
        return cleaned

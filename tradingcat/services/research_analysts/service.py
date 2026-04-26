from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from tradingcat.adapters.llm import LLMMessage, LLMProvider


class AnalystOutput(BaseModel):
    analyst_id: str
    summary: str
    bullets: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    risks: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


class ResearchAnalystService:
    """Advisory-only LLM analyst wrapper.

    The service returns research artifacts only. It never creates Signals,
    OrderIntents, approvals, or broker actions.
    """

    def __init__(self, provider: LLMProvider) -> None:
        self._provider = provider

    def analyze(self, analyst_id: str, payload: dict[str, Any], *, source_refs: list[str] | None = None) -> AnalystOutput:
        messages = [
            LLMMessage(
                role="system",
                content=(
                    "You are a research analyst. Produce advisory research only. "
                    "Do not recommend trades, orders, approvals, or execution actions."
                ),
            ),
            LLMMessage(role="user", content=_payload_prompt(analyst_id, payload)),
        ]
        response = self._provider.chat(messages, purpose=f"analyst:{analyst_id}")
        bullets = _extract_bullets(response.text)
        return AnalystOutput(
            analyst_id=analyst_id,
            summary=_summary(response.text),
            bullets=bullets,
            confidence=_confidence(payload),
            risks=_extract_risks(response.text),
            source_refs=source_refs or [],
            metadata={
                "provider": response.provider,
                "model": response.model,
                "tokens_in": response.tokens_in,
                "tokens_out": response.tokens_out,
                "cost": response.cost,
                "advisory_only": True,
            },
        )


def _payload_prompt(analyst_id: str, payload: dict[str, Any]) -> str:
    return f"Analyst: {analyst_id}\nInput payload:\n{payload!r}\nReturn concise summary, bullets, risks."


def _summary(text: str) -> str:
    for line in text.splitlines():
        cleaned = line.strip(" -\t")
        if cleaned:
            return cleaned[:600]
    return text[:600]


def _extract_bullets(text: str) -> list[str]:
    bullets = []
    for line in text.splitlines():
        cleaned = line.strip()
        if cleaned.startswith(("-", "*")):
            value = cleaned.lstrip("-* ").strip()
            if value:
                bullets.append(value)
    return bullets[:8]


def _extract_risks(text: str) -> list[str]:
    risks = []
    for line in text.splitlines():
        lowered = line.casefold()
        if "risk" in lowered or "风险" in lowered:
            risks.append(line.strip(" -*\t"))
    return risks[:5]


def _confidence(payload: dict[str, Any]) -> float:
    source_count = len(payload.get("sources") or []) if isinstance(payload.get("sources"), list) else 0
    confidence = 0.45 + min(source_count, 4) * 0.1
    return round(min(confidence, 0.85), 4)

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LLMMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class LLMResponse:
    text: str
    provider: str
    model: str
    tokens_in: int
    tokens_out: int
    cost: float


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    provider: str
    model: str

    def chat(self, messages: list[LLMMessage], *, purpose: str = "research") -> LLMResponse: ...

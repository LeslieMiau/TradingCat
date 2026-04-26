from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Iterable

from tradingcat.adapters.llm import LLMMessage, LLMProvider, LLMResponse


@dataclass(frozen=True, slots=True)
class LLMCacheEntry:
    key: str
    response: LLMResponse


class InMemoryLLMResponseCache:
    def __init__(self) -> None:
        self._entries: dict[str, LLMResponse] = {}

    def key(self, *, provider: str, model: str, messages: Iterable[LLMMessage], purpose: str) -> str:
        payload = {
            "provider": provider,
            "model": model,
            "purpose": purpose,
            "messages": [asdict(message) for message in messages],
        }
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def get(self, key: str) -> LLMResponse | None:
        return self._entries.get(key)

    def put(self, key: str, response: LLMResponse) -> None:
        self._entries[key] = response


class CachedLLMProvider:
    """Read-through cache wrapper for advisory LLM providers."""

    def __init__(self, inner: LLMProvider, cache: InMemoryLLMResponseCache) -> None:
        self._inner = inner
        self._cache = cache
        self.provider = inner.provider
        self.model = inner.model

    def chat(self, messages: list[LLMMessage], *, purpose: str = "research") -> LLMResponse:
        key = self._cache.key(provider=self.provider, model=self.model, messages=messages, purpose=purpose)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        response = self._inner.chat(messages, purpose=purpose)
        self._cache.put(key, response)
        return response

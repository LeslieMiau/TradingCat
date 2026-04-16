"""Shared HTTP client used by every external sentiment-source adapter.

Design goals (from `.harness/spec.md` §4):
- Single `httpx.Client` shared across fetchers — one outbound TCP pool.
- In-memory TTL cache keyed on `(method, url, sorted_params, frozen_headers)`.
- Negative cache on failure so a transient 4xx/5xx doesn't hammer the endpoint.
- Exponential backoff with bounded retries; never raises to the caller — a
  failed call returns `None` so upstream services can mark the indicator stale.
- Close hook callable from `runtime.py` shutdown pathway.

Intentionally thin: no async API, no interceptors. The whole point is one
file, one construct, one place to review when CNN/eastmoney changes shape.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx


logger = logging.getLogger(__name__)


def _freeze(params: dict[str, Any] | None) -> tuple[tuple[str, str], ...]:
    if not params:
        return ()
    return tuple(sorted((str(k), str(v)) for k, v in params.items()))


@dataclass(slots=True)
class _CacheEntry:
    expires_at: float
    payload: dict[str, Any] | None  # None = negative cache


class SentimentHttpClient:
    """Thin wrapper around `httpx.Client` with TTL cache + retries.

    Never raises. `get_json` returns `None` on any failure path. Callers must
    treat `None` as "source unavailable" and downgrade their indicator.
    """

    def __init__(
        self,
        *,
        timeout_seconds: float = 5.0,
        retries: int = 2,
        backoff_seconds: float = 0.5,
        default_ttl_seconds: int = 600,
        negative_ttl_seconds: int = 60,
        default_headers: dict[str, str] | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._timeout_seconds = max(0.1, float(timeout_seconds))
        self._retries = max(0, int(retries))
        self._backoff_seconds = max(0.0, float(backoff_seconds))
        self._default_ttl_seconds = max(1, int(default_ttl_seconds))
        self._negative_ttl_seconds = max(1, int(negative_ttl_seconds))
        self._default_headers = dict(default_headers or {})
        self._owned_client = client is None
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(self._timeout_seconds),
            headers=self._default_headers,
        )
        self._cache: dict[tuple, _CacheEntry] = {}
        self._cache_lock = threading.Lock()

    # ------------------------------------------------------------------ cache

    def _cache_get(self, key: tuple) -> _CacheEntry | None:
        now = time.monotonic()
        with self._cache_lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._cache.pop(key, None)
                return None
            return entry

    def _cache_put(self, key: tuple, payload: dict[str, Any] | None, ttl: int) -> None:
        with self._cache_lock:
            self._cache[key] = _CacheEntry(expires_at=time.monotonic() + ttl, payload=payload)

    def invalidate(self) -> None:
        with self._cache_lock:
            self._cache.clear()

    # ------------------------------------------------------------------ public

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        ttl_seconds: int | None = None,
        negative_ttl_seconds: int | None = None,
    ) -> dict[str, Any] | None:
        """Fetch JSON. Returns the parsed dict, or `None` on failure."""

        cache_key = ("GET", url, _freeze(params), _freeze(headers))
        cached = self._cache_get(cache_key)
        if cached is not None:
            return cached.payload

        ttl = int(ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds)
        neg_ttl = int(
            negative_ttl_seconds if negative_ttl_seconds is not None else self._negative_ttl_seconds
        )

        attempt = 0
        last_exc: Exception | None = None
        while attempt <= self._retries:
            try:
                response = self._client.get(url, params=params, headers=headers)
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict):
                    # Only dict-shaped JSON is supported — callers encode their own
                    # shape. Wrap it to keep the contract uniform.
                    payload = {"data": payload}
                self._cache_put(cache_key, payload, ttl)
                return payload
            except Exception as exc:  # noqa: BLE001 — deliberate catch-all
                last_exc = exc
                logger.warning(
                    "SentimentHttpClient GET failed",
                    extra={"url": url, "attempt": attempt, "error": str(exc)},
                )
                attempt += 1
                if attempt > self._retries:
                    break
                if self._backoff_seconds > 0:
                    time.sleep(self._backoff_seconds * (2 ** (attempt - 1)))

        logger.info(
            "SentimentHttpClient giving up on %s after %s attempts: %s",
            url,
            self._retries + 1,
            last_exc,
        )
        self._cache_put(cache_key, None, neg_ttl)
        return None

    def close(self) -> None:
        if self._owned_client:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                logger.debug("SentimentHttpClient close failed (ignored)", exc_info=True)

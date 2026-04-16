"""Unit tests for `SentimentHttpClient`.

Uses `httpx.MockTransport` so no real network traffic is generated. Covers
contract items from `.harness/spec.md` §4:

- `get_json` never raises; failures return `None` and are negative-cached.
- Successful payloads are TTL-cached across calls.
- Non-dict JSON is wrapped in `{"data": ...}` for a uniform caller shape.
- Retries honour `retries` and stop hitting the transport after exhaustion.
"""
from __future__ import annotations

import httpx
import pytest

from tradingcat.adapters.sentiment_http import SentimentHttpClient


def _build_client(transport: httpx.MockTransport, **overrides) -> SentimentHttpClient:
    client_args = {
        "timeout_seconds": 1.0,
        "retries": 2,
        "backoff_seconds": 0.0,  # no sleep in tests
        "default_ttl_seconds": 5,
        "negative_ttl_seconds": 5,
    }
    client_args.update(overrides)
    return SentimentHttpClient(
        client=httpx.Client(transport=transport, timeout=1.0),
        **client_args,
    )


def test_get_json_returns_parsed_dict_for_2xx():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"foo": 1})

    client = _build_client(httpx.MockTransport(handler))
    try:
        result = client.get_json("https://example.invalid/endpoint")
        assert result == {"foo": 1}
    finally:
        client.close()


def test_get_json_wraps_non_dict_payloads_in_data_key():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[1, 2, 3])

    client = _build_client(httpx.MockTransport(handler))
    try:
        result = client.get_json("https://example.invalid/endpoint")
        assert result == {"data": [1, 2, 3]}
    finally:
        client.close()


def test_get_json_returns_none_after_retries_exhausted():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(500, text="server error")

    client = _build_client(httpx.MockTransport(handler), retries=2)
    try:
        result = client.get_json("https://example.invalid/endpoint")
        assert result is None
        # 1 initial attempt + 2 retries = 3 calls
        assert call_count["n"] == 3
    finally:
        client.close()


def test_get_json_caches_successful_responses_across_calls():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"value": call_count["n"]})

    client = _build_client(httpx.MockTransport(handler))
    try:
        first = client.get_json("https://example.invalid/endpoint")
        second = client.get_json("https://example.invalid/endpoint")
        assert first == {"value": 1}
        # Same URL → cache hit, transport only called once.
        assert second == first
        assert call_count["n"] == 1
    finally:
        client.close()


def test_get_json_negative_caches_failures():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(503, text="upstream down")

    client = _build_client(httpx.MockTransport(handler), retries=0)
    try:
        assert client.get_json("https://example.invalid/endpoint") is None
        first_call_total = call_count["n"]
        # Second invocation should not re-hit the transport — negative cache.
        assert client.get_json("https://example.invalid/endpoint") is None
        assert call_count["n"] == first_call_total
    finally:
        client.close()


def test_get_json_different_params_use_different_cache_keys():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"q": request.url.query.decode() if isinstance(request.url.query, bytes) else str(request.url.query)})

    client = _build_client(httpx.MockTransport(handler))
    try:
        first = client.get_json("https://example.invalid/endpoint", params={"a": "1"})
        second = client.get_json("https://example.invalid/endpoint", params={"a": "2"})
        assert first["q"] != second["q"]
    finally:
        client.close()


def test_invalidate_clears_cache():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        return httpx.Response(200, json={"n": call_count["n"]})

    client = _build_client(httpx.MockTransport(handler))
    try:
        assert client.get_json("https://example.invalid/endpoint") == {"n": 1}
        client.invalidate()
        assert client.get_json("https://example.invalid/endpoint") == {"n": 2}
    finally:
        client.close()


def test_close_is_safe_to_call_when_client_was_injected():
    # When the caller injects a pre-built httpx.Client, we shouldn't close it.
    injected = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    wrapper = SentimentHttpClient(client=injected)
    wrapper.close()  # must not raise
    # Injected client still usable after wrapper.close()
    assert injected.get("http://example.invalid").status_code == 200
    injected.close()


def test_get_json_never_raises_on_unexpected_exceptions(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise RuntimeError("connection exploded")

    client = _build_client(httpx.MockTransport(handler), retries=1)
    try:
        assert client.get_json("https://example.invalid/endpoint") is None
    finally:
        client.close()


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__])

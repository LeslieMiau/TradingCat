"""Unit tests for `HKSouthboundClient`.

All HTTP interactions are driven by `httpx.MockTransport` injected into the
shared `SentimentHttpClient`, so no real network calls are made.
"""
from __future__ import annotations

import json

import httpx
import pytest

from tradingcat.adapters.sentiment_http import SentimentHttpClient
from tradingcat.adapters.sentiment_sources.hk_southbound import (
    HKSouthboundClient,
    HKSouthboundReading,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(handler) -> tuple[HKSouthboundClient, SentimentHttpClient]:
    """Wrap a handler in a SentimentHttpClient + HKSouthboundClient."""

    transport = httpx.MockTransport(handler)
    http = SentimentHttpClient(
        timeout_seconds=2.0,
        retries=0,
        backoff_seconds=0.0,
        default_ttl_seconds=1,
        negative_ttl_seconds=1,
        client=httpx.Client(transport=transport),
    )
    return HKSouthboundClient(http, window_days=5, ttl_seconds=1), http


def _kline_payload(rows: list[str]) -> dict:
    """Build a minimal East Money kline payload."""
    return {"data": {"klines": rows}}


# ---------------------------------------------------------------------------
# Happy-path parsing
# ---------------------------------------------------------------------------


def test_southbound_positive_net(tmp_path):
    """Positive southbound net = mainland buying HK stocks."""

    # 5 rows: each with net +20000 万 (2亿)
    rows = [
        "2026-04-11,100000,80000,20000",
        "2026-04-12,110000,90000,20000",
        "2026-04-13,105000,85000,20000",
        "2026-04-14,120000,100000,20000",
        "2026-04-15,115000,95000,20000",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload(rows))

    client, _ = _make_client(handler)
    reading = client.fetch()
    assert reading is not None
    # Total: 5 * 20000 = 100000 万 = 1.0 HKD bn
    assert reading.net_5d_hkd_bn == pytest.approx(1.0, abs=1e-3)


def test_southbound_negative_net(tmp_path):
    """Negative net = mainland selling HK stocks."""

    rows = [
        "2026-04-11,80000,100000,-20000",
        "2026-04-12,85000,110000,-25000",
        "2026-04-13,90000,105000,-15000",
        "2026-04-14,75000,120000,-45000",
        "2026-04-15,80000,115000,-35000",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload(rows))

    client, _ = _make_client(handler)
    reading = client.fetch()
    assert reading is not None
    # Total: -20000 + -25000 + -15000 + -45000 + -35000 = -140000 万 = -1.4 bn
    assert reading.net_5d_hkd_bn == pytest.approx(-1.4, abs=1e-3)


def test_southbound_window_slices_last_n_rows():
    """When more rows than window_days, only last N are summed."""

    rows = [
        "2026-04-09,100000,100000,0",
        "2026-04-10,100000,100000,0",
        "2026-04-11,100000,100000,0",
        "2026-04-12,100000,100000,0",
        "2026-04-13,100000,100000,0",
        "2026-04-14,100000,50000,50000",  # only this
        "2026-04-15,100000,50000,50000",  # and this
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload(rows))

    transport = httpx.MockTransport(handler)
    http = SentimentHttpClient(
        timeout_seconds=2.0, retries=0, backoff_seconds=0.0,
        default_ttl_seconds=1, negative_ttl_seconds=1,
        client=httpx.Client(transport=transport),
    )
    client = HKSouthboundClient(http, window_days=2, ttl_seconds=1)
    reading = client.fetch()
    assert reading is not None
    # Last 2 rows: 50000 + 50000 = 100000 万 = 1.0 bn
    assert reading.net_5d_hkd_bn == pytest.approx(1.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Error / edge cases
# ---------------------------------------------------------------------------


def test_southbound_missing_klines_field():
    """Payload without 'klines' key → returns None."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": {"something": "else"}})

    client, _ = _make_client(handler)
    assert client.fetch() is None


def test_southbound_empty_klines():
    """Empty klines list → returns None."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload([]))

    client, _ = _make_client(handler)
    assert client.fetch() is None


def test_southbound_http_500():
    """Server error → returns None."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client, _ = _make_client(handler)
    assert client.fetch() is None


def test_southbound_non_numeric_rows_skipped():
    """Rows with non-numeric net field are skipped; valid rows still parsed."""

    rows = [
        "2026-04-11,100000,90000,bad_value",
        "2026-04-12,100000,50000,50000",
        "2026-04-13,100000,50000,50000",
        "2026-04-14,X,Y,Z",
        "2026-04-15,100000,50000,50000",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload(rows))

    client, _ = _make_client(handler)
    reading = client.fetch()
    assert reading is not None
    # 3 valid rows: 50000 * 3 = 150000 万 = 1.5 bn
    assert reading.net_5d_hkd_bn == pytest.approx(1.5, abs=1e-3)


def test_southbound_short_rows_skipped():
    """Rows with fewer than 4 fields are skipped."""

    rows = [
        "2026-04-14,100000",  # too short
        "2026-04-15,100000,50000,50000",  # valid
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_kline_payload(rows))

    client, _ = _make_client(handler)
    reading = client.fetch()
    assert reading is not None
    assert reading.net_5d_hkd_bn == pytest.approx(0.5, abs=1e-3)

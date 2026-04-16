"""Unit tests for `CNMarketFlowsClient`.

All HTTP interactions are driven by `httpx.MockTransport` injected into the
shared `SentimentHttpClient`, so no real network calls are made.
"""
from __future__ import annotations

import json

import httpx
import pytest

from tradingcat.adapters.sentiment_http import SentimentHttpClient
from tradingcat.adapters.sentiment_sources.cn_market_flows import (
    CNMarketFlowsClient,
    CNMarginReading,
    CNNorthboundReading,
    CNTurnoverReading,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_client(handler) -> tuple[CNMarketFlowsClient, SentimentHttpClient]:
    """Wrap a handler in a SentimentHttpClient + CNMarketFlowsClient."""

    transport = httpx.MockTransport(handler)
    http = SentimentHttpClient(
        timeout_seconds=2.0,
        retries=0,
        backoff_seconds=0.0,
        default_ttl_seconds=1,
        negative_ttl_seconds=1,
        client=httpx.Client(transport=transport),
    )
    return CNMarketFlowsClient(
        http,
        turnover_universe_size=10,
        northbound_window_days=5,
        ttl_seconds=1,
    ), http


# ---------------------------------------------------------------------------
# Turnover
# ---------------------------------------------------------------------------


def _turnover_handler(request: httpx.Request) -> httpx.Response:
    """Return a minimal clist/get payload with 5 stocks."""
    diff = {
        str(i): {"f8": float(rate)}
        for i, rate in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])
    }
    body = {"rc": 0, "rt": 1, "data": {"total": 5, "diff": diff}}
    return httpx.Response(200, json=body)


def test_turnover_parses_correct_median():
    client, _ = _make_client(_turnover_handler)
    reading = client.fetch_turnover()
    assert isinstance(reading, CNTurnoverReading)
    # sorted [1.0, 2.0, 3.0, 4.0, 5.0] → median = 3.0
    assert reading.median_pct == pytest.approx(3.0, abs=1e-3)
    assert reading.sample_size == 5


def test_turnover_handles_list_diff():
    """The diff field can be a list instead of a dict."""

    def handler(request: httpx.Request) -> httpx.Response:
        diff = [{"f8": 2.0}, {"f8": 4.0}]
        body = {"data": {"diff": diff}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    reading = client.fetch_turnover()
    assert reading is not None
    assert reading.median_pct == pytest.approx(3.0, abs=1e-3)


def test_turnover_returns_none_on_empty_diff():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"data": {"diff": {}}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    assert client.fetch_turnover() is None


def test_turnover_returns_none_on_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="Internal Server Error")

    client, _ = _make_client(handler)
    assert client.fetch_turnover() is None


def test_turnover_skips_non_numeric_rates():
    def handler(request: httpx.Request) -> httpx.Response:
        diff = {"0": {"f8": 2.0}, "1": {"f8": "-"}, "2": {"f8": 4.0}}
        body = {"data": {"diff": diff}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    reading = client.fetch_turnover()
    assert reading is not None
    assert reading.sample_size == 2
    assert reading.median_pct == pytest.approx(3.0, abs=1e-3)


# ---------------------------------------------------------------------------
# Northbound
# ---------------------------------------------------------------------------


def _northbound_handler(request: httpx.Request) -> httpx.Response:
    """Return a minimal kamt.kline payload with 5 daily rows."""
    # Each row is comma-separated: date, buy, sell, net
    # net values in 万元 (10,000 CNY).
    # 5 rows × 20万元 net = 100万元 = 0.001bn
    rows = [
        "2026-04-11,1000,800,200000",    # 20万元 = 0.002bn
        "2026-04-12,1000,800,200000",
        "2026-04-13,1000,800,200000",
        "2026-04-14,1000,800,200000",
        "2026-04-15,1000,800,200000",
    ]
    body = {"data": {"s2n": rows}}
    return httpx.Response(200, json=body)


def test_northbound_parses_5d_net():
    client, _ = _make_client(_northbound_handler)
    reading = client.fetch_northbound()
    assert isinstance(reading, CNNorthboundReading)
    # 5 × 200000 万 = 1000000 万 = 1000000 / 1e5 = 10.0 bn
    assert reading.net_5d_bn == pytest.approx(10.0, abs=0.1)


def test_northbound_returns_none_on_missing_s2n():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"data": {"other": []}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    assert client.fetch_northbound() is None


def test_northbound_returns_none_on_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    client, _ = _make_client(handler)
    assert client.fetch_northbound() is None


def test_northbound_negative_flow():
    """Negative net values produce negative reading."""

    def handler(request: httpx.Request) -> httpx.Response:
        rows = [f"2026-04-{11+i},1000,800,-500000" for i in range(5)]
        body = {"data": {"s2n": rows}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    reading = client.fetch_northbound()
    assert reading is not None
    # 5 × -500000 万 = -2500000 万 = -2500000 / 1e5 = -25.0 bn
    assert reading.net_5d_bn == pytest.approx(-25.0, abs=0.1)


# ---------------------------------------------------------------------------
# Margin
# ---------------------------------------------------------------------------


def _margin_handler(request: httpx.Request) -> httpx.Response:
    """Return two monthly rows for MoM computation."""
    body = {
        "result": {
            "data": [
                {"DIM_DATE": "2026-04-01", "RZRQYE": 2100000000000},  # current
                {"DIM_DATE": "2026-03-01", "RZRQYE": 2000000000000},  # previous
            ]
        }
    }
    return httpx.Response(200, json=body)


def test_margin_computes_mom_pct():
    client, _ = _make_client(_margin_handler)
    reading = client.fetch_margin_balance()
    assert isinstance(reading, CNMarginReading)
    # (2.1T - 2.0T) / 2.0T * 100 = 5.0%
    assert reading.mom_pct == pytest.approx(5.0, abs=0.01)


def test_margin_negative_mom():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "result": {
                "data": [
                    {"DIM_DATE": "2026-04-01", "RZRQYE": 1800000000000},
                    {"DIM_DATE": "2026-03-01", "RZRQYE": 2000000000000},
                ]
            }
        }
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    reading = client.fetch_margin_balance()
    assert reading is not None
    # (1.8T - 2.0T) / 2.0T * 100 = -10.0%
    assert reading.mom_pct == pytest.approx(-10.0, abs=0.01)


def test_margin_returns_none_on_single_row():
    def handler(request: httpx.Request) -> httpx.Response:
        body = {"result": {"data": [{"RZRQYE": 2000000000000}]}}
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    assert client.fetch_margin_balance() is None


def test_margin_returns_none_on_500():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="error")

    client, _ = _make_client(handler)
    assert client.fetch_margin_balance() is None


def test_margin_tries_alternative_field_name():
    """If RZRQYE is missing, try RZYE."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = {
            "result": {
                "data": [
                    {"DIM_DATE": "2026-04-01", "RZYE": 2050000000000},
                    {"DIM_DATE": "2026-03-01", "RZYE": 2000000000000},
                ]
            }
        }
        return httpx.Response(200, json=body)

    client, _ = _make_client(handler)
    reading = client.fetch_margin_balance()
    assert reading is not None
    assert reading.mom_pct == pytest.approx(2.5, abs=0.01)

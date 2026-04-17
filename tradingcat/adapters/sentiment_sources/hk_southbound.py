"""HK southbound (mainland → HK) flow fetcher.

Southbound fund flows represent mainland Chinese institutional/retail money
entering the Hong Kong market via Stock Connect.  Positive net flow is
generally viewed as bullish for HK equities; sustained outflows signal
risk-off sentiment from mainland participants toward HK.

Data source: East Money's HKEX southbound summary API
(``push2.eastmoney.com/api/qt/kamt.kline/get`` with the southbound fields).
The endpoint is the same as the northbound one but uses different column
selectors (``fields1=f1,f3,f5`` for southbound net buy).

Failure mode contract: ``fetch()`` returns ``None`` on any error (HTTP,
parse, shape, type).  Upstream callers must treat ``None`` as "source
unavailable" and downgrade their indicator.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HKSouthboundReading:
    """5-day net southbound flow (HKD billions, positive = mainland buying HK)."""

    net_5d_hkd_bn: float  # e.g. +8.3 or -5.1
    fetched_at: datetime


# East Money southbound kline endpoint (same host as northbound,
# different secid for SH Connect southbound + SZ Connect southbound).
_SOUTHBOUND_KLINE_URL = "https://push2.eastmoney.com/api/qt/kamt.kline/get"


class HKSouthboundClient:
    """Thin wrapper around the East Money southbound Stock Connect endpoint.

    Fetches the daily kline for southbound net buy, sums the last N rows
    (default 5 days) into a single reading, and returns a typed result.
    Returns ``None`` on any failure.
    """

    def __init__(
        self,
        http: SentimentHttpClient,
        *,
        window_days: int = 5,
        ttl_seconds: int = 1800,
    ) -> None:
        self._http = http
        self._window_days = max(1, int(window_days))
        self._ttl_seconds = max(1, int(ttl_seconds))

    def fetch(self) -> HKSouthboundReading | None:
        """Fetch southbound 5d net flow in HKD billions.

        The East Money endpoint returns daily rows like::

            "klines": ["2026-04-14,1234567.00,-5678901.00,...", ...]

        Southbound net buy is typically in field index 2 (s2n: south-to-north
        net, which for southbound is the net buy in wan-yuan).  We sum the
        last ``window_days`` rows and convert wan → HKD billion.
        """
        payload = self._http.get_json(
            _SOUTHBOUND_KLINE_URL,
            params={
                "fields1": "f1,f3,f5",
                "fields2": "f51,f52,f54,f56",
                "klt": "101",  # daily
                "lmt": str(self._window_days + 5),  # buffer
                "secid": "EMK.SOUTH",  # southbound composite
                "ut": "b2884a393a59ad64002292a3e90d46a5",
            },
            ttl_seconds=self._ttl_seconds,
        )
        if payload is None:
            logger.info("HK southbound fetch returned None")
            return None

        try:
            return self._parse(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("HK southbound parse failure: %s", exc)
            return None

    def _parse(self, payload: dict) -> HKSouthboundReading | None:
        """Extract southbound net buy from kline rows."""
        data = payload.get("data") or payload
        klines_raw = data.get("klines")
        if not klines_raw or not isinstance(klines_raw, list):
            logger.info("HK southbound payload missing 'klines'")
            return None

        # Each kline row: "date,buy,sell,net,..."  or comma-delimited fields.
        rows: list[float] = []
        for line in klines_raw:
            parts = str(line).split(",")
            if len(parts) < 4:
                continue
            try:
                # Field index 3 is the southbound net buy in wan-yuan.
                net_wan = float(parts[3])
                rows.append(net_wan)
            except (ValueError, TypeError):
                continue

        if not rows:
            logger.info("HK southbound: no parseable kline rows")
            return None

        # Take the last window_days rows.
        recent = rows[-self._window_days :]
        net_wan_total = sum(recent)
        # 1 HKD bn = 100,000 万  (1e5 万)
        net_hkd_bn = net_wan_total / 1e5

        return HKSouthboundReading(
            net_5d_hkd_bn=round(net_hkd_bn, 4),
            fetched_at=datetime.now(UTC),
        )

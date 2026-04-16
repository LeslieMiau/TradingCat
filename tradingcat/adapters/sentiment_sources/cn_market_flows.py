"""A-share (CN) market flows / turnover / margin balance fetchers.

Endpoints are on East Money's public data APIs — undocumented but widely used
by Chinese quant tools. All three methods return typed readings or ``None`` on
any error (HTTP, parse, shape, type). Upstream callers must treat ``None`` as
"source unavailable".

Turnover: cross-sectional median of top-N active stocks from the full A-share
list.  Northbound: 5-day net of HK→mainland Stock Connect flows.  Margin
balance: month-over-month change of the A-share 融资融券 aggregate balance.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from tradingcat.adapters.sentiment_http import SentimentHttpClient


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------- readings

@dataclass(frozen=True, slots=True)
class CNTurnoverReading:
    """Cross-sectional median turnover rate (%) of top-N A-share universe."""

    median_pct: float       # e.g. 2.3 → 2.3%
    sample_size: int        # how many stocks were averaged
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class CNNorthboundReading:
    """5-day net northbound flow (CNY billions, positive = inflow)."""

    net_5d_bn: float        # e.g. +12.3 or -8.5
    fetched_at: datetime


@dataclass(frozen=True, slots=True)
class CNMarginReading:
    """Month-over-month change in aggregate margin (融资融券) balance."""

    mom_pct: float          # e.g. +3.5 → +3.5% MoM
    fetched_at: datetime


# ---------------------------------------------------------------------- URLs

_CLIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
_NORTHBOUND_KLINE_URL = "https://push2.eastmoney.com/api/qt/kamt.kline/get"
_MARGIN_URL = "https://datacenter-web.eastmoney.com/api/data/v1/get"


class CNMarketFlowsClient:
    """Thin wrapper around East Money endpoints for A-share flow indicators.

    All ``fetch_*`` methods return their typed reading or ``None`` on error.
    They never raise.
    """

    def __init__(
        self,
        http: SentimentHttpClient,
        *,
        turnover_universe_size: int = 500,
        northbound_window_days: int = 5,
        ttl_seconds: int = 1800,          # 30min default
    ) -> None:
        self._http = http
        self._universe_size = int(turnover_universe_size)
        self._nb_window = int(northbound_window_days)
        self._ttl = int(ttl_seconds)

    # ------------------------------------------------------------------ turnover

    def fetch_turnover(self) -> CNTurnoverReading | None:
        """Fetch the cross-sectional median turnover rate from clist/get."""

        params = {
            "pn": "1",
            "pz": str(self._universe_size),
            "po": "1",                      # descending by turnover
            "np": "1",
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": "2",
            "invt": "2",
            "fid": "f3",                    # sort by turnover rate
            "fs": "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23",  # SH+SZ A-shares
            "fields": "f8",                 # f8 = turnover rate (%)
        }
        payload = self._http.get_json(
            _CLIST_URL,
            params=params,
            ttl_seconds=self._ttl,
        )
        if payload is None:
            return None
        try:
            data = payload.get("data") or {}
            diff = data.get("diff")
            if not isinstance(diff, (list, dict)):
                logger.info("CN turnover: missing 'diff' section")
                return None
            # diff can be a dict keyed by index or a list; normalise.
            rows = list(diff.values()) if isinstance(diff, dict) else diff
            rates: list[float] = []
            for row in rows:
                raw_rate = row.get("f8") if isinstance(row, dict) else None
                if raw_rate is not None and raw_rate != "-":
                    try:
                        rates.append(float(raw_rate))
                    except (TypeError, ValueError):
                        continue
            if not rates:
                logger.info("CN turnover: no parseable rates in %d rows", len(rows))
                return None
            rates.sort()
            n = len(rates)
            median = (rates[n // 2] + rates[(n - 1) // 2]) / 2.0
            return CNTurnoverReading(
                median_pct=round(median, 4),
                sample_size=n,
                fetched_at=datetime.now(UTC),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.warning("CN turnover parse failure: %s", exc)
            return None

    # ------------------------------------------------------------------ northbound

    def fetch_northbound(self) -> CNNorthboundReading | None:
        """Fetch the trailing N-day net of HK→mainland Stock Connect flows."""

        params = {
            "fields1": "f1,f2,f3,f7",
            "fields2": "f51,f52,f54,f56",   # date, north_buy, north_sell, net
            "klt": "101",                    # daily granularity
            "lmt": str(self._nb_window + 5),  # extra days for holidays
            "ut": "b733418eda1c6f6b8ff5e63e8bdf4e02",
        }
        payload = self._http.get_json(
            _NORTHBOUND_KLINE_URL,
            params=params,
            ttl_seconds=self._ttl,
        )
        if payload is None:
            return None
        try:
            data = payload.get("data") or {}
            # The payload nests north/south summaries under keys like "hk2sh", "hk2sz".
            # We need the combined northbound net.  Try "s2n" (south-to-north composite).
            klines = data.get("s2n") or data.get("hk2sh") or data.get("hk2sz")
            if not isinstance(klines, list):
                logger.info("CN northbound: missing kline data")
                return None
            net_values: list[float] = []
            for row in klines[-self._nb_window:]:
                if not isinstance(row, str):
                    continue
                parts = row.split(",")
                if len(parts) < 4:
                    continue
                try:
                    net_val = float(parts[3])  # f56 = net
                    net_values.append(net_val)
                except (ValueError, IndexError):
                    continue
            if not net_values:
                logger.info("CN northbound: no net values parsed")
                return None
            # Sum over the window. Values are in "wan yuan" (万元), convert to bn.
            net_wan = sum(net_values)
            net_bn = net_wan / 1e5  # 1bn = 10万 × 1万 = 1e5 万
            return CNNorthboundReading(
                net_5d_bn=round(net_bn, 4),
                fetched_at=datetime.now(UTC),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.warning("CN northbound parse failure: %s", exc)
            return None

    # ------------------------------------------------------------------ margin

    def fetch_margin_balance(self) -> CNMarginReading | None:
        """Fetch MoM change of the total 融资融券 balance from datacenter-web."""

        params = {
            "reportName": "RPT_RZRQ_LSHJ",
            "columns": "ALL",
            "source": "WEB",
            "sortColumns": "DIM_DATE",
            "sortTypes": "-1",
            "pageSize": "2",               # latest 2 rows to compute MoM
            "pageNumber": "1",
        }
        payload = self._http.get_json(
            _MARGIN_URL,
            params=params,
            ttl_seconds=self._ttl,
        )
        if payload is None:
            return None
        try:
            result = payload.get("result") or {}
            data = result.get("data")
            if not isinstance(data, list) or len(data) < 2:
                logger.info("CN margin: not enough rows (%s)", type(data))
                return None
            # data[0] = latest, data[1] = previous month.
            curr_balance = self._extract_margin_balance(data[0])
            prev_balance = self._extract_margin_balance(data[1])
            if curr_balance is None or prev_balance is None or prev_balance == 0:
                logger.info("CN margin: unparseable balances")
                return None
            mom_pct = ((curr_balance - prev_balance) / abs(prev_balance)) * 100.0
            return CNMarginReading(
                mom_pct=round(mom_pct, 4),
                fetched_at=datetime.now(UTC),
            )
        except (TypeError, ValueError, AttributeError) as exc:
            logger.warning("CN margin parse failure: %s", exc)
            return None

    @staticmethod
    def _extract_margin_balance(row: dict) -> float | None:
        """Pull the total margin balance from a RPT_RZRQ_LSHJ row."""

        # East Money uses "RZRQYE" (融资融券余额) or "RZYE" (融资余额) as the balance field.
        for key in ("RZRQYE", "RZYE", "rzrqye", "rzye"):
            raw = row.get(key)
            if raw is not None:
                try:
                    return float(raw)
                except (TypeError, ValueError):
                    continue
        return None

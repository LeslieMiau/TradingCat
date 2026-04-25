"""BaoStock-backed market data adapter for China A-share daily bars.

BaoStock (https://pypi.org/project/baostock/) is a free China market data SDK.
It requires an explicit ``login`` before querying and ``logout`` afterward.
This adapter keeps that lifecycle local to each request so the optional backend
does not leak global session state into the rest of TradingCat.

Scope of this adapter (Round 03):
- ``fetch_bars`` — daily K-line for CN 6-digit stock and ETF symbols.
- ``fetch_quotes`` / ``fetch_option_chain`` / ``fetch_corporate_actions`` /
  ``fetch_fx_rates`` — return empty values; factory integration and quote
  fallback are deferred to later rounds.

Routing is CN-only. Non-CN instruments, index labels, and malformed symbols
raise ``BaostockUnavailable`` so a later composite adapter can fallback cleanly.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, date, datetime
from typing import Any, Iterable

from tradingcat.domain.models import Bar, FxRate, Instrument, Market, OptionContract


logger = logging.getLogger(__name__)


try:  # BaoStock is an optional dependency.
    import baostock as _baostock  # type: ignore[import-not-found]

    BAOSTOCK_AVAILABLE = True
except Exception:  # pragma: no cover - env-dependent
    _baostock = None  # type: ignore[assignment]
    BAOSTOCK_AVAILABLE = False


class BaostockUnavailable(RuntimeError):
    """Raised when BaoStock cannot be used for the requested instrument."""


_DATE_FIELD = "date"
_OPEN_FIELD = "open"
_HIGH_FIELD = "high"
_LOW_FIELD = "low"
_CLOSE_FIELD = "close"
_VOLUME_FIELD = "volume"
_TRADE_STATUS_FIELD = "tradestatus"

_DAILY_FIELDS = ",".join(
    [
        _DATE_FIELD,
        "code",
        _OPEN_FIELD,
        _HIGH_FIELD,
        _LOW_FIELD,
        _CLOSE_FIELD,
        _VOLUME_FIELD,
        "amount",
        _TRADE_STATUS_FIELD,
    ]
)


def _normalise_baostock_symbol(instrument: Instrument) -> str:
    if instrument.market != Market.CN:
        raise BaostockUnavailable(
            f"BaoStock adapter only handles CN instruments, got {instrument.market}"
        )
    symbol = instrument.symbol.strip().upper()
    if symbol.startswith(("SH", "SZ")):
        raise BaostockUnavailable(
            f"BaoStock adapter does not handle CN index labels ({symbol}) in Round 03"
        )
    if not symbol.isdigit() or len(symbol) != 6:
        raise BaostockUnavailable(f"BaoStock expects 6-digit A-share symbols, got {symbol!r}")
    if symbol.startswith(("5", "6", "9")):
        return f"sh.{symbol}"
    return f"sz.{symbol}"


class BaostockMarketDataAdapter:
    """Market data adapter for A-share daily bars via BaoStock."""

    def __init__(
        self,
        *,
        adjustflag: str = "2",
        baostock_module: Any | None = None,
    ) -> None:
        module = baostock_module if baostock_module is not None else _baostock
        if module is None:
            raise BaostockUnavailable(
                "baostock is not installed. Install with: pip install 'tradingcat[sentiment_baostock]'"
            )
        self._bs = module
        self._adjustflag = adjustflag
        self._session_lock = threading.Lock()

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        symbol = _normalise_baostock_symbol(instrument)

        with self._session_lock:
            if not self._login():
                return []
            try:
                result = self._bs.query_history_k_data_plus(
                    symbol,
                    _DAILY_FIELDS,
                    start_date=start.isoformat(),
                    end_date=end.isoformat(),
                    frequency="d",
                    adjustflag=self._adjustflag,
                )
                if str(getattr(result, "error_code", "0")) != "0":
                    logger.warning(
                        "BaoStock query_history_k_data_plus failed for %s: %s",
                        symbol,
                        getattr(result, "error_msg", ""),
                    )
                    return []
                return list(_iter_bars_from_result(result, instrument))
            except Exception as exc:
                logger.warning("BaoStock fetch_bars failed for %s: %s", symbol, exc)
                return []
            finally:
                self._logout()

    def _login(self) -> bool:
        try:
            login_result = self._bs.login()
        except Exception as exc:
            logger.warning("BaoStock login failed: %s", exc)
            return False
        if str(getattr(login_result, "error_code", "0")) != "0":
            logger.warning("BaoStock login rejected: %s", getattr(login_result, "error_msg", ""))
            return False
        return True

    def _logout(self) -> None:
        try:
            self._bs.logout()
        except Exception as exc:
            logger.debug("BaoStock logout failed: %s", exc)

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        return {}

    def fetch_option_chain(
        self,
        underlying: str,
        as_of: date,
        *,
        market: Market | None = None,
    ) -> list[OptionContract]:
        return []

    def fetch_corporate_actions(
        self,
        instrument: Instrument,
        start: date,
        end: date,
    ) -> list[dict]:
        return []

    def fetch_fx_rates(
        self,
        base_currency: str,
        quote_currency: str,
        start: date,
        end: date,
    ) -> list[FxRate]:
        return []


def _iter_bars_from_result(result: Any, instrument: Instrument) -> Iterable[Bar]:
    fields = list(getattr(result, "fields", []))
    if not fields:
        return
    while result.next():
        row_values = result.get_row_data()
        row = dict(zip(fields, row_values, strict=False))
        if str(row.get(_TRADE_STATUS_FIELD, "1")) not in {"", "1"}:
            continue
        ts = _parse_date(row.get(_DATE_FIELD))
        if ts is None:
            continue
        try:
            yield Bar(
                instrument=instrument,
                timestamp=ts,
                open=float(row[_OPEN_FIELD]),
                high=float(row[_HIGH_FIELD]),
                low=float(row[_LOW_FIELD]),
                close=float(row[_CLOSE_FIELD]),
                volume=float(row.get(_VOLUME_FIELD, 0) or 0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed BaoStock row %r: %s", row, exc)
            continue


def _parse_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, date):
        return datetime.combine(raw, datetime.min.time(), tzinfo=UTC)
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"):
        try:
            return datetime.strptime(raw_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    logger.debug("Could not parse BaoStock date: %r", raw)
    return None

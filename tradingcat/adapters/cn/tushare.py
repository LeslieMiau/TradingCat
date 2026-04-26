"""Tushare-backed China A-share data adapter.

Tushare Pro requires a user token and exposes both market data and research
fundamental datasets. This adapter keeps it optional and disabled by default.

Scope of this adapter (Round 04):
- ``fetch_bars`` — daily A-share bars via ``ts.pro_bar``.
- ``fetch_daily_basic`` — research-only ``daily_basic`` rows.
- ``fetch_fina_indicator`` — research-only ``fina_indicator`` rows.
- Other market-data protocol methods return empty values.

The research helper methods intentionally return plain dictionaries. They do
not create orders, signals, approvals, or any trading-side effect.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime
from typing import Any, Iterable

from tradingcat.domain.models import Bar, FxRate, Instrument, Market, OptionContract


logger = logging.getLogger(__name__)


try:  # Tushare is an optional dependency.
    import tushare as _tushare  # type: ignore[import-not-found]

    TUSHARE_AVAILABLE = True
except Exception:  # pragma: no cover - env-dependent
    _tushare = None  # type: ignore[assignment]
    TUSHARE_AVAILABLE = False


class TushareUnavailable(RuntimeError):
    """Raised when Tushare cannot be used for the requested operation."""


_DATE_FIELD = "trade_date"
_OPEN_FIELD = "open"
_HIGH_FIELD = "high"
_LOW_FIELD = "low"
_CLOSE_FIELD = "close"
_VOLUME_FIELD = "vol"
_AMOUNT_FIELD = "amount"


def _normalise_ts_code(instrument: Instrument) -> str:
    if instrument.market != Market.CN:
        raise TushareUnavailable(
            f"Tushare adapter only handles CN instruments, got {instrument.market}"
        )
    symbol = instrument.symbol.strip().upper()
    if symbol.startswith(("SH", "SZ")):
        raise TushareUnavailable(
            f"Tushare adapter does not handle CN index labels ({symbol}) in Round 04"
        )
    if not symbol.isdigit() or len(symbol) != 6:
        raise TushareUnavailable(f"Tushare expects 6-digit A-share symbols, got {symbol!r}")
    if symbol.startswith(("5", "6", "9")):
        return f"{symbol}.SH"
    return f"{symbol}.SZ"


def _format_date(dt: date) -> str:
    return dt.strftime("%Y%m%d")


class TushareMarketDataAdapter:
    """Market data adapter for China A-share data via Tushare Pro."""

    def __init__(
        self,
        *,
        token: str | None,
        adj: str = "qfq",
        tushare_module: Any | None = None,
        pro_client: Any | None = None,
    ) -> None:
        self._token = (token or "").strip()
        if not self._token and pro_client is None:
            raise TushareUnavailable("Tushare token is required; set TRADINGCAT_TUSHARE_TOKEN")
        self._ts = tushare_module if tushare_module is not None else _tushare
        if self._ts is None and pro_client is None:
            raise TushareUnavailable(
                "tushare is not installed. Install with: pip install 'tradingcat[sentiment_tushare]'"
            )
        self._adj = adj
        self._pro = pro_client

    def _client(self):
        if self._pro is not None:
            return self._pro
        try:
            self._pro = self._ts.pro_api(self._token)
        except Exception as exc:
            raise TushareUnavailable(f"Tushare pro_api initialization failed: {exc}") from exc
        return self._pro

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        ts_code = _normalise_ts_code(instrument)
        try:
            df = self._ts.pro_bar(
                ts_code=ts_code,
                start_date=_format_date(start),
                end_date=_format_date(end),
                freq="D",
                asset="E",
                adj=self._adj or None,
                pro_api=self._client(),
            )
        except TushareUnavailable:
            raise
        except Exception as exc:
            logger.warning("Tushare pro_bar failed for %s: %s", ts_code, exc)
            return []
        if df is None or getattr(df, "empty", True):
            return []
        return sorted(_iter_bars_from_df(df, instrument), key=lambda bar: bar.timestamp)

    def fetch_daily_basic(self, instrument: Instrument, start: date, end: date) -> list[dict[str, Any]]:
        ts_code = _normalise_ts_code(instrument)
        try:
            df = self._client().daily_basic(
                ts_code=ts_code,
                start_date=_format_date(start),
                end_date=_format_date(end),
            )
        except Exception as exc:
            logger.warning("Tushare daily_basic failed for %s: %s", ts_code, exc)
            return []
        return list(_iter_dict_rows(df))

    def fetch_fina_indicator(self, instrument: Instrument, start: date, end: date) -> list[dict[str, Any]]:
        ts_code = _normalise_ts_code(instrument)
        try:
            df = self._client().fina_indicator(
                ts_code=ts_code,
                start_date=_format_date(start),
                end_date=_format_date(end),
            )
        except Exception as exc:
            logger.warning("Tushare fina_indicator failed for %s: %s", ts_code, exc)
            return []
        return list(_iter_dict_rows(df))

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


def _iter_dict_rows(df: Any) -> Iterable[dict[str, Any]]:
    if df is None or getattr(df, "empty", True):
        return
    to_dict = getattr(df, "to_dict", None)
    if to_dict is not None:
        try:
            records = to_dict(orient="records")
        except TypeError:
            records = None
        if records is not None:
            for row in records:
                if isinstance(row, dict):
                    yield row
            return

    iterrows = getattr(df, "iterrows", None)
    if iterrows is not None:
        for _, row in iterrows():
            yield dict(row)


def _iter_bars_from_df(df: Any, instrument: Instrument) -> Iterable[Bar]:
    for row in _iter_dict_rows(df):
        ts = _parse_trade_date(row.get(_DATE_FIELD))
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
            logger.debug("Skipping malformed Tushare row %r: %s", row, exc)
            continue


def _parse_trade_date(raw: Any) -> datetime | None:
    if raw is None:
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, date):
        return datetime.combine(raw, datetime.min.time(), tzinfo=UTC)
    raw_str = str(raw).strip()
    if not raw_str:
        return None
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(raw_str, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    logger.debug("Could not parse Tushare trade_date: %r", raw)
    return None

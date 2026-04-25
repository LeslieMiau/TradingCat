"""AKShare-backed market data adapter for A-share equities and ETFs.

AKShare (https://akshare.akfamily.xyz/) is a community-maintained Chinese
financial-data SDK. It is broader and more accurate for A-shares than yfinance,
which is currently the CN fallback in this repo. AKShare is an *optional*
dependency (declared as ``sentiment_akshare`` extras in ``pyproject.toml``); the
adapter degrades gracefully when the import fails.

Scope of this adapter (Round 01):
- ``fetch_bars`` — daily K-line for A-share stocks and ETFs, forward-adjusted.
- ``fetch_quotes`` — last close from the spot snapshot.
- ``fetch_option_chain`` / ``fetch_corporate_actions`` / ``fetch_fx_rates`` —
  stubbed to ``[]``; later rounds may wire ``stock_history_dividend_detail`` and
  ``stock_option_*``.

Routing is **CN-only**: passing a US/HK instrument raises
``AkshareUnavailable`` rather than silently returning empty data, so callers
must handle dispatch (the planned ``CompositeMarketDataAdapter`` in Round 02).

Symbol conventions (from TradingCat catalogue):
- Stocks: bare 6-digit code (e.g. ``600000``, ``300308``).
- ETFs: bare 6-digit code (e.g. ``510300``, ``159915``); dispatched via
  ``Instrument.asset_class == ETF`` to ``fund_etf_hist_em`` /
  ``fund_etf_spot_em``.
- Indices (e.g. ``SH000001``): not handled here; callers use yfinance.

AKShare's stock_zh_a_hist response uses Chinese column names; the constants
``_HIST_COLUMNS_CN`` document the expected schema and aid mocking in tests.
"""

from __future__ import annotations

import logging
import threading
from datetime import UTC, date, datetime, timedelta
from typing import Any, Iterable

from tradingcat.domain.models import (
    AssetClass,
    Bar,
    FxRate,
    Instrument,
    Market,
    OptionContract,
)


logger = logging.getLogger(__name__)


try:  # AKShare is an optional dependency.
    import akshare as _akshare  # type: ignore[import-not-found]

    AKSHARE_AVAILABLE = True
except Exception:  # pragma: no cover — env-dependent
    _akshare = None  # type: ignore[assignment]
    AKSHARE_AVAILABLE = False


class AkshareUnavailable(RuntimeError):
    """Raised when AKShare is not importable or asked to handle a non-CN symbol."""


# AKShare returns these Chinese column names for stock_zh_a_hist / fund_etf_hist_em.
_HIST_DATE_COL = "日期"
_HIST_OPEN_COL = "开盘"
_HIST_CLOSE_COL = "收盘"
_HIST_HIGH_COL = "最高"
_HIST_LOW_COL = "最低"
_HIST_VOLUME_COL = "成交量"


# stock_zh_a_spot_em returns these (subset, the ones we care about).
_SPOT_CODE_COL = "代码"
_SPOT_LAST_COL = "最新价"


def _normalise_cn_symbol(instrument: Instrument) -> str:
    """Validate and return the bare A-share symbol.

    AKShare's A-share endpoints take the bare 6-digit code (no exchange
    suffix). This rejects malformed or non-CN symbols so callers fail fast
    instead of issuing a wasted upstream request.
    """

    if instrument.market != Market.CN:
        raise AkshareUnavailable(
            f"AKShare adapter only handles CN instruments, got {instrument.market}"
        )
    symbol = instrument.symbol.strip().upper()
    # CN catalogue includes index labels like SH000001 / SZ399001; AKShare's
    # stock/ETF endpoints can't take those.
    if symbol.startswith(("SH", "SZ")):
        raise AkshareUnavailable(
            f"AKShare adapter does not handle CN index labels ({symbol}); "
            "use the index endpoint or a different adapter"
        )
    if not symbol.isdigit() or len(symbol) != 6:
        raise AkshareUnavailable(
            f"AKShare expects 6-digit A-share symbols, got {symbol!r}"
        )
    return symbol


def _format_date(dt: date) -> str:
    return dt.strftime("%Y%m%d")


class AkshareMarketDataAdapter:
    """Market data adapter for A-share equities and ETFs via AKShare.

    Args:
        adjust: Price adjustment. ``"qfq"`` (forward-adjust, default) is the
            usual choice for backtest consistency. Pass ``""`` for raw or
            ``"hfq"`` for back-adjust.
        akshare_module: Optional override, mainly for tests that want to inject
            a fake. Defaults to the imported ``akshare`` package.
        spot_cache_ttl_seconds: How long ``fetch_quotes`` caches the full
            ``stock_zh_a_spot_em`` snapshot. The endpoint returns thousands of
            rows; caching avoids one HTTP round-trip per quoted symbol.
    """

    def __init__(
        self,
        *,
        adjust: str = "qfq",
        akshare_module: Any | None = None,
        spot_cache_ttl_seconds: float = 30.0,
    ) -> None:
        module = akshare_module if akshare_module is not None else _akshare
        if module is None:
            raise AkshareUnavailable(
                "akshare is not installed. Install with: pip install 'tradingcat[sentiment_akshare]'"
            )
        self._ak = module
        self._adjust = adjust
        self._spot_cache_ttl = float(spot_cache_ttl_seconds)
        self._spot_cache: tuple[float, dict[str, float]] | None = None
        self._spot_cache_lock = threading.Lock()

    # ------------------------------------------------------------------ bars

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        symbol = _normalise_cn_symbol(instrument)
        start_str = _format_date(start)
        end_str = _format_date(end)

        try:
            if instrument.asset_class == AssetClass.ETF:
                df = self._ak.fund_etf_hist_em(
                    symbol=symbol,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust=self._adjust,
                )
            else:
                df = self._ak.stock_zh_a_hist(
                    symbol=symbol,
                    period="daily",
                    start_date=start_str,
                    end_date=end_str,
                    adjust=self._adjust,
                )
        except Exception as exc:  # AKShare raises bare exceptions on bad symbols.
            logger.warning(
                "AKShare fetch_bars failed for %s (%s): %s",
                symbol,
                instrument.asset_class,
                exc,
            )
            return []

        if df is None or getattr(df, "empty", True):
            return []
        return list(_iter_bars_from_df(df, instrument))

    # ------------------------------------------------------------------ quotes

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        if not instruments:
            return {}

        snapshot = self._get_spot_snapshot()
        quotes: dict[str, float] = {}
        for instrument in instruments:
            try:
                symbol = _normalise_cn_symbol(instrument)
            except AkshareUnavailable as exc:
                logger.debug("Skipping non-CN instrument in AKShare quotes: %s", exc)
                continue
            price = snapshot.get(symbol)
            if price is None:
                logger.info("AKShare snapshot missing price for %s", symbol)
                continue
            quotes[instrument.symbol] = price
        return quotes

    def _get_spot_snapshot(self) -> dict[str, float]:
        """Return ``{symbol: last_price}`` for all A-shares, refreshed lazily.

        The snapshot is cached for ``self._spot_cache_ttl`` seconds because
        ``stock_zh_a_spot_em`` returns the entire A-share board (~5k rows).
        """

        import time

        now = time.monotonic()
        with self._spot_cache_lock:
            if self._spot_cache is not None:
                cached_at, cached = self._spot_cache
                if now - cached_at < self._spot_cache_ttl:
                    return cached

            try:
                df = self._ak.stock_zh_a_spot_em()
            except Exception as exc:
                logger.warning("AKShare stock_zh_a_spot_em failed: %s", exc)
                return self._spot_cache[1] if self._spot_cache is not None else {}

            snapshot: dict[str, float] = {}
            if df is not None and not getattr(df, "empty", True):
                for row in _iter_dict_rows(df):
                    code = str(row.get(_SPOT_CODE_COL, "")).strip()
                    last = row.get(_SPOT_LAST_COL)
                    if not code or last is None:
                        continue
                    try:
                        snapshot[code] = float(last)
                    except (TypeError, ValueError):
                        continue
            self._spot_cache = (now, snapshot)
            return snapshot

    # ------------------------------------------------------------------ stubs

    def fetch_option_chain(
        self,
        underlying: str,
        as_of: date,
        *,
        market: Market | None = None,
    ) -> list[OptionContract]:
        # AKShare exposes A-share option chains via stock_option_um_*; defer
        # to a later round to keep this adapter scoped.
        return []

    def fetch_corporate_actions(
        self,
        instrument: Instrument,
        start: date,
        end: date,
    ) -> list[dict]:
        # ak.stock_history_dividend_detail can populate this; deferred.
        return []

    def fetch_fx_rates(
        self,
        base_currency: str,
        quote_currency: str,
        start: date,
        end: date,
    ) -> list[FxRate]:
        return []


# ---------------------------------------------------------------------- helpers


def _iter_dict_rows(df: Any) -> Iterable[dict]:
    """Iterate over a pandas-like DataFrame as plain dicts.

    Pandas is not a hard dependency of this module; the AKShare DataFrame
    typically supports ``.to_dict(orient="records")`` and ``.iterrows()``.
    """

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
        ts = _parse_hist_timestamp(row.get(_HIST_DATE_COL))
        if ts is None:
            continue
        try:
            yield Bar(
                instrument=instrument,
                timestamp=ts,
                open=float(row[_HIST_OPEN_COL]),
                high=float(row[_HIST_HIGH_COL]),
                low=float(row[_HIST_LOW_COL]),
                close=float(row[_HIST_CLOSE_COL]),
                volume=float(row.get(_HIST_VOLUME_COL, 0) or 0),
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.debug("Skipping malformed AKShare row %r: %s", row, exc)
            continue


def _parse_hist_timestamp(raw: Any) -> datetime | None:
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
            parsed = datetime.strptime(raw_str, fmt)
        except ValueError:
            continue
        return parsed.replace(tzinfo=UTC)
    # Pandas Timestamp objects have to_pydatetime; some AKShare endpoints emit them.
    to_py = getattr(raw, "to_pydatetime", None)
    if to_py is not None:
        try:
            converted = to_py()
            if isinstance(converted, datetime):
                return converted if converted.tzinfo else converted.replace(tzinfo=UTC)
        except Exception:
            pass
    logger.debug("Could not parse AKShare hist date: %r", raw)
    return None

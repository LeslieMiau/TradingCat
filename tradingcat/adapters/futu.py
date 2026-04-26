from __future__ import annotations

import logging
import time
from datetime import UTC, date, datetime
from typing import Any

logger = logging.getLogger(__name__)

from tradingcat.config import FutuConfig
from tradingcat.domain.models import (
    AssetClass,
    Bar,
    ExecutionReport,
    FxRate,
    Instrument,
    Market,
    OptionContract,
    OrderIntent,
    OrderSide,
    OrderStatus,
    Position,
)


class FutuAdapterUnavailable(RuntimeError):
    pass


def _load_futu_sdk() -> Any:
    try:
        import futu as ft
    except ImportError as exc:
        raise FutuAdapterUnavailable("futu SDK is not installed") from exc
    except Exception as exc:
        logger.exception("futu SDK initialization failed")
        raise FutuAdapterUnavailable(f"futu SDK could not initialize: {exc}") from exc
    return ft


def _normalize_code(instrument: Instrument) -> str:
    symbol = instrument.symbol
    if instrument.market == Market.CN and symbol in {"SH000001", "SZ399001", "SZ399006"}:
        exchange = "SH" if symbol.startswith("SH") else "SZ"
        return f"{exchange}.{symbol[-6:]}"
    if instrument.market == Market.HK and symbol.isdigit():
        symbol = symbol.zfill(5)
    if instrument.market == Market.CN:
        exchange = "SH" if symbol.startswith(("5", "6", "9")) else "SZ"
        return f"{exchange}.{symbol}"
    return f"{instrument.market.value}.{symbol}"


def _market_from_code(code: str) -> Market:
    market_prefix = code.split(".", 1)[0]
    if market_prefix in {"SH", "SZ"}:
        return Market.CN
    return Market(market_prefix)


def _first_value(row: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        value = row.get(key)
        if value is not None and value != "":
            return value
    return default


def _parse_date(raw: Any) -> date | None:
    if raw in (None, ""):
        return None
    raw_str = str(raw)
    for separator in ("T", " "):
        if separator in raw_str:
            raw_str = raw_str.split(separator, 1)[0]
    return date.fromisoformat(raw_str)


def _asset_class_from_symbol(symbol: str) -> AssetClass:
    upper_symbol = symbol.upper()
    if upper_symbol.endswith(("ETF",)):
        return AssetClass.ETF
    if symbol.isdigit():
        return AssetClass.ETF if len(symbol) >= 6 else AssetClass.STOCK
    return AssetClass.STOCK


def _map_order_status(raw_status: Any) -> OrderStatus:
    status = str(raw_status or "").upper()
    if "CANCEL" in status:
        return OrderStatus.CANCELLED
    if "FAIL" in status or "REJECT" in status:
        return OrderStatus.REJECTED
    if "FILLED" in status or status.endswith("_ALL"):
        return OrderStatus.FILLED
    return OrderStatus.SUBMITTED


def _wait_for_session(ctx, ft_module, *, timeout: float = 10.0, interval: float = 0.5) -> None:
    """Block until the Futu context session is ready or timeout is reached."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if hasattr(ctx, "get_global_state"):
            ret, data = ctx.get_global_state()
            if ret == ft_module.RET_OK:
                return
        else:
            return
        time.sleep(interval)
    logger.error("Futu session not ready before timeout")
    raise FutuAdapterUnavailable(
        f"Futu session not ready after {timeout}s — is OpenD running on {getattr(ctx, '_host', '?')}?"
    )


class FutuMarketDataAdapter:
    def __init__(self, config: FutuConfig) -> None:
        self._config = config
        self._ft = _load_futu_sdk()
        self._quote_ctx = self._ft.OpenQuoteContext(host=config.host, port=config.port)
        _wait_for_session(self._quote_ctx, self._ft)

    def close(self) -> None:
        self._quote_ctx.close()

    def health_check(self) -> dict[str, object]:
        if hasattr(self._quote_ctx, "get_global_state"):
            ret, data = self._quote_ctx.get_global_state()
            if ret != self._ft.RET_OK:
                return {"healthy": False, "detail": f"Quote context unhealthy: {data}"}
            return {"healthy": True, "detail": "Quote context connected"}
        return {"healthy": True, "detail": "Quote context initialized"}

    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]:
        ret, data, _ = self._quote_ctx.request_history_kline(
            code=_normalize_code(instrument),
            start=start.isoformat(),
            end=end.isoformat(),
            max_count=None,
        )
        if ret != self._ft.RET_OK:
            raise RuntimeError(f"Futu kline request failed: {data}")
        bars: list[Bar] = []
        for row in data.to_dict("records"):
            bars.append(
                Bar(
                    instrument=instrument,
                    timestamp=datetime.fromisoformat(row["time_key"]).replace(tzinfo=UTC),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
            )
        return bars

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]:
        codes = [_normalize_code(instrument) for instrument in instruments]
        ret, data = self._quote_ctx.get_market_snapshot(codes)
        if ret != self._ft.RET_OK:
            raise RuntimeError(f"Futu quote snapshot failed: {data}")
        snapshots = data.to_dict("records")
        if len(codes) != len(snapshots):
            logger.warning(
                "Futu snapshot count mismatch: requested %d codes, got %d rows",
                len(codes), len(snapshots),
            )
        return {
            code.split(".", 1)[1]: float(row["last_price"])
            for code, row in zip(codes, snapshots)
        }

    def fetch_option_chain(self, underlying: str, as_of: date, *, market: Market | None = None) -> list[OptionContract]:
        if market is None:
            market = Market.US if underlying.isalpha() else Market.HK
            logger.debug("Inferred market=%s for option chain underlying=%s", market.value, underlying)
        sym = underlying.zfill(5) if market == Market.HK else underlying
        code = f"{market.value}.{sym}"
        ret, data = self._quote_ctx.get_option_chain(code=code, start=as_of.isoformat(), end=as_of.isoformat())
        if ret != self._ft.RET_OK:
            raise RuntimeError(f"Futu option chain request failed: {data}")
        contracts: list[OptionContract] = []
        for row in data.to_dict("records"):
            strike = _first_value(row, "strike_price", "strike", default=0.0)
            expiry = _parse_date(_first_value(row, "expiry_date", "expiration_date", "expiry"))
            if expiry is None:
                continue
            contracts.append(
                OptionContract(
                    symbol=str(row["code"]),
                    underlying=underlying,
                    strike=float(strike),
                    expiry=expiry,
                    option_type="call" if str(_first_value(row, "option_type", default="CALL")).upper().startswith("C") else "put",
                    market=_market_from_code(str(row["code"])),
                    currency="USD" if market == Market.US else "HKD",
                )
            )
        return contracts

    def fetch_corporate_actions(self, instrument: Instrument, start: date, end: date) -> list[dict]:
        ret, data = self._quote_ctx.get_rehab(code=_normalize_code(instrument))
        if ret != self._ft.RET_OK:
            raise RuntimeError(f"Futu rehab request failed: {data}")
        actions = []
        for row in data.to_dict("records"):
            row_date = _parse_date(_first_value(row, "ex_div_date", "record_date", "effective_date"))
            if row_date is None:
                logger.debug("Skipping corporate action record with no parseable date: %s", row)
                continue
            if start <= row_date <= end:
                actions.append(row)
        return actions

    def fetch_fx_rates(self, base_currency: str, quote_currency: str, start: date, end: date) -> list[FxRate]:
        # Futu OpenD does not support forex quote codes (Forex.USDCNH etc.)
        # FX rates should be fetched via a dedicated FX data source.
        return []


class FutuBrokerAdapter:
    def __init__(self, config: FutuConfig) -> None:
        self._config = config
        self._ft = _load_futu_sdk()
        self._contexts: dict[Market, object] = {}
        for market, config_attr in [
            (Market.HK, config.hk_trade_market),
            (Market.US, config.us_trade_market),
            (Market.CN, config.cn_trade_market),
        ]:
            trd_market = getattr(self._ft.TrdMarket, config_attr, None)
            if trd_market is None:
                logger.warning("Futu SDK does not support TrdMarket.%s, skipping %s context", config_attr, market.value)
                continue
            self._contexts[market] = self._ft.OpenSecTradeContext(
                filter_trdmarket=trd_market, host=config.host, port=config.port,
            )
        for ctx in self._contexts.values():
            _wait_for_session(ctx, self._ft)
        if config.unlock_trade_password:
            self._unlock_all()

    def _unlock_all(self) -> None:
        for context in self._contexts.values():
            ret, data = context.unlock_trade(self._config.unlock_trade_password)
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu trade unlock failed: {data}")

    def close(self) -> None:
        for context in self._contexts.values():
            context.close()

    def health_check(self) -> dict[str, object]:
        try:
            context = next(iter(self._contexts.values()))
        except StopIteration:
            return {"healthy": False, "detail": "No trade contexts initialized"}
        ret, data = context.accinfo_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
        if ret != self._ft.RET_OK:
            return {"healthy": False, "detail": f"Trade context unhealthy: {data}"}
        return {"healthy": True, "detail": "Trade context connected"}

    def _context_for(self, market: Market):
        if market not in self._contexts:
            raise RuntimeError(f"Futu live broker does not support market {market.value} in V1")
        return self._contexts[market]

    def place_order(self, intent: OrderIntent) -> ExecutionReport:
        context = self._context_for(intent.instrument.market)
        order_type = self._ft.OrderType.NORMAL if intent.order_type == "limit" else self._ft.OrderType.MARKET
        trd_side = self._ft.TrdSide.BUY if intent.side == OrderSide.BUY else self._ft.TrdSide.SELL
        price = intent.limit_price or 0.0
        ret, data = context.place_order(
            price=price,
            qty=intent.quantity,
            code=_normalize_code(intent.instrument),
            trd_side=trd_side,
            order_type=order_type,
            trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()),
        )
        if ret != self._ft.RET_OK:
            raise RuntimeError(f"Futu place_order failed: {data}")
        record = data.to_dict("records")[0]
        return ExecutionReport(
            order_intent_id=intent.id,
            broker_order_id=str(record["order_id"]),
            status=OrderStatus.SUBMITTED,
            average_price=float(record.get("price", price)) if record.get("price") is not None else None,
            message="Accepted by Futu broker",
        )

    def cancel_order(self, broker_order_id: str) -> ExecutionReport:
        for market, context in self._contexts.items():
            ret, data = context.modify_order(
                modify_order_op=self._ft.ModifyOrderOp.CANCEL,
                order_id=broker_order_id,
                qty=0,
                price=0,
                trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()),
            )
            if ret == self._ft.RET_OK:
                return ExecutionReport(
                    order_intent_id=str(broker_order_id),
                    broker_order_id=str(broker_order_id),
                    status=OrderStatus.CANCELLED,
                    message=f"Cancelled via Futu {market.value} trade context",
                )
            message = str(data)
            if "order not found" in message.lower() or "not exist" in message.lower():
                continue
            raise RuntimeError(f"Futu cancel_order failed: {data}")
        raise RuntimeError(f"Futu cancel_order could not find order {broker_order_id} in any configured trade context")

    def get_orders(self) -> list[ExecutionReport]:
        reports: list[ExecutionReport] = []
        for context in self._contexts.values():
            ret, data = context.order_list_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu order query failed: {data}")
            for row in data.to_dict("records"):
                reports.append(
                    ExecutionReport(
                        order_intent_id=str(row["order_id"]),
                        broker_order_id=str(row["order_id"]),
                        status=_map_order_status(row.get("order_status")),
                        filled_quantity=float(row.get("dealt_qty", 0.0)),
                        average_price=float(row["price"]) if row.get("price") is not None else None,
                        message=str(row.get("order_status", "")),
                    )
                )
        return reports

    def get_positions(self) -> list[Position]:
        positions: list[Position] = []
        for market, context in self._contexts.items():
            ret, data = context.position_list_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu position query failed: {data}")
            for row in data.to_dict("records"):
                symbol = str(row["code"]).split(".", 1)[1]
                positions.append(
                    Position(
                        instrument=Instrument(
                            symbol=symbol,
                            market=market,
                            asset_class=_asset_class_from_symbol(symbol),
                            currency={"US": "USD", "HK": "HKD", "CN": "CNY"}.get(market.value, "CNY"),
                        ),
                        quantity=float(row["qty"]),
                        market_value=float(row.get("market_val", 0.0)),
                        weight=0.0,
                    )
                )
        return positions

    def get_cash(self) -> float:
        total_cash = 0.0
        for context in self._contexts.values():
            ret, data = context.accinfo_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu account info query failed: {data}")
            record = data.to_dict("records")[0]
            total_cash += float(record.get("cash", 0.0))
        return total_cash

    def get_cash_by_market(self) -> dict[Market, float]:
        balances: dict[Market, float] = {}
        for market, context in self._contexts.items():
            ret, data = context.accinfo_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu account info query failed: {data}")
            record = data.to_dict("records")[0]
            balances[market] = float(record.get("cash", 0.0))
        return balances

    def reconcile_fills(self) -> list[ExecutionReport]:
        reports: list[ExecutionReport] = []
        for context in self._contexts.values():
            ret, data = context.deal_list_query(trd_env=getattr(self._ft.TrdEnv, self._config.environment.upper()))
            if ret != self._ft.RET_OK:
                raise RuntimeError(f"Futu deal query failed: {data}")
            for row in data.to_dict("records"):
                deal_id = row.get("deal_id") or row.get("trd_id")
                reports.append(
                    ExecutionReport(
                        order_intent_id=str(row["order_id"]),
                        broker_order_id=str(row["order_id"]),
                        fill_id=str(deal_id) if deal_id is not None else "",
                        status=OrderStatus.FILLED,
                        filled_quantity=float(row.get("qty", 0.0)),
                        average_price=float(row.get("price", 0.0)),
                        message="Reconciled from Futu deal list",
                    )
                )
        return reports

    def probe(self) -> dict:
        orders = self.get_orders()
        positions = self.get_positions()
        cash = self.get_cash()
        return {
            "status": "ok",
            "detail": "Futu broker probe completed",
            "cash": cash,
            "positions": len(positions),
            "orders": len(orders),
        }

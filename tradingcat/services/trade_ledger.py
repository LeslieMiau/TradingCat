"""Trade ledger export service.

Stage B deliverable: defines the schema used for year-end tax/audit reporting
and derives ledger rows from the execution orders + intent metadata already
persisted by :mod:`tradingcat.services.execution`.

Fee / tax schedules (2026-Q2 reference rates — update when regulators revise):

* **HK**: stamp duty 0.13% (both sides), trading fee 0.0000565 (SFC + FRC + AFRC),
  exchange fee 0.00565%, settlement fee not modelled (0.002% min HKD 2).
  No capital gains tax on equity trades.
* **US**: SEC Section 31 fee 0.00278% on sell notional, FINRA TAF USD 0.000166/share
  on sell (capped USD 8.30/trade). No stamp duty. Dividend withholding 30% is a
  *dividend ledger* concern, not a trade-ledger concern — column reserved.
* **CN** (A-share, advisory-only in V1): seller stamp duty 0.05% (after 2023-08-28
  halving), transfer fee 0.001% (both sides), commission min CNY 5 or 0.02%.
* **Other markets**: zero fees until schedules are added.

The service is *pure* in the sense that it consumes already-persisted
execution state — no broker calls, no side effects. Export rendering
(JSON / CSV) lives in the route layer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Iterable

from tradingcat.domain.models import (
    AssetClass,
    ExecutionReport,
    Market,
    OrderSide,
    OrderStatus,
    TradeLedgerEntry,
)


UTC = timezone.utc

FEE_SCHEDULE_VERSION = "v1-2026Q2"


@dataclass(frozen=True)
class FeeSchedule:
    """Per-market fee/tax rates applied to a single fill."""

    stamp_duty_buy: float = 0.0
    stamp_duty_sell: float = 0.0
    transfer_fee_rate: float = 0.0
    exchange_fee_rate: float = 0.0
    regulatory_fee_rate_sell: float = 0.0
    commission_rate: float = 0.0
    commission_min: float = 0.0
    per_share_fee: float = 0.0
    per_share_fee_cap: float | None = None
    regulatory_notes: tuple[str, ...] = ()


FEE_SCHEDULES: dict[Market, FeeSchedule] = {
    Market.HK: FeeSchedule(
        stamp_duty_buy=0.0013,
        stamp_duty_sell=0.0013,
        transfer_fee_rate=0.00002,
        exchange_fee_rate=0.0000565,
        regulatory_fee_rate_sell=0.0000027,
        commission_rate=0.0003,
        commission_min=3.0,
        regulatory_notes=("HK: stamp duty both sides; no capital gains tax.",),
    ),
    Market.US: FeeSchedule(
        regulatory_fee_rate_sell=0.0000278,
        commission_rate=0.0,
        commission_min=0.99,
        per_share_fee=0.0049,
        per_share_fee_cap=8.30,
        regulatory_notes=(
            "US: SEC fee on sell only; dividend withholding 30% tracked in dividend ledger.",
        ),
    ),
    Market.CN: FeeSchedule(
        stamp_duty_sell=0.0005,
        transfer_fee_rate=0.00001,
        commission_rate=0.0002,
        commission_min=5.0,
        regulatory_notes=(
            "CN: 0.05% seller stamp duty (2023-08-28 halving); advisory-only in V1.",
        ),
    ),
}


class TradeLedgerService:
    """Derive :class:`TradeLedgerEntry` rows from execution state."""

    def __init__(
        self,
        *,
        list_orders,
        resolve_intent_context,
        resolve_price_context,
        resolve_authorization_context=None,
    ) -> None:
        self._list_orders = list_orders
        self._resolve_intent = resolve_intent_context
        self._resolve_price = resolve_price_context
        self._resolve_auth = resolve_authorization_context

    def build_entries(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        market: Market | None = None,
    ) -> list[TradeLedgerEntry]:
        entries: list[TradeLedgerEntry] = []
        for report in self._list_orders():
            entry = self._entry_for_report(report)
            if entry is None:
                continue
            if market is not None and entry.market != market:
                continue
            if start is not None and entry.trade_date < start:
                continue
            if end is not None and entry.trade_date > end:
                continue
            entries.append(entry)
        entries.sort(key=lambda row: (row.trade_datetime, row.order_intent_id))
        return entries

    def summary(self, entries: Iterable[TradeLedgerEntry]) -> dict[str, object]:
        rows = list(entries)
        by_market: dict[str, dict[str, float]] = {}
        total_gross = 0.0
        total_fees = 0.0
        for row in rows:
            bucket = by_market.setdefault(
                row.market.value,
                {
                    "row_count": 0,
                    "gross_amount": 0.0,
                    "fees": 0.0,
                    "stamp_duty": 0.0,
                    "commission": 0.0,
                    "regulatory_fee": 0.0,
                    "withholding_tax": 0.0,
                },
            )
            fees = (
                row.commission
                + row.stamp_duty
                + row.transfer_fee
                + row.exchange_fee
                + row.regulatory_fee
                + row.other_fees
            )
            bucket["row_count"] = int(bucket["row_count"]) + 1
            bucket["gross_amount"] = round(bucket["gross_amount"] + row.gross_amount, 4)
            bucket["fees"] = round(bucket["fees"] + fees, 4)
            bucket["stamp_duty"] = round(bucket["stamp_duty"] + row.stamp_duty, 4)
            bucket["commission"] = round(bucket["commission"] + row.commission, 4)
            bucket["regulatory_fee"] = round(bucket["regulatory_fee"] + row.regulatory_fee, 4)
            bucket["withholding_tax"] = round(bucket["withholding_tax"] + row.withholding_tax, 4)
            total_gross += row.gross_amount
            total_fees += fees
        return {
            "row_count": len(rows),
            "gross_amount": round(total_gross, 4),
            "total_fees": round(total_fees, 4),
            "fee_schedule_version": FEE_SCHEDULE_VERSION,
            "by_market": by_market,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _entry_for_report(self, report: ExecutionReport) -> TradeLedgerEntry | None:
        if report.status != OrderStatus.FILLED or report.filled_quantity <= 0 or report.average_price is None:
            return None
        intent_context = self._resolve_intent(report.order_intent_id) or {}
        price_context = self._resolve_price(report.order_intent_id) if self._resolve_price else {}
        auth_context = self._resolve_auth(report.order_intent_id) if self._resolve_auth else {}

        symbol = str(intent_context.get("symbol") or "")
        market = self._coerce_market(intent_context.get("market") or report.market)
        asset_class = self._coerce_asset_class(intent_context.get("asset_class"))
        side = self._coerce_side(intent_context.get("side"))
        currency = str(intent_context.get("currency") or self._default_currency(market))
        strategy_id = str(intent_context.get("strategy_id") or "unknown")
        fill_source = self._fill_source(auth_context)

        quantity = float(report.filled_quantity)
        price = float(report.average_price)
        gross_amount = round(quantity * price, 6)

        schedule = FEE_SCHEDULES.get(market, FeeSchedule())
        commission = self._commission(schedule, quantity, gross_amount)
        stamp_duty = self._stamp_duty(schedule, side, gross_amount)
        transfer_fee = round(gross_amount * schedule.transfer_fee_rate, 6)
        exchange_fee = round(gross_amount * schedule.exchange_fee_rate, 6)
        regulatory_fee = self._regulatory_fee(schedule, side, gross_amount)

        fees = commission + stamp_duty + transfer_fee + exchange_fee + regulatory_fee
        signed_sign = -1.0 if side == OrderSide.BUY else 1.0
        net_amount = round(signed_sign * gross_amount - fees, 6)

        slippage_bps: float | None = None
        if report.slippage is not None:
            slippage_bps = round(float(report.slippage) * 10_000.0, 4)

        trade_dt = report.timestamp if isinstance(report.timestamp, datetime) else datetime.now(UTC)
        if trade_dt.tzinfo is None:
            trade_dt = trade_dt.replace(tzinfo=UTC)

        notes = list(schedule.regulatory_notes)
        if market == Market.CN:
            notes.append("A-share trades are advisory-only in V1; verify broker invoice before filing.")

        return TradeLedgerEntry(
            order_intent_id=report.order_intent_id,
            broker_order_id=report.broker_order_id,
            fill_id=report.fill_id,
            trade_date=trade_dt.date(),
            trade_datetime=trade_dt,
            symbol=symbol,
            market=market,
            asset_class=asset_class,
            side=side,
            currency=currency,
            quantity=quantity,
            price=price,
            gross_amount=gross_amount,
            commission=round(commission, 6),
            stamp_duty=round(stamp_duty, 6),
            transfer_fee=transfer_fee,
            exchange_fee=exchange_fee,
            regulatory_fee=round(regulatory_fee, 6),
            net_amount=net_amount,
            realized_slippage_bps=slippage_bps,
            strategy_id=strategy_id,
            fill_source=fill_source,
            fee_schedule_version=FEE_SCHEDULE_VERSION,
            reporting_notes=notes,
        )

    @staticmethod
    def _coerce_market(raw: object) -> Market:
        if isinstance(raw, Market):
            return raw
        if isinstance(raw, str):
            try:
                return Market(raw)
            except ValueError:
                return Market.US
        return Market.US

    @staticmethod
    def _coerce_asset_class(raw: object) -> AssetClass:
        if isinstance(raw, AssetClass):
            return raw
        if isinstance(raw, str):
            try:
                return AssetClass(raw)
            except ValueError:
                return AssetClass.STOCK
        return AssetClass.STOCK

    @staticmethod
    def _coerce_side(raw: object) -> OrderSide:
        if isinstance(raw, OrderSide):
            return raw
        if isinstance(raw, str):
            try:
                return OrderSide(raw)
            except ValueError:
                return OrderSide.BUY
        return OrderSide.BUY

    @staticmethod
    def _default_currency(market: Market) -> str:
        return {Market.US: "USD", Market.HK: "HKD", Market.CN: "CNY"}.get(market, "USD")

    @staticmethod
    def _commission(schedule: FeeSchedule, quantity: float, gross: float) -> float:
        rate_component = gross * schedule.commission_rate
        per_share = quantity * schedule.per_share_fee
        if schedule.per_share_fee_cap is not None:
            per_share = min(per_share, schedule.per_share_fee_cap)
        total = rate_component + per_share
        return max(total, schedule.commission_min) if gross > 0 else 0.0

    @staticmethod
    def _stamp_duty(schedule: FeeSchedule, side: OrderSide, gross: float) -> float:
        rate = schedule.stamp_duty_buy if side == OrderSide.BUY else schedule.stamp_duty_sell
        return gross * rate

    @staticmethod
    def _regulatory_fee(schedule: FeeSchedule, side: OrderSide, gross: float) -> float:
        if side != OrderSide.SELL:
            return 0.0
        return gross * schedule.regulatory_fee_rate_sell

    @staticmethod
    def _fill_source(auth_context: dict[str, object] | None) -> str:
        if not auth_context:
            return "live"
        mode = str(auth_context.get("final_authorization_mode") or auth_context.get("authorization_mode") or "")
        if "manual" in mode:
            return "manual"
        return "live"


CSV_COLUMNS = [
    "trade_date",
    "trade_datetime",
    "market",
    "symbol",
    "asset_class",
    "side",
    "currency",
    "quantity",
    "price",
    "gross_amount",
    "commission",
    "stamp_duty",
    "transfer_fee",
    "exchange_fee",
    "regulatory_fee",
    "other_fees",
    "net_amount",
    "withholding_tax",
    "realized_slippage_bps",
    "strategy_id",
    "fill_source",
    "order_intent_id",
    "broker_order_id",
    "fill_id",
    "fee_schedule_version",
]


def render_csv(entries: Iterable[TradeLedgerEntry]) -> str:
    import csv
    import io

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for entry in entries:
        writer.writerow(
            [
                entry.trade_date.isoformat(),
                entry.trade_datetime.isoformat(),
                entry.market.value,
                entry.symbol,
                entry.asset_class.value,
                entry.side.value,
                entry.currency,
                f"{entry.quantity}",
                f"{entry.price}",
                f"{entry.gross_amount}",
                f"{entry.commission}",
                f"{entry.stamp_duty}",
                f"{entry.transfer_fee}",
                f"{entry.exchange_fee}",
                f"{entry.regulatory_fee}",
                f"{entry.other_fees}",
                f"{entry.net_amount}",
                f"{entry.withholding_tax}",
                "" if entry.realized_slippage_bps is None else f"{entry.realized_slippage_bps}",
                entry.strategy_id,
                entry.fill_source,
                entry.order_intent_id,
                entry.broker_order_id,
                entry.fill_id,
                entry.fee_schedule_version,
            ]
        )
    return buffer.getvalue()


__all__ = [
    "FEE_SCHEDULE_VERSION",
    "FEE_SCHEDULES",
    "FeeSchedule",
    "TradeLedgerService",
    "CSV_COLUMNS",
    "render_csv",
]

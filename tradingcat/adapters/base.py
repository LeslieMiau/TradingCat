from __future__ import annotations

from datetime import date
from typing import Protocol

from tradingcat.domain.models import (
    Bar,
    ExecutionReport,
    Instrument,
    Market,
    OptionContract,
    OrderIntent,
    Position,
)


class MarketDataAdapter(Protocol):
    def fetch_bars(self, instrument: Instrument, start: date, end: date) -> list[Bar]: ...

    def fetch_quotes(self, instruments: list[Instrument]) -> dict[str, float]: ...

    def fetch_option_chain(self, underlying: str, as_of: date, *, market: Market | None = None) -> list[OptionContract]: ...

    def fetch_corporate_actions(self, instrument: Instrument, start: date, end: date) -> list[dict]: ...


class BrokerAdapter(Protocol):
    def place_order(self, intent: OrderIntent) -> ExecutionReport: ...

    def cancel_order(self, broker_order_id: str) -> ExecutionReport: ...

    def get_orders(self) -> list[ExecutionReport]: ...

    def get_positions(self) -> list[Position]: ...

    def get_cash(self) -> float: ...

    def get_cash_by_market(self) -> dict[Market, float]: ...

    def reconcile_fills(self) -> list[ExecutionReport]: ...

    def probe(self) -> dict: ...

    def health_check(self) -> dict[str, object]: ...

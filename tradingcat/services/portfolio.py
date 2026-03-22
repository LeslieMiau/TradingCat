from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.adapters.base import BrokerAdapter
from tradingcat.config import AppConfig
from tradingcat.domain.models import Instrument, OrderSide, PortfolioReconciliationSummary, PortfolioSnapshot, Position
from tradingcat.repositories.state import PortfolioHistoryRepository, PortfolioRepository


class PortfolioService:
    def __init__(self, config: AppConfig, repository: PortfolioRepository, history_repository: PortfolioHistoryRepository) -> None:
        self._config = config
        self._repository = repository
        self._history_repository = history_repository
        self._history = history_repository.load()
        snapshot = repository.load()
        if snapshot is None:
            self._positions = []
            self._cash = config.portfolio_value
            self._drawdown = 0.0
            self._daily_pnl = 0.0
            self._weekly_pnl = 0.0
        else:
            self._positions = snapshot.positions
            self._cash = snapshot.cash
            self._drawdown = snapshot.drawdown
            self._daily_pnl = snapshot.daily_pnl
            self._weekly_pnl = snapshot.weekly_pnl

    def current_snapshot(self) -> PortfolioSnapshot:
        """Return an in-memory snapshot without persisting (safe for GET)."""
        nav = self._cash + sum(position.market_value for position in self._positions)
        for position in self._positions:
            position.cost_basis = round(position.quantity * position.average_cost, 4)
            position.unrealized_pnl = round(position.market_value - position.cost_basis, 4)
            position.unrealized_return = (
                round(position.unrealized_pnl / position.cost_basis, 6)
                if position.cost_basis > 0
                else None
            )
        return PortfolioSnapshot(
            timestamp=datetime.now(UTC),
            nav=nav,
            cash=self._cash,
            drawdown=self._drawdown,
            daily_pnl=self._daily_pnl,
            weekly_pnl=self._weekly_pnl,
            positions=list(self._positions),
        )

    def snapshot(self) -> PortfolioSnapshot:
        """Build snapshot AND persist it (use for write paths)."""
        snap = self.current_snapshot()
        self._repository.save(snap)
        self._history[snap.timestamp.isoformat()] = snap
        self._history_repository.save(self._history)
        return snap

    def set_risk_state(self, drawdown: float, daily_pnl: float, weekly_pnl: float) -> None:
        self._drawdown = drawdown
        self._daily_pnl = daily_pnl
        self._weekly_pnl = weekly_pnl
        self.snapshot()

    def reset(self) -> None:
        self._positions = []
        self._cash = self._config.portfolio_value
        self._drawdown = 0.0
        self._daily_pnl = 0.0
        self._weekly_pnl = 0.0
        self._history = {}
        self.snapshot()

    def apply_fill(self, instrument: Instrument, side: OrderSide, quantity: float, average_price: float) -> PortfolioSnapshot:
        signed_quantity = quantity if side == OrderSide.BUY else -quantity
        cash_delta = quantity * average_price
        self._cash = self._cash - cash_delta if side == OrderSide.BUY else self._cash + cash_delta

        existing = next((position for position in self._positions if position.instrument.symbol == instrument.symbol), None)
        if existing is None:
            if signed_quantity > 0:
                self._positions.append(
                    Position(
                        instrument=instrument,
                        quantity=quantity,
                        market_value=round(quantity * average_price, 4),
                        weight=0.0,
                        average_cost=round(average_price, 4),
                        cost_basis=round(quantity * average_price, 4),
                    )
                )
        else:
            new_quantity = existing.quantity + signed_quantity
            if new_quantity <= 0:
                self._positions = [position for position in self._positions if position.instrument.symbol != instrument.symbol]
            else:
                if side == OrderSide.BUY:
                    existing_cost = existing.quantity * existing.average_cost
                    added_cost = quantity * average_price
                    existing.average_cost = round((existing_cost + added_cost) / new_quantity, 4) if new_quantity > 0 else 0.0
                existing.quantity = round(new_quantity, 4)
                existing.market_value = round(existing.quantity * average_price, 4)

        snapshot = self.snapshot()
        nav = snapshot.nav or 1.0
        for position in self._positions:
            position.weight = round(position.market_value / nav, 6) if nav > 0 else 0.0
        return self.snapshot()

    def nav_history(self, limit: int = 120) -> list[PortfolioSnapshot]:
        entries = sorted(self._history.values(), key=lambda item: item.timestamp)
        if limit > 0:
            entries = entries[-limit:]
        return entries

    def reconcile_with_broker(self, broker: BrokerAdapter) -> PortfolioReconciliationSummary:
        snapshot = self.snapshot()
        broker_cash = broker.get_cash()
        broker_positions = broker.get_positions()
        snapshot_symbols = {position.instrument.symbol for position in snapshot.positions}
        broker_symbols = {position.instrument.symbol for position in broker_positions}
        return PortfolioReconciliationSummary(
            broker_cash=broker_cash,
            snapshot_cash=snapshot.cash,
            cash_difference=round(broker_cash - snapshot.cash, 4),
            broker_position_count=len(broker_positions),
            snapshot_position_count=len(snapshot.positions),
            missing_symbols=sorted(snapshot_symbols - broker_symbols),
            unexpected_symbols=sorted(broker_symbols - snapshot_symbols),
        )

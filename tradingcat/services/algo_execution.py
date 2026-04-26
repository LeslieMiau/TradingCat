from __future__ import annotations

import math
import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Callable

import numpy as np


class AlgoType(str, Enum):
    TWAP = "twap"
    VWAP = "vwap"
    ADAPTIVE = "adaptive"


@dataclass
class AlmgrenChrissImpact:
    """Almgren-Chriss market impact model."""
    annual_volatility: float = 0.20
    bid_ask_spread: float = 0.001  # 10 bps
    daily_volume: float = 1_000_000
    permanent_impact_coeff: float = 0.01
    temporary_impact_coeff: float = 0.02

    def permanent_impact(self, qty: float, price: float) -> float:
        """Permanent price impact per share."""
        participation = qty / self.daily_volume if self.daily_volume > 0 else 0
        return self.permanent_impact_coeff * self.annual_volatility * math.sqrt(participation) * price

    def temporary_impact(self, qty: float, price: float) -> float:
        """Temporary impact (reverses after trade)."""
        participation = qty / self.daily_volume if self.daily_volume > 0 else 0
        return self.temporary_impact_coeff * self.annual_volatility * math.sqrt(participation) * price

    def total_cost_bps(self, qty: float, price: float) -> float:
        perm = self.permanent_impact(qty, price)
        temp = self.temporary_impact(qty, price)
        total = (self.bid_ask_spread * price + perm + temp) / price * 10_000 if price > 0 else 0
        return total  # in bps


@dataclass
class AlgoSlice:
    time_idx: int
    quantity: float
    expected_price: float | None = None
    status: str = "pending"
    filled_qty: float = 0.0


class AlgoOrder:
    """A parent order broken into slices."""

    def __init__(self, symbol: str, side: str, total_quantity: float,
                 slices: list[AlgoSlice], algo_type: AlgoType) -> None:
        self.symbol = symbol
        self.side = side
        self.total_quantity = total_quantity
        self.remaining = total_quantity
        self.slices = slices
        self.algo_type = algo_type
        self.created_at = datetime.now()
        self.execution_log: list[dict] = []

    @property
    def filled_qty(self) -> float:
        return sum(s.filled_qty for s in self.slices)

    @property
    def is_complete(self) -> bool:
        return self.filled_qty >= self.total_quantity - 1e-8


class AlgoExecutor:
    """Execute large orders via algorithmic slicing."""

    def __init__(self, submit_fn: Callable, impact: AlmgrenChrissImpact | None = None) -> None:
        self._submit = submit_fn  # fn(symbol, side, qty) -> broker_order_id
        self._impact = impact or AlmgrenChrissImpact()

    # ---- slicing strategies ----

    def twap_slices(self, symbol: str, side: str, quantity: float,
                    n_slices: int = 10, price: float = 0.0) -> AlgoOrder:
        """Equal quantity per time slice."""
        qty_per = round(quantity / n_slices, 2)
        cost_est = self._impact.total_cost_bps(quantity, price) if price > 0 else 0
        slices = [AlgoSlice(time_idx=i, quantity=qty_per,
                            expected_price=price * (1 + cost_est / 10_000 * (-1 if side == "sell" else 1)))
                  for i in range(n_slices)]
        return AlgoOrder(symbol, side, quantity, slices, AlgoType.TWAP)

    def vwap_slices(self, symbol: str, side: str, quantity: float,
                    volume_profile: list[float] | None = None,
                    price: float = 0.0) -> AlgoOrder:
        """Quantity proportional to expected volume."""
        vp = volume_profile or [1.0] * 13  # default 13 half-hour bars
        total = sum(vp)
        weights = [v / total for v in vp]
        qty_per = [round(quantity * w, 2) for w in weights]
        cost_est = self._impact.total_cost_bps(quantity, price) if price > 0 else 0
        slices = [AlgoSlice(time_idx=i, quantity=max(q, 0.01),
                            expected_price=price * (1 + cost_est / 10_000 * (-1 if side == "sell" else 1)))
                  for i, q in enumerate(qty_per)]
        return AlgoOrder(symbol, side, quantity, slices, AlgoType.VWAP)

    # ---- execution ----

    def execute(self, order: AlgoOrder, interval_seconds: int = 30,
                callback: Callable | None = None) -> None:
        """Execute slices sequentially."""
        for i, slc in enumerate(order.slices):
            if slc.quantity < 0.01:
                continue
            try:
                broker_id = self._submit(order.symbol, order.side, slc.quantity)
                slc.status = "submitted"
                order.execution_log.append({
                    "slice": i, "qty": slc.quantity, "broker_id": broker_id,
                    "status": "submitted", "timestamp": datetime.now().isoformat(),
                })
            except Exception as exc:
                slc.status = "failed"
                order.execution_log.append({
                    "slice": i, "qty": slc.quantity, "error": str(exc),
                    "status": "failed", "timestamp": datetime.now().isoformat(),
                })
                continue

            if callback:
                try:
                    callback(order, slc)
                except Exception:
                    pass

            if i < len(order.slices) - 1:
                time.sleep(interval_seconds)

    def estimate_cost(self, symbol: str, side: str, quantity: float,
                      price: float, algo: AlgoType = AlgoType.TWAP) -> dict:
        impact = self._impact
        perm = impact.permanent_impact(quantity, price)
        temp = impact.temporary_impact(quantity, price)
        total_bps = impact.total_cost_bps(quantity, price)
        slippage_cost = temp * quantity
        return {
            "symbol": symbol,
            "quantity": quantity,
            "price": price,
            "side": side,
            "algo": algo.value,
            "permanent_impact_per_share": round(perm, 6),
            "temporary_impact_per_share": round(temp, 6),
            "estimated_total_cost_bps": round(total_bps, 2),
            "estimated_slippage_cost": round(slippage_cost, 2),
            "participation_rate": round(quantity / impact.daily_volume * 100, 4) if impact.daily_volume > 0 else 0,
        }

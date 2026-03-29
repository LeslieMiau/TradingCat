from __future__ import annotations

from collections.abc import Callable

from tradingcat.domain.models import Market, PortfolioSnapshot


class PortfolioProjectionService:
    def __init__(
        self,
        *,
        available_cash_by_market: Callable[[], dict[Market, float]],
        nav_history: Callable[[int], list[PortfolioSnapshot]],
    ) -> None:
        self._available_cash_by_market = available_cash_by_market
        self._nav_history = nav_history

    @staticmethod
    def account_keys() -> list[str]:
        return ["total", Market.CN.value, Market.HK.value, Market.US.value]

    @staticmethod
    def serialize_position(position) -> dict[str, object]:
        return {
            "symbol": position.instrument.symbol,
            "name": position.instrument.name,
            "market": position.instrument.market.value,
            "asset_class": position.instrument.asset_class.value,
            "quantity": position.quantity,
            "average_cost": position.average_cost,
            "market_value": position.market_value,
            "weight": position.weight,
            "unrealized_pnl": position.unrealized_pnl,
            "unrealized_return": position.unrealized_return,
        }

    def account_positions(self, snapshot: PortfolioSnapshot, account: str) -> list[dict[str, object]]:
        if account == "total":
            return [self.serialize_position(position) for position in snapshot.positions]
        return [
            self.serialize_position(position)
            for position in snapshot.positions
            if position.instrument.market.value == account
        ]

    def account_cash_map(self, snapshot: PortfolioSnapshot) -> dict[str, float]:
        cash_by_market = self._available_cash_by_market()
        return {
            "total": snapshot.cash,
            Market.CN.value: round(cash_by_market.get(Market.CN, 0.0), 4),
            Market.HK.value: round(cash_by_market.get(Market.HK, 0.0), 4),
            Market.US.value: round(cash_by_market.get(Market.US, 0.0), 4),
        }

    def account_curves(self, *, limit: int = 90) -> dict[str, list[dict[str, object]]]:
        curves = {key: [] for key in self.account_keys()}
        history = self._nav_history(limit)
        if not history:
            return curves
        current_cash_map = self.account_cash_map(history[-1])
        for item in history:
            market_values = {
                Market.CN.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.CN), 4),
                Market.HK.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.HK), 4),
                Market.US.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.US), 4),
            }
            curves["total"].append({"t": item.timestamp.isoformat(), "v": round(item.nav, 4)})
            for market_key in (Market.CN.value, Market.HK.value, Market.US.value):
                curves[market_key].append(
                    {
                        "t": item.timestamp.isoformat(),
                        "v": round(market_values[market_key] + current_cash_map.get(market_key, 0.0), 4),
                    }
                )
        return curves

    @staticmethod
    def allocation_mix(
        position_value: float,
        cash: float,
        positions: list[dict[str, object]],
        nav: float,
    ) -> dict[str, float]:
        if not nav:
            return {"cash": 0.0, "equity": 0.0, "option": 0.0}
        option_value = sum(float(position["market_value"]) for position in positions if position["asset_class"] == "option")
        equity_value = max(0.0, position_value - option_value)
        return {
            "cash": round(cash / nav, 6),
            "equity": round(equity_value / nav, 6),
            "option": round(option_value / nav, 6),
        }

from __future__ import annotations

from datetime import UTC, datetime

from tradingcat.domain.models import AssetClass, Instrument, Market, PortfolioSnapshot, Position
from tradingcat.services.portfolio_projections import PortfolioProjectionService


def _snapshot(*, timestamp: datetime, nav: float, cash: float, positions: list[Position]) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        timestamp=timestamp,
        nav=nav,
        cash=cash,
        positions=positions,
    )


def test_portfolio_projection_service_builds_market_curves_and_mix():
    us_position = Position(
        instrument=Instrument(symbol="SPY", market=Market.US, asset_class=AssetClass.ETF, name="SPY"),
        quantity=2.0,
        average_cost=100.0,
        market_value=220.0,
        weight=0.55,
    )
    hk_option = Position(
        instrument=Instrument(symbol="700OPT", market=Market.HK, asset_class=AssetClass.OPTION, currency="HKD"),
        quantity=1.0,
        average_cost=10.0,
        market_value=40.0,
        weight=0.1,
    )
    history = [
        _snapshot(
            timestamp=datetime(2026, 3, 7, tzinfo=UTC),
            nav=320.0,
            cash=60.0,
            positions=[us_position],
        ),
        _snapshot(
            timestamp=datetime(2026, 3, 8, tzinfo=UTC),
            nav=360.0,
            cash=100.0,
            positions=[us_position, hk_option],
        ),
    ]
    service = PortfolioProjectionService(
        available_cash_by_market=lambda: {Market.US: 70.0, Market.HK: 30.0},
        nav_history=lambda limit: history[:limit],
    )

    cash_map = service.account_cash_map(history[-1])
    curves = service.account_curves(limit=90)
    total_positions = service.account_positions(history[-1], "total")
    allocation_mix = service.allocation_mix(
        position_value=sum(float(position["market_value"]) for position in total_positions),
        cash=cash_map["total"],
        positions=total_positions,
        nav=history[-1].nav,
    )

    assert cash_map == {"total": 100.0, "CN": 0.0, "HK": 30.0, "US": 70.0}
    assert curves["total"][-1]["v"] == 360.0
    assert curves["US"][-1]["v"] == 290.0
    assert curves["HK"][-1]["v"] == 70.0
    assert allocation_mix == {"cash": 0.277778, "equity": 0.611111, "option": 0.111111}

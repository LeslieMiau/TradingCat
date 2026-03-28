from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from tradingcat.api.schemas import RebalancePlanPayload, RiskStatePayload
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/portfolio")


@router.get("")
def portfolio(request: Request):
    return get_app_state(request).portfolio.current_snapshot()


@router.post("/risk-state")
def portfolio_risk_state(request: Request, payload: RiskStatePayload):
    app = get_app_state(request)
    app.portfolio.set_risk_state(payload.drawdown, payload.daily_pnl, payload.weekly_pnl)
    return app.execution_gate_summary(date.today())


@router.post("/reconcile")
def portfolio_reconcile(request: Request):
    return get_app_state(request).reconcile_portfolio_with_live_broker()


@router.post("/rebalance-plan")
def portfolio_rebalance_plan(request: Request, payload: RebalancePlanPayload):
    return get_app_state(request).rebalance_plan(payload.as_of or date.today())

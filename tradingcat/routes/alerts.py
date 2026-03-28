from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/alerts")


@router.get("")
def alerts(request: Request):
    return get_app_state(request).alerts.list_alerts()


@router.get("/summary")
def alerts_summary(request: Request):
    return get_app_state(request).alerts.latest_summary()


@router.post("/evaluate")
def alerts_evaluate(request: Request):
    return get_app_state(request).alerts_facade.evaluate()

from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state
router = APIRouter()


@router.get("/preflight")
@router.get("/preflight/startup")
def preflight_startup(request: Request):
    return get_app_state(request).startup_preflight_summary()


@router.get("/diagnostics/summary")
def diagnostics_summary(request: Request):
    return get_app_state(request).operations_facade.readiness()

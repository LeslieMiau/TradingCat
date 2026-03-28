from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state
from tradingcat.services.preflight import build_startup_preflight


router = APIRouter()


@router.get("/preflight")
@router.get("/preflight/startup")
def preflight_startup(request: Request):
    return build_startup_preflight(get_app_state(request).config)


@router.get("/diagnostics/summary")
def diagnostics_summary(request: Request):
    return get_app_state(request).operations_readiness()


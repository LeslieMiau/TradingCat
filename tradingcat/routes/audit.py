from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/audit")


@router.get("/events")
@router.get("/logs")
def audit_logs(request: Request, limit: int = 100):
    return get_app_state(request).audit.list_events(limit=limit)


@router.get("/summary")
def audit_summary(request: Request):
    return get_app_state(request).audit.summary()


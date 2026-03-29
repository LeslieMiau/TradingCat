from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/audit")


@router.get("/events")
@router.get("/logs")
def audit_logs(request: Request, limit: int = 100, order_intent_id: str | None = None):
    return get_app_state(request).audit.list_events(limit=limit, order_intent_id=order_intent_id)


@router.get("/summary")
def audit_summary(request: Request):
    return get_app_state(request).audit.summary()

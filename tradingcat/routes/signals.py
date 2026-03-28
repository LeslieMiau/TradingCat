from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request

from tradingcat.routes.common import get_app_state
from tradingcat.services.risk import RiskViolation


router = APIRouter(prefix="/signals")


@router.get("/today")
def signals_today(request: Request):
    app = get_app_state(request)
    try:
        return app.get_signals(date.today())
    except RiskViolation as exc:
        app.audit.log(category="risk", action="violation", status="warning", details={"source": "signals_today", "detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


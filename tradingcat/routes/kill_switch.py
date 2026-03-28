from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/kill-switch")


@router.get("")
def kill_switch(request: Request):
    return get_app_state(request).risk.kill_switch_status()


@router.post("")
def set_kill_switch(request: Request, enabled: bool = True, reason: str | None = None):
    return get_app_state(request).set_kill_switch(enabled, reason)


@router.post("/verify")
def verify_kill_switch(request: Request):
    status = get_app_state(request).risk.kill_switch_status()
    return {"verified": True, "enabled": status["enabled"], "latest": status["latest"]}


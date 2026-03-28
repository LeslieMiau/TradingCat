from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/broker")


@router.get("/status")
@router.get("/probe")
def broker_status(request: Request):
    return get_app_state(request).broker_status()


@router.post("/recover")
def broker_recover(request: Request):
    app = get_app_state(request)
    result = app.recover_runtime()
    app.audit.log(category="operations", action="broker_recover", details={"detail": result["after"]["broker_status"]["detail"]})
    return result


@router.get("/recovery-attempts")
def broker_recovery_attempts(request: Request):
    return get_app_state(request).recovery.list_attempts()


@router.get("/recovery-summary")
def broker_recovery_summary(request: Request):
    return get_app_state(request).recovery.summary()


@router.get("/validate")
@router.post("/validate")
def broker_validate(request: Request):
    return get_app_state(request).broker_validation()


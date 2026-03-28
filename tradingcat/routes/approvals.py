from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.api.schemas import DecisionPayload
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/approvals")


@router.get("")
def list_approvals(request: Request):
    return get_app_state(request).approvals.list_requests()


@router.post("/{request_id}/approve")
def approve_request(request: Request, request_id: str, payload: DecisionPayload):
    app = get_app_state(request)
    approval = app.approvals.approve(request_id, payload.reason)
    report = app.execution.submit_approved(request_id)
    app.audit.log(category="approval", action="approve", details={"request_id": approval.id, "status": approval.status.value, "reason": payload.reason or ""})
    return {"approval": approval, "report": report}


@router.post("/{request_id}/reject")
def reject_request(request: Request, request_id: str, payload: DecisionPayload):
    app = get_app_state(request)
    approval = app.approvals.reject(request_id, payload.reason)
    app.audit.log(category="approval", action="reject", details={"request_id": approval.id, "status": approval.status.value, "reason": payload.reason or ""})
    return approval


@router.post("/{request_id}/expire")
def expire_request(request: Request, request_id: str, payload: DecisionPayload):
    app = get_app_state(request)
    approval = app.approvals.expire(request_id, payload.reason)
    app.audit.log(category="approval", action="expire", details={"request_id": approval.id, "status": approval.status.value, "reason": payload.reason or ""})
    return approval


@router.post("/expire-stale")
def expire_stale_approvals(request: Request, reason: str | None = None):
    return get_app_state(request).expire_stale_approvals(reason)


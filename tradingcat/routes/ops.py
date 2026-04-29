from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from tradingcat.api.schemas import ExecutionPolicyPayload, RiskUpdatePayload
from tradingcat.api.view_models import OperationsReadinessResponse
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/ops")


@router.post("/evaluate-triggers")
async def evaluate_smart_orders(request: Request):
    return await get_app_state(request).rule_engine.evaluate_all_async()


@router.get("/risk/config")
def get_risk_config(request: Request):
    return get_app_state(request).operations_facade.risk_config()


@router.post("/risk/config")
def update_risk_config(request: Request, payload: RiskUpdatePayload):
    return get_app_state(request).update_risk_config(**payload.model_dump(exclude_none=True))


@router.get("/tca")
def get_tca_metrics(request: Request):
    return get_app_state(request).operations_facade.tca()


@router.get("/readiness", response_model=OperationsReadinessResponse)
def ops_readiness(request: Request):
    return get_app_state(request).operations_facade.readiness()


@router.get("/execution-metrics")
def ops_execution_metrics(request: Request):
    return get_app_state(request).operations_facade.execution_metrics()


@router.get("/daily-report")
def ops_daily_report(request: Request):
    return get_app_state(request).operations_facade.daily_report()


@router.get("/weekly-report")
def ops_weekly_report(request: Request):
    return get_app_state(request).operations_facade.weekly_report()


@router.get("/postmortem")
def ops_postmortem(request: Request, window_days: int = 7):
    return get_app_state(request).operations_facade.postmortem(window_days)


@router.get("/incidents/replay")
def ops_incidents_replay(request: Request, window_days: int = 7):
    return get_app_state(request).operations_facade.incident_replay(window_days)


@router.post("/journal/record")
def ops_journal_record(request: Request):
    return get_app_state(request).operations_facade.record_journal()


@router.get("/journal")
def ops_journal(request: Request):
    return get_app_state(request).operations.list_entries()


@router.get("/journal/summary")
def ops_journal_summary(request: Request):
    return get_app_state(request).operations.summary()


@router.get("/execution-policy")
def get_execution_policy(request: Request):
    return get_app_state(request).execution_policy.summary()


@router.post("/execution-policy")
def set_execution_policy(request: Request, payload: ExecutionPolicyPayload):
    return get_app_state(request).execution_policy.set_mode(payload.mode, reason=payload.reason)

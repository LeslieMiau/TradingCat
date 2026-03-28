from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from tradingcat.api.schemas import RiskUpdatePayload, RolloutPolicyPayload
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
    return get_app_state(request).audit.execution_metrics_summary()


@router.get("/audit/summary")
def ops_audit_summary(request: Request):
    return get_app_state(request).audit.summary()


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


@router.get("/acceptance")
def ops_acceptance(request: Request):
    return get_app_state(request).operations.acceptance_summary()


@router.get("/acceptance/timeline")
@router.get("/live-acceptance/timeline")
def ops_acceptance_timeline(request: Request, window_days: int = 30):
    return get_app_state(request).operations.acceptance_timeline(window_days)


@router.get("/rollout")
def ops_rollout(request: Request):
    return get_app_state(request).operations_facade.rollout()


@router.get("/rollout/milestones")
def ops_rollout_milestones(request: Request):
    return get_app_state(request).operations.rollout_milestones()


@router.get("/rollout/checklist")
def ops_rollout_checklist(request: Request, stage: str | None = None, as_of: date | None = None):
    return get_app_state(request).operations_facade.rollout_checklist(stage, as_of)


@router.get("/rollout/promotions")
@router.get("/rollout/promotions/summary")
def ops_rollout_promotions(request: Request):
    return get_app_state(request).rollout_promotions.summary()


@router.get("/rollout-policy")
def ops_rollout_policy(request: Request):
    return get_app_state(request).operations_facade.rollout_policy_summary()


@router.post("/rollout-policy")
def ops_set_rollout_policy(request: Request, payload: RolloutPolicyPayload):
    return get_app_state(request).rollout_policy.set_policy(payload.stage, reason=payload.reason, source="manual")


@router.post("/rollout-policy/apply-recommendation")
def ops_apply_rollout_policy_recommendation(request: Request):
    return get_app_state(request).operations_facade.apply_rollout_policy_recommendation()


@router.post("/rollout/promote")
@router.post("/rollout-policy/promote")
def ops_rollout_promote(request: Request, stage: str, reason: str | None = None):
    return get_app_state(request).promote_rollout_stage(stage, reason)


@router.get("/go-live")
def ops_go_live(request: Request, as_of: date | None = None):
    return get_app_state(request).operations_facade.go_live(as_of)


@router.get("/live-acceptance")
def ops_live_acceptance(request: Request, as_of: date | None = None, incident_window_days: int = 14):
    return get_app_state(request).operations_facade.live_acceptance(as_of, incident_window_days)

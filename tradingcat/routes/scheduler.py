from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request

from tradingcat.domain.models import Market
from tradingcat.routes.common import get_app_state
from tradingcat.services.trading_session import TradingSessionService


router = APIRouter(prefix="/scheduler")


_CYCLE_JOB_IDS = {
    "pre_market_briefing", "pre_market_briefing_us", "pre_market_briefing_hk",
    "intraday_insight_scan",
    "post_market_reflection", "post_market_reflection_us", "post_market_reflection_hk",
}


@router.get("/jobs")
def scheduler_jobs(request: Request):
    return get_app_state(request).scheduler.list_jobs()


@router.post("/jobs/{job_id}/run")
def scheduler_run(request: Request, job_id: str):
    return get_app_state(request).scheduler.run_job(job_id)


@router.get("/runs")
def scheduler_runs(request: Request, limit: int = 50, job_id: str | None = None):
    return get_app_state(request).scheduler.run_history(limit=limit, job_id=job_id)


@router.get("/jobs/{job_id}/runs")
def scheduler_job_runs(request: Request, job_id: str, limit: int = 50):
    return get_app_state(request).scheduler.run_history(limit=limit, job_id=job_id)


@router.get("/cycle-status")
def scheduler_cycle_status(request: Request):
    """聚合自主交易循环状态：各市场阶段 + 循环任务状态 + 最近运行记录。"""
    app_state = get_app_state(request)
    calendar = app_state.market_calendar
    session_svc = TradingSessionService(calendar)
    now = datetime.now(UTC)

    # 各市场阶段
    phases = {}
    for m in Market:
        s = session_svc.get_phase(m, now=now)
        phases[m.value] = {
            "phase": s.phase.value,
            "local_date": str(s.local_date),
            "is_trading_day": s.underlying_session.is_trading_day,
        }

    # 循环任务状态
    jobs = {j.id: j for j in app_state.scheduler.list_jobs() if j.id in _CYCLE_JOB_IDS}

    # 最近运行记录（批量查询，避免 N+1）
    all_history = app_state.scheduler.run_history(limit=50)
    recent_runs = {}
    for jid in _CYCLE_JOB_IDS:
        if jid not in jobs:
            continue
        matches = [r for r in all_history if r.job_id == jid]
        recent_runs[jid] = matches[0] if matches else None

    return {
        "phases": phases,
        "jobs": {
            jid: {
                "id": j.id,
                "name": j.name,
                "enabled": j.enabled,
                "next_run_at": j.next_run_at.isoformat() if j.next_run_at else None,
                "last_run_at": j.last_run_at.isoformat() if j.last_run_at else None,
                "interval_seconds": getattr(j, "interval_seconds", None),
            }
            for jid, j in jobs.items()
        },
        "recent_runs": {
            jid: {
                "status": r.status,
                "detail": r.detail,
                "executed_at": r.executed_at.isoformat() if hasattr(r, "executed_at") and r.executed_at else None,
                "duration_ms": getattr(r, "duration_ms", None),
            }
            if r else None
            for jid, r in recent_runs.items()
        },
    }


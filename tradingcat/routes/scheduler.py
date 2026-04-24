from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/scheduler")


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


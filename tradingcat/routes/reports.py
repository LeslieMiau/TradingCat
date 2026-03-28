from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from tradingcat.routes.common import get_app_state
from tradingcat.services.reporting import latest_report_dir, load_report_summary, resolve_report_dir, summarize_report_for_dashboard


router = APIRouter(prefix="/reports")


@router.get("/latest")
def reports_latest(request: Request):
    latest_dir = latest_report_dir(get_app_state(request).config.data_dir)
    if latest_dir is None:
        return {"report_dir": None}
    return load_report_summary(latest_dir)


@router.get("/latest/dashboard")
def reports_latest_dashboard(request: Request):
    latest_dir = latest_report_dir(get_app_state(request).config.data_dir)
    if latest_dir is None:
        return {"report_dir": None}
    return summarize_report_for_dashboard(load_report_summary(latest_dir))


@router.get("/{report_ref}/dashboard")
def reports_dashboard(request: Request, report_ref: str):
    report_dir = resolve_report_dir(get_app_state(request).config.data_dir, report_ref)
    if report_dir is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return summarize_report_for_dashboard(load_report_summary(report_dir))


@router.get("/{report_ref}")
def reports_detail(request: Request, report_ref: str):
    report_dir = resolve_report_dir(get_app_state(request).config.data_dir, report_ref)
    if report_dir is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return load_report_summary(report_dir)


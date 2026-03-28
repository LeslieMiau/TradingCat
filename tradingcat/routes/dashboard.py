from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from tradingcat.routes.common import dashboard_page_response, get_app_state, read_template


router = APIRouter(prefix="/dashboard")


@router.get("", response_class=HTMLResponse)
def dashboard_page():
    return dashboard_page_response()


@router.get("/summary")
def dashboard_summary(request: Request, as_of: date | None = None):
    return get_app_state(request).dashboard_summary(as_of)


@router.get("/strategies/{strategy_id}", response_class=HTMLResponse)
def dashboard_strategy_page(request: Request, strategy_id: str):
    get_app_state(request).strategy_by_id(strategy_id)
    return read_template("strategy.html")


@router.get("/accounts/{account_id}", response_class=HTMLResponse)
def dashboard_account_page(account_id: str):
    if account_id not in {"total", "CN", "HK", "US"}:
        raise HTTPException(status_code=404, detail="Unknown account")
    return read_template("account.html")


@router.get("/research", response_class=HTMLResponse)
def dashboard_research_page():
    return read_template("research.html")


@router.get("/journal", response_class=HTMLResponse)
def dashboard_journal_page():
    return read_template("journal.html")


@router.get("/operations", response_class=HTMLResponse)
def dashboard_operations_page():
    return read_template("operations.html")


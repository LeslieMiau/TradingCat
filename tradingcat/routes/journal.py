from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/journal")


@router.get("/plans/latest")
def latest_plan(request: Request, account: str = "total", as_of: date | None = None):
    app = get_app_state(request)
    note = app.trading_journal.latest_plan(account=account, as_of=as_of)
    return note or app.generate_daily_trading_plan(as_of or date.today(), account=account)


@router.get("/plans")
def list_plans(request: Request, account: str | None = None):
    return get_app_state(request).trading_journal.list_plans(account)


@router.post("/plans/generate")
def generate_plan(request: Request, as_of: date | None = None):
    return get_app_state(request).generate_daily_trading_plan(as_of or date.today())


@router.get("/summaries/latest")
def latest_summary(request: Request, account: str = "total", as_of: date | None = None):
    app = get_app_state(request)
    note = app.trading_journal.latest_summary(account=account, as_of=as_of)
    return note or app.generate_daily_trading_summary(as_of or date.today())


@router.get("/summaries")
def list_summaries(request: Request, account: str | None = None):
    return get_app_state(request).trading_journal.list_summaries(account)


@router.post("/summaries/generate")
def generate_summary(request: Request, as_of: date | None = None):
    return get_app_state(request).generate_daily_trading_summary(as_of or date.today())


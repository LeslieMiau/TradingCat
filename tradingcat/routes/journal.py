from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/journal")


@router.get("/plans/latest")
def latest_plan(request: Request, account: str = "total", as_of: date | None = None):
    return get_app_state(request).journal_facade.latest_plan(account=account, as_of=as_of)


@router.get("/plans")
def list_plans(request: Request, account: str | None = None):
    return get_app_state(request).trading_journal.list_plans(account)


@router.post("/plans/generate")
def generate_plan(request: Request, as_of: date | None = None):
    return get_app_state(request).journal_facade.generate_plan(as_of)


@router.get("/summaries/latest")
def latest_summary(request: Request, account: str = "total", as_of: date | None = None):
    return get_app_state(request).journal_facade.latest_summary(account=account, as_of=as_of)


@router.get("/summaries")
def list_summaries(request: Request, account: str | None = None):
    return get_app_state(request).trading_journal.list_summaries(account)


@router.post("/summaries/generate")
def generate_summary(request: Request, as_of: date | None = None):
    return get_app_state(request).journal_facade.generate_summary(as_of)


@router.get("/daily")
def daily_journal(request: Request, account: str = "total", as_of: date | None = None):
    journal = get_app_state(request).trading_journal
    plan = journal.latest_plan(account=account, as_of=as_of)
    summary = journal.latest_summary(account=account, as_of=as_of)
    return {
        "account": account,
        "as_of": (as_of or date.today()).isoformat(),
        "latest_plan": plan.model_dump(mode="json") if plan else None,
        "latest_summary": summary.model_dump(mode="json") if summary else None,
        "recent_plans": [note.model_dump(mode="json") for note in journal.list_plans(account)[:7]],
        "recent_summaries": [note.model_dump(mode="json") for note in journal.list_summaries(account)[:7]],
    }


@router.get("/markdown/latest", response_class=PlainTextResponse)
def latest_markdown(request: Request, account: str = "total", as_of: date | None = None):
    journal = get_app_state(request).trading_journal
    plan = journal.latest_plan(account=account, as_of=as_of)
    summary = journal.latest_summary(account=account, as_of=as_of)
    lines = [f"# TradingCat Daily Journal ({account})", ""]
    if plan is None and summary is None:
        lines.append("No plan or summary is available for the selected account/date.")
        return "\n".join(lines)
    if plan is not None:
        lines.extend([f"## Plan {plan.as_of}", "", plan.headline, ""])
        if plan.reasons:
            lines.extend(["### Reasons", *[f"- {item}" for item in plan.reasons], ""])
        if plan.items:
            lines.extend(["### Items", *[f"- {item}" for item in plan.items], ""])
    if summary is not None:
        lines.extend([f"## Summary {summary.as_of}", "", summary.headline, ""])
        if summary.highlights:
            lines.extend(["### Highlights", *[f"- {item}" for item in summary.highlights], ""])
        if summary.blockers:
            lines.extend(["### Blockers", *[f"- {item}" for item in summary.blockers], ""])
        if summary.next_actions:
            lines.extend(["### Next Actions", *[f"- {item}" for item in summary.next_actions], ""])
    return "\n".join(lines)

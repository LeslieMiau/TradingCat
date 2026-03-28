from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request

from tradingcat.api.schemas import ExecutionPreviewPayload, ExecutionRunPayload
from tradingcat.routes.common import get_app_state
from tradingcat.services.risk import RiskViolation


router = APIRouter(prefix="/execution")


@router.post("/reconcile")
def execution_reconcile(request: Request):
    app = get_app_state(request)
    summary = app.execution.reconcile_live_state()
    applied_snapshots = []
    for order_id in summary.applied_fill_order_ids:
        report = next((item for item in app.execution.list_orders() if item.order_intent_id == order_id), None)
        if report is None or report.average_price is None:
            continue
        snapshot = app.apply_fill_to_portfolio(order_id, report.filled_quantity, report.average_price)
        applied_snapshots.append({"order_intent_id": order_id, "nav": snapshot.nav, "cash": snapshot.cash})
    return {"summary": summary, "applied_snapshots": applied_snapshots}


@router.get("/quality")
def execution_quality(request: Request):
    return get_app_state(request).execution.execution_quality_summary()


@router.get("/authorization")
def execution_authorization(request: Request):
    return get_app_state(request).execution.authorization_summary()


@router.post("/preview")
def execution_preview(request: Request, payload: ExecutionPreviewPayload):
    app = get_app_state(request)
    as_of = payload.as_of or date.today()
    try:
        result = app.preview_execution(as_of)
    except RiskViolation as exc:
        app.audit.log(category="risk", action="violation", status="warning", details={"source": "execution_preview", "detail": str(exc)})
        raise
    app.audit.log(category="execution", action="preview_ok", details={"intent_count": result["intent_count"]})
    return result


@router.post("/run")
def execution_run(request: Request, payload: ExecutionRunPayload):
    app = get_app_state(request)
    as_of = payload.as_of or date.today()
    result = app.run_execution_cycle(as_of, enforce_gate=payload.enforce_gate)
    if "submitted_orders" not in result:
        app.audit.log(category="execution", action="run_partial", status="warning", details={"detail": "Execution gate blocked"})
        return {"gate": result}
    app.audit.log(
        category="execution",
        action="run_ok" if not result["failed_orders"] else "run_partial",
        status="ok" if not result["failed_orders"] else "warning",
        details={"submitted_count": len(result["submitted_orders"]), "failed_count": len(result["failed_orders"])},
    )
    return result


@router.get("/gate")
def execution_gate(request: Request, as_of: date | None = None):
    return get_app_state(request).execution_gate_summary(as_of or date.today())

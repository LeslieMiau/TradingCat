from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.api.schemas import ManualFillImportPayload
from tradingcat.domain.models import ManualFill
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/reconcile")


@router.post("/manual-fill")
def reconcile_manual_fill(request: Request, fill: ManualFill):
    app = get_app_state(request)
    report = app.execution.reconcile_manual_fill(fill)
    snapshot = app._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price, fill.side)
    app.audit.log(category="execution", action="manual_fill", details={"broker_order_id": fill.broker_order_id, "order_intent_id": fill.order_intent_id})
    return {"report": report, "snapshot": snapshot}


@router.post("/manual-fills/import")
def reconcile_manual_fill_import(request: Request, payload: ManualFillImportPayload):
    app = get_app_state(request)
    fills = app.parse_manual_fill_import(payload.csv_text, payload.delimiter)
    reports = []
    snapshots = []
    for fill in fills:
        report = app.execution.reconcile_manual_fill(fill)
        snapshot = app._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price, fill.side)
        reports.append(report)
        snapshots.append({"order_intent_id": fill.order_intent_id, "cash": snapshot.cash, "nav": snapshot.nav})
    app.audit.log(category="execution", action="manual_fill_import", details={"count": len(fills)})
    return {"count": len(fills), "reports": reports, "snapshots": snapshots}


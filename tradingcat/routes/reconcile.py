from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.api.schemas import ManualFillImportPayload
from tradingcat.domain.models import ManualFill
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/reconcile")


@router.post("/manual-fill")
def reconcile_manual_fill(request: Request, fill: ManualFill):
    return get_app_state(request).reconcile_manual_fill(fill)


@router.post("/manual-fills/import")
def reconcile_manual_fill_import(request: Request, payload: ManualFillImportPayload):
    app = get_app_state(request)
    fills = app.parse_manual_fill_import(payload.csv_text, payload.delimiter)
    return app.reconcile_manual_fill_import(fills)

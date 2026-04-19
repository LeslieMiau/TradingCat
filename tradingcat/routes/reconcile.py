from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Request
from fastapi.responses import PlainTextResponse

from tradingcat.api.schemas import ManualFillImportPayload
from tradingcat.domain.models import ManualFill, Market
from tradingcat.routes.common import get_app_state
from tradingcat.services.trade_ledger import render_csv


router = APIRouter(prefix="/reconcile")


@router.post("/manual-fill")
def reconcile_manual_fill(request: Request, fill: ManualFill):
    return get_app_state(request).reconcile_manual_fill(fill)


@router.post("/manual-fills/import")
def reconcile_manual_fill_import(request: Request, payload: ManualFillImportPayload):
    app = get_app_state(request)
    fills = app.parse_manual_fill_import(payload.csv_text, payload.delimiter)
    return app.reconcile_manual_fill_import(fills)


@router.get("/ledger")
def reconcile_ledger(
    request: Request,
    start: date | None = None,
    end: date | None = None,
    market: str | None = None,
    fmt: str = "json",
):
    app = get_app_state(request)
    if fmt.lower() == "csv":
        parsed_market: Market | None = None
        if market:
            try:
                parsed_market = Market(market.upper())
            except ValueError:
                parsed_market = None
        entries = app.trade_ledger_service().build_entries(start=start, end=end, market=parsed_market)
        filename_market = parsed_market.value if parsed_market else "ALL"
        filename_end = (end or date.today()).isoformat()
        filename = f"trade_ledger_{filename_market}_{filename_end}.csv"
        return PlainTextResponse(
            render_csv(entries),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return app.operations_facade.trade_ledger(start=start, end=end, market=market)

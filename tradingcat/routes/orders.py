from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from tradingcat.api.schemas import ManualOrderPayload
from tradingcat.domain.triggers import SmartOrder
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/orders")


@router.get("")
def orders(request: Request):
    app = get_app_state(request)
    rows = []
    for order in app.execution.list_orders():
        context = app.execution.resolve_intent_context(order.order_intent_id) or {}
        price_context = app.execution.resolve_price_context(order.order_intent_id)
        rows.append({**order.model_dump(mode="json"), **context, **price_context})
    return rows


@router.post("/{broker_order_id}/cancel")
def cancel_order(request: Request, broker_order_id: str):
    try:
        return get_app_state(request).execution.cancel(broker_order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/cancel-open")
def cancel_open_orders(request: Request):
    result = get_app_state(request).execution.cancel_open_orders()
    return {
        "cancelled_count": len(result["cancelled"]),
        "failed_count": len(result["failed"]),
        "cancelled": result["cancelled"],
        "failed": result["failed"],
    }


@router.post("/manual")
def submit_manual_order(request: Request, payload: ManualOrderPayload):
    return get_app_state(request).submit_manual_order(**payload.model_dump())


@router.get("/triggers")
def list_smart_orders(request: Request):
    return get_app_state(request).rule_engine.list_orders()


@router.post("/triggers")
def create_smart_order(request: Request, order: SmartOrder):
    return get_app_state(request).rule_engine.register_order(order)

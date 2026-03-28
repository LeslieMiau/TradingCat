from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.api.schemas import ChecklistItemPayload
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/compliance")


@router.get("/checklist")
@router.get("/checklists")
def compliance_checklists(request: Request):
    return get_app_state(request).compliance.list_checklists()


@router.get("/checklists/summary")
def compliance_checklists_summary(request: Request):
    return get_app_state(request).compliance.summary()


@router.post("/checklist/{item_id}")
def compliance_checklist_alias(request: Request, item_id: str, payload: ChecklistItemPayload):
    return get_app_state(request).compliance.update_item("cn_programmatic_trading", item_id, payload.status, payload.notes)


@router.post("/checklists/{checklist_id}/items/{item_id}")
def compliance_checklist_item(request: Request, checklist_id: str, item_id: str, payload: ChecklistItemPayload):
    return get_app_state(request).compliance.update_item(checklist_id, item_id, payload.status, payload.notes)


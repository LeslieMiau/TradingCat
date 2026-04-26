from __future__ import annotations

from datetime import date as date_cls

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from tradingcat.domain.models import InsightKind, InsightUserAction
from tradingcat.routes.common import get_app_state


router = APIRouter(prefix="/insights")


class InsightDismissPayload(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class InsightAckPayload(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class InsightRunPayload(BaseModel):
    as_of: date_cls | None = None


def _serialize(insight) -> dict:
    return insight.model_dump(mode="json")


@router.get("")
def list_insights(
    request: Request,
    include_dismissed: bool = False,
    kind: str | None = None,
):
    kinds = None
    if kind is not None:
        try:
            kinds = [InsightKind(kind)]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"unknown insight kind: {kind}") from exc
    items = get_app_state(request).insight_engine.list_active(
        include_dismissed=include_dismissed, kinds=kinds
    )
    return {
        "count": len(items),
        "items": [_serialize(item) for item in items],
        "backend": get_app_state(request).insight_store.backend,
    }


@router.get("/{insight_id}")
def get_insight(request: Request, insight_id: str):
    insight = get_app_state(request).insight_store.get(insight_id)
    if insight is None:
        raise HTTPException(status_code=404, detail="insight not found")
    return _serialize(insight)


@router.post("/{insight_id}/dismiss")
def dismiss_insight(request: Request, insight_id: str, payload: InsightDismissPayload):
    updated = get_app_state(request).insight_store.update_user_action(
        insight_id, InsightUserAction.DISMISSED, reason=payload.reason
    )
    if not updated:
        raise HTTPException(status_code=404, detail="insight not found")
    return {"id": insight_id, "user_action": InsightUserAction.DISMISSED.value}


@router.post("/{insight_id}/ack")
def ack_insight(request: Request, insight_id: str, payload: InsightAckPayload):
    updated = get_app_state(request).insight_store.update_user_action(
        insight_id, InsightUserAction.ACKNOWLEDGED, reason=payload.note
    )
    if not updated:
        raise HTTPException(status_code=404, detail="insight not found")
    return {"id": insight_id, "user_action": InsightUserAction.ACKNOWLEDGED.value}


@router.post("/run")
def run_insight_engine(request: Request, payload: InsightRunPayload | None = None):
    payload = payload or InsightRunPayload()
    result = get_app_state(request).insight_engine.run(as_of=payload.as_of)
    return {
        "as_of": result.as_of.isoformat(),
        "produced": result.produced,
        "produced_count": len(result.produced),
        "suppressed_duplicates": result.suppressed_duplicates,
        "expired": result.expired,
    }

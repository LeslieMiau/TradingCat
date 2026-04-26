"""Advisory-only diagnostic endpoints.

Read-only surface for the absorbed (TradingAgents-CN) capability layer.
Lives under ``/research/advisory`` to keep it visually segregated from
the trading control surface — these endpoints never produce signals,
orders, or approvals.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from tradingcat.routes.common import get_app_state
from tradingcat.services.advisory_capabilities import build_advisory_capability_snapshot


router = APIRouter(prefix="/research/advisory")


@router.get("/capabilities")
def advisory_capabilities(request: Request) -> dict:
    """Snapshot of which absorbed capabilities are loaded, enabled, ready.

    Pure read; safe to poll. Inspects the in-process ``AppConfig`` plus a
    handful of optional-SDK import probes. Does not contact any external
    network endpoint and does not mutate state.
    """

    config = get_app_state(request).config
    return build_advisory_capability_snapshot(config)

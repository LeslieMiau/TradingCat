"""API-level tests for /insights endpoints."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from tradingcat.domain.models import (
    Insight,
    InsightEvidence,
    InsightKind,
    InsightSeverity,
    InsightUserAction,
)
from tradingcat.main import app, app_state
from tradingcat.repositories.insight_store import InsightStore
from tradingcat.services.insight_engine import InsightEngine

client = TestClient(app)


def _now() -> datetime:
    return datetime.now(UTC)


def _seed(store: InsightStore, now: datetime, **overrides: object) -> str:
    defaults = {
        "id": "api-test-1",
        "kind": InsightKind.CORRELATION_BREAK,
        "severity": InsightSeverity.URGENT,
        "headline": "0700 与 SPY 相关性偏离",
        "subjects": ["0700", "SPY"],
        "causal_chain": [
            InsightEvidence(source="test", fact="30日相关性 0.85", value={"correlation": 0.85}, observed_at=now),
            InsightEvidence(source="test", fact="今日收益偏离 z=2.5", value={"z_score": 2.5}, observed_at=now),
        ],
        "confidence": 0.85,
        "triggered_at": now,
        "expires_at": now + timedelta(hours=36),
    }
    merged = {**defaults, **overrides}
    store.upsert(Insight(**merged))  # type: ignore[arg-type]
    return str(merged["id"])


def test_insights_list_empty():
    store: InsightStore = app_state.insight_store
    for item in store.list(include_dismissed=True):
        store.update_user_action(item.id, InsightUserAction.DISMISSED, reason="cleanup")
    resp = client.get("/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["items"] == []


def test_insights_list_with_items():
    store: InsightStore = app_state.insight_store
    _seed(store, _now())
    resp = client.get("/insights")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] >= 1
    ids = [item["id"] for item in data["items"]]
    assert "api-test-1" in ids


def test_insights_get_by_id():
    store: InsightStore = app_state.insight_store
    _seed(store, _now())
    resp = client.get("/insights/api-test-1")
    assert resp.status_code == 200
    assert resp.json()["id"] == "api-test-1"


def test_insights_get_not_found():
    resp = client.get("/insights/nonexistent")
    assert resp.status_code == 404


def test_insights_dismiss():
    store: InsightStore = app_state.insight_store
    _seed(store, _now(), id="dismiss-test-1")
    resp = client.post("/insights/dismiss-test-1/dismiss", json={"reason": "false alarm"})
    assert resp.status_code == 200
    assert resp.json()["user_action"] == "dismissed"
    list_resp = client.get("/insights")
    assert "dismiss-test-1" not in [item["id"] for item in list_resp.json()["items"]]


def test_insights_ack():
    store: InsightStore = app_state.insight_store
    _seed(store, _now(), id="ack-test-1")
    resp = client.post("/insights/ack-test-1/ack", json={"note": "noted"})
    assert resp.status_code == 200
    assert resp.json()["user_action"] == "acknowledged"


def test_insights_run():
    resp = client.post("/insights/run", json={"as_of": "2026-03-15"})
    assert resp.status_code == 200
    data = resp.json()
    assert "as_of" in data
    assert isinstance(data["produced_count"], int)

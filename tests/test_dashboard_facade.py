from __future__ import annotations

from datetime import date

from tradingcat.api.view_models import PlanItemView
from tradingcat.main import app_state


class _DummyNote:
    def __init__(self, **payload):
        self._payload = payload
        for key, value in payload.items():
            setattr(self, key, value)

    def model_dump(self, mode: str = "json"):
        return dict(self._payload)


def test_dashboard_facade_sub_builders_are_independently_exercisable():
    facade = app_state.dashboard_facade

    candidate_summary = facade._candidate_summary(
        {
            "rows": [
                {"strategy_id": "alpha", "profitability_score": 1.2},
                {"strategy_id": "beta", "profitability_score": 0.8},
            ],
            "deploy_candidate_count": 1,
        }
    )
    assert candidate_summary["deploy_candidate_count"] == 1
    assert [row["strategy_id"] for row in candidate_summary["top_candidates"]] == ["alpha", "beta"]

    plan_note = _DummyNote(
        status="planned",
        headline="今日执行 1 条计划单",
        reasons=["波动率回落"],
        counts={"signal_count": 2, "intent_count": 1, "manual_count": 0},
        items=[],
    )
    plan_items = [
        PlanItemView(
            intent_id="intent-1",
            strategy_id="strategy_a",
            symbol="000001.SZ",
            market="CN",
            side="buy",
            quantity=100.0,
            target_weight=0.1,
            reference_price=10.0,
            requires_approval=False,
            reason="test plan item",
        )
    ]
    trading_plan = facade._trading_plan_summary(
        plan_note,
        plan_items,
        {"pending": [{"id": "approval-1"}], "recent": [{"id": "approval-0"}]},
        {"ready": True, "should_block": False, "policy_stage": "simulate"},
    )
    assert trading_plan["signal_count"] == 2
    assert trading_plan["automated_count"] == 1
    assert trading_plan["pending_approvals"][0]["id"] == "approval-1"

    summary_note = _DummyNote(
        headline="今日总结",
        highlights=["组合维持稳定"],
        blockers=["等待审批"],
        next_actions=["复核候选池"],
    )
    summaries = facade._summaries_summary(
        plan_note,
        summary_note,
        {"highlights": ["日报摘要"]},
        {"highlights": ["周报摘要"]},
    )
    assert summaries["plan"]["headline"] == "今日执行 1 条计划单"
    assert summaries["summary"]["headline"] == "今日总结"
    assert summaries["daily"]["highlights"] == ["日报摘要"]

    details = facade._details_summary(
        {"ready": True, "should_block": False},
        {"ready_for_live": False, "blockers": ["waiting"]},
        {"ready": False},
        [{"broker_order_id": "order-1"}],
    )
    assert details["live_acceptance"]["ready_for_live"] is False
    assert details["recent_orders"][0]["broker_order_id"] == "order-1"

    actual_plan = facade._ensure_plan_note(date.today())
    actual_summary = facade._ensure_summary_note(date.today())
    journal = facade._journal_summary(actual_plan, actual_summary)
    assert "latest_plan" in journal
    assert "recent_plans" in journal
    assert "latest_summary" in journal
    assert "recent_summaries" in journal

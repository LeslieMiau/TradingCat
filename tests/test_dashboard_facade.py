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
        {"overall_regime": "caution", "risk_posture": "hold_pace"},
    )
    assert trading_plan["signal_count"] == 2
    assert trading_plan["automated_count"] == 1
    assert trading_plan["pending_approvals"][0]["id"] == "approval-1"
    assert trading_plan["market_awareness"]["overall_regime"] == "caution"

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
        {
            "live_acceptance": {"ready_for_live": False, "blockers": ["waiting"]},
            "rollout": {"current_recommendation": "simulate", "blockers": ["waiting"]},
            "operations": {"ready": False},
            "data_quality": {"ready": False},
            "market_awareness": {"overall_regime": "neutral", "actions": []},
            "recent_orders": [{"broker_order_id": "order-1"}],
        },
    )
    assert details["live_acceptance"]["ready_for_live"] is False
    assert details["acceptance_progress"]["blockers"] == ["waiting"]
    assert details["recent_orders"][0]["broker_order_id"] == "order-1"

    actual_plan = facade._ensure_plan_note(date.today())
    actual_summary = facade._ensure_summary_note(date.today())
    journal = facade._journal_summary(actual_plan, actual_summary)
    assert "latest_plan" in journal
    assert "recent_plans" in journal
    assert "latest_summary" in journal
    assert "recent_summaries" in journal


def test_dashboard_facade_accounts_delegate_to_portfolio_projection_service():
    facade = app_state.dashboard_facade
    snapshot = app_state.portfolio.current_snapshot()
    original_service = app_state.portfolio_projections

    class _StubProjectionService:
        def account_curves(self, *, limit: int = 90):
            return {
                "total": [{"t": "2026-03-29T00:00:00+00:00", "v": 123.0}],
                "CN": [],
                "HK": [],
                "US": [],
            }

        def account_cash_map(self, snapshot):
            return {"total": snapshot.cash, "CN": 0.0, "HK": 0.0, "US": 0.0}

        @staticmethod
        def account_keys():
            return ["total", "CN", "HK", "US"]

        def account_positions(self, snapshot, account: str):
            return []

        def allocation_mix(self, position_value: float, cash: float, positions, nav: float):
            return {"cash": 1.0, "equity": 0.0, "option": 0.0}

    try:
        app_state.portfolio_projections = _StubProjectionService()
        accounts = facade._accounts(snapshot, [])
    finally:
        app_state.portfolio_projections = original_service

    assert accounts["total"].nav_curve == [{"t": "2026-03-29T00:00:00+00:00", "v": 123.0}]
    assert accounts["total"].allocation_mix == {"cash": 1.0, "equity": 0.0, "option": 0.0}


def test_dashboard_facade_build_summary_delegates_dashboard_reads_to_query_service():
    facade = app_state.dashboard_facade
    original_dashboard_queries = app_state.dashboard_queries
    original_execution_gate_summary = app_state.execution_gate_summary
    original_operations_period_report = app_state.operations_period_report
    original_live_acceptance_summary = app_state.live_acceptance_summary
    original_operations_rollout = app_state.operations_rollout
    original_operations_readiness = app_state.operations_readiness
    original_data_quality_summary = app_state.data_quality_summary
    original_active_execution_strategy_ids = app_state.active_execution_strategy_ids
    original_selection_summary = app_state.selection.summary
    original_allocation_summary = app_state.allocations.summary
    try:
        app_state.execution_gate_summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.operations_period_report = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.live_acceptance_summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.operations_rollout = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.operations_readiness = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.data_quality_summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.active_execution_strategy_ids = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))  # type: ignore[method-assign]
        app_state.selection.summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))
        app_state.allocations.summary = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("dashboard should use dashboard_queries"))

        class _StubDashboardQueries:
            def summary_context(self, evaluation_date: date) -> dict[str, object]:
                return {
                    "gate": {"ready": False, "should_block": True, "reasons": [], "next_actions": [], "policy_stage": "simulate"},
                    "daily_report": {"highlights": ["daily"]},
                    "weekly_report": {"highlights": ["weekly"]},
                    "live_acceptance": {
                        "ready_for_live": False,
                        "blockers": ["need more evidence"],
                        "acceptance_evidence": {"current_clean_day_streak": 2, "current_clean_week_streak": 0},
                        "next_requirement": {"remaining_clean_days": 26, "remaining_clean_weeks": 4},
                    },
                    "rollout": {"current_recommendation": "simulate", "blockers": ["need more evidence"]},
                    "operations": {"ready": False},
                    "data_quality": {"ready": False},
                    "market_awareness": {"overall_regime": "neutral", "actions": []},
                    "recent_orders": [{"broker_order_id": "order-1"}],
                    "candidate_scorecard": {
                        "rows": [
                            {
                                "strategy_id": "strategy_a_etf_rotation",
                                "action": "paper_only",
                                "promotion_blocked": True,
                                "blocking_reasons": ["history incomplete"],
                            }
                        ],
                        "next_actions": [],
                        "accepted_strategy_ids": [],
                        "portfolio_metrics": {},
                        "portfolio_passed": False,
                    },
                    "active_strategy_ids": ["strategy_a_etf_rotation"],
                    "selection_summary": {"active": [], "paper_only": []},
                    "allocation_summary": {"active": [], "paper_only": []},
                }

        app_state.dashboard_queries = _StubDashboardQueries()
        payload = facade.build_summary(date.today())

        assert payload.details["recent_orders"][0]["broker_order_id"] == "order-1"
        assert payload.summaries["daily"]["highlights"] == ["daily"]
        assert payload.strategies["blocked_by_data_count"] == 1
        assert payload.trading_plan["market_awareness"]["overall_regime"] == "neutral"
    finally:
        app_state.dashboard_queries = original_dashboard_queries
        app_state.execution_gate_summary = original_execution_gate_summary
        app_state.operations_period_report = original_operations_period_report
        app_state.live_acceptance_summary = original_live_acceptance_summary
        app_state.operations_rollout = original_operations_rollout
        app_state.operations_readiness = original_operations_readiness
        app_state.data_quality_summary = original_data_quality_summary
        app_state.active_execution_strategy_ids = original_active_execution_strategy_ids
        app_state.selection.summary = original_selection_summary
        app_state.allocations.summary = original_allocation_summary


def test_dashboard_facade_strategies_derives_mixed_statuses_and_counts():
    facade = app_state.dashboard_facade

    strategy_report = {
        "rows": [
            {
                "strategy_id": "strategy_c_option_overlay",
                "action": "paper_only",
                "promotion_blocked": True,
                "blocking_reasons": ["history incomplete"],
            },
            {
                "strategy_id": "strategy_b_equity_momentum",
                "action": "keep",
                "promotion_blocked": False,
                "blocking_reasons": [],
            },
            {
                "strategy_id": "strategy_a_etf_rotation",
                "action": "keep",
                "promotion_blocked": False,
                "blocking_reasons": [],
            },
        ],
        "next_actions": [],
        "accepted_strategy_ids": ["strategy_a_etf_rotation"],
        "portfolio_metrics": {"annualized_return": 0.1},
        "portfolio_passed": False,
    }
    dashboard_context = {
        "active_strategy_ids": [
            "strategy_c_option_overlay",
            "strategy_b_equity_momentum",
            "strategy_a_etf_rotation",
        ],
        "selection_summary": {"active": ["strategy_a_etf_rotation"], "paper_only": ["strategy_b_equity_momentum"]},
        "allocation_summary": {"active": [], "paper_only": []},
    }

    payload = facade._strategies(strategy_report, dashboard_context)
    rows = {row["strategy_id"]: row for row in payload["rows"]}

    assert rows["strategy_c_option_overlay"]["display_status"] == "blocked_by_data"
    assert rows["strategy_c_option_overlay"]["status_reason"] == "history incomplete"
    assert rows["strategy_b_equity_momentum"]["display_status"] == "paper_only"
    assert rows["strategy_b_equity_momentum"]["status_reason"] == "Selection/allocation keeps this strategy in paper-only mode."
    assert rows["strategy_a_etf_rotation"]["display_status"] == "active"
    assert rows["strategy_a_etf_rotation"]["status_reason"] == "Current execution set includes this strategy."
    assert payload["blocked_by_data_count"] == 1
    assert payload["paper_only_count"] == 1


def test_dashboard_facade_strategies_uses_blocked_reason_fallback_and_all_paper_only_paths():
    facade = app_state.dashboard_facade

    strategy_report = {
        "rows": [
            {
                "strategy_id": "strategy_c_option_overlay",
                "action": "paper_only",
                "promotion_blocked": True,
                "blocking_reasons": [
                    "Research data is blocked, but no specific blocker was recorded."
                ],
            },
            {
                "strategy_id": "strategy_b_equity_momentum",
                "action": "keep",
                "promotion_blocked": False,
                "blocking_reasons": [],
            },
            {
                "strategy_id": "strategy_a_etf_rotation",
                "action": "keep",
                "promotion_blocked": False,
                "blocking_reasons": [],
            },
            {
                "strategy_id": "strategy_g_jianfang_3l",
                "action": "paper_only",
                "promotion_blocked": False,
                "blocking_reasons": [],
            },
        ],
        "next_actions": [],
        "accepted_strategy_ids": [],
        "portfolio_metrics": {},
        "portfolio_passed": False,
    }
    dashboard_context = {
        "active_strategy_ids": [
            "strategy_c_option_overlay",
            "strategy_b_equity_momentum",
            "strategy_a_etf_rotation",
            "strategy_g_jianfang_3l",
        ],
        "selection_summary": {"active": [], "paper_only": ["strategy_b_equity_momentum"]},
        "allocation_summary": {
            "active": [],
            "paper_only": [{"strategy_id": "strategy_a_etf_rotation", "target_weight": 0.0}],
        },
    }

    payload = facade._strategies(strategy_report, dashboard_context)
    rows = {row["strategy_id"]: row for row in payload["rows"]}

    assert rows["strategy_c_option_overlay"]["display_status"] == "blocked_by_data"
    assert rows["strategy_c_option_overlay"]["status_reason"]
    assert rows["strategy_b_equity_momentum"]["display_status"] == "paper_only"
    assert rows["strategy_a_etf_rotation"]["display_status"] == "paper_only"
    assert rows["strategy_g_jianfang_3l"]["display_status"] == "paper_only"
    assert payload["blocked_by_data_count"] == 1
    assert payload["paper_only_count"] == 3

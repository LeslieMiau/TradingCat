from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from tradingcat.api.view_models import (
    AccountSummaryView,
    DashboardSummaryResponse,
    OperationsReadinessResponse,
    PlanItemView,
    PositionView,
    ResearchScorecardResponse,
)
from tradingcat.domain.models import ApprovalRequest, DailyTradingPlanNote, DailyTradingSummaryNote, Market, PortfolioSnapshot
from tradingcat.strategies.simple import strategy_metadata

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


_ACCOUNT_LABELS = {
    "total": "总账户",
    Market.CN.value: "A股账户",
    Market.HK.value: "港股账户",
    Market.US.value: "美股账户",
}


class DashboardFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def build_summary(self, as_of: date | None = None) -> DashboardSummaryResponse:
        evaluation_date = as_of or date.today()
        snapshot = self._app.portfolio.current_snapshot()
        projections = self._app.portfolio_projections
        plan_note = self._ensure_plan_note(evaluation_date)
        summary_note = self._ensure_summary_note(evaluation_date)
        gate = self._normalize_gate(self._app.execution_gate_summary(evaluation_date))
        daily_report = self._app.operations_period_report(window_days=1, label="daily")
        weekly_report = self._app.operations_period_report(window_days=7, label="weekly")
        live_acceptance = self._app.live_acceptance_summary(evaluation_date)
        rollout = self._app.operations_rollout()
        operations = self._app.operations_readiness()
        recent_orders = self._recent_orders()
        plan_items = [PlanItemView.model_validate(item) for item in plan_note.items]
        approvals = self._approval_rows()
        strategy_signals = self._app.strategy_signal_map(evaluation_date, include_candidates=True)
        candidate_scorecard = self._app.strategy_analysis.build_profit_scorecard(
            evaluation_date,
            strategy_signals,
        )

        payload = DashboardSummaryResponse(
            as_of=evaluation_date,
            overview=self._overview(snapshot),
            assets={
                "position_value": round(sum(position.market_value for position in snapshot.positions), 4),
                "cash": snapshot.cash,
                "positions": [projections.serialize_position(position) for position in snapshot.positions],
            },
            accounts=self._accounts(snapshot, plan_items),
            strategies=self._strategies(candidate_scorecard, candidate_scorecard),
            candidates=self._candidate_summary(candidate_scorecard),
            trading_plan=self._trading_plan_summary(plan_note, plan_items, approvals, gate),
            journal=self._journal_summary(plan_note, summary_note),
            summaries=self._summaries_summary(plan_note, summary_note, daily_report, weekly_report),
            details=self._details_summary(gate, live_acceptance, rollout, operations, recent_orders),
        )
        return payload

    def _ensure_plan_note(self, evaluation_date: date):
        note = self._app.trading_journal.latest_plan(as_of=evaluation_date)
        if note is not None and all("intent_id" in item and "target_weight" in item for item in note.items):
            return note
        return DailyTradingPlanNote(
            as_of=evaluation_date,
            status="no_trade",
            headline="No archived trading plan is available for this date yet.",
            reasons=["Generate or archive a daily trading plan to populate this panel."],
            metrics={"source": "dashboard_fallback"},
            items=[],
        )

    def _ensure_summary_note(self, evaluation_date: date):
        note = self._app.trading_journal.latest_summary(as_of=evaluation_date)
        return note or DailyTradingSummaryNote(
            as_of=evaluation_date,
            headline="No archived daily summary is available for this date yet.",
            highlights=["Generate a daily summary after review to populate this panel."],
            next_actions=["Run the summary/archive flow after the daily review closes."],
            metrics={"source": "dashboard_fallback"},
        )

    def _overview(self, snapshot: PortfolioSnapshot) -> dict[str, object]:
        return {
            "as_of": snapshot.timestamp.date(),
            "nav": snapshot.nav,
            "cash": snapshot.cash,
            "drawdown": snapshot.drawdown,
            "daily_pnl": snapshot.daily_pnl,
            "weekly_pnl": snapshot.weekly_pnl,
            "position_count": len(snapshot.positions),
            "total_position_value": round(sum(position.market_value for position in snapshot.positions), 4),
            "cash_ratio": round(snapshot.cash / snapshot.nav, 4) if snapshot.nav else None,
        }

    @staticmethod
    def _candidate_summary(candidate_scorecard: dict[str, object]) -> dict[str, object]:
        return {
            **candidate_scorecard,
            "top_candidates": candidate_scorecard.get("rows", [])[:5],
        }

    def _trading_plan_summary(
        self,
        plan_note,
        plan_items: list[PlanItemView],
        approvals: dict[str, list[dict[str, object]]],
        gate: dict[str, object],
    ) -> dict[str, object]:
        return {
            "status": plan_note.status,
            "headline": plan_note.headline,
            "reasons": plan_note.reasons,
            "counts": plan_note.counts,
            "items": [item.model_dump(mode="json") for item in plan_items],
            "signal_count": int(plan_note.counts.get("signal_count", 0)),
            "intent_count": int(plan_note.counts.get("intent_count", 0)),
            "manual_count": int(plan_note.counts.get("manual_count", 0)),
            "automated_count": max(0, int(plan_note.counts.get("intent_count", 0)) - int(plan_note.counts.get("manual_count", 0))),
            "pending_approvals": approvals["pending"],
            "recent_approvals": approvals["recent"],
            "gate": gate,
        }

    def _journal_summary(self, plan_note, summary_note) -> dict[str, object]:
        return {
            "latest_plan": plan_note.model_dump(mode="json"),
            "latest_summary": summary_note.model_dump(mode="json"),
            "recent_plans": [note.model_dump(mode="json") for note in self._app.trading_journal.list_plans()[:7]],
            "recent_summaries": [note.model_dump(mode="json") for note in self._app.trading_journal.list_summaries()[:7]],
        }

    @staticmethod
    def _summaries_summary(
        plan_note,
        summary_note,
        daily_report: dict[str, object],
        weekly_report: dict[str, object],
    ) -> dict[str, object]:
        return {
            "plan": plan_note.model_dump(mode="json"),
            "summary": summary_note.model_dump(mode="json"),
            "daily": daily_report,
            "weekly": weekly_report,
        }

    def _details_summary(
        self,
        gate: dict[str, object],
        live_acceptance: dict[str, object],
        rollout: dict[str, object],
        operations: dict[str, object],
        recent_orders: list[dict[str, object]],
    ) -> dict[str, object]:
        acceptance_progress = {
            "current_clean_day_streak": live_acceptance.get("acceptance_evidence", {}).get("current_clean_day_streak"),
            "current_clean_week_streak": live_acceptance.get("acceptance_evidence", {}).get("current_clean_week_streak"),
            "remaining_clean_days": live_acceptance.get("next_requirement", {}).get("remaining_clean_days"),
            "remaining_clean_weeks": live_acceptance.get("next_requirement", {}).get("remaining_clean_weeks"),
            "next_requirement": live_acceptance.get("next_requirement", {}),
            "blockers": list(live_acceptance.get("blockers", [])) or list(rollout.get("blockers", [])),
        }
        return {
            "execution_gate": gate,
            "live_acceptance": live_acceptance,
            "acceptance_progress": acceptance_progress,
            "data_quality": self._app.data_quality_summary(),
            "operations": operations,
            "recent_orders": recent_orders,
            "broker_order_check": {},
        }

    def _accounts(self, snapshot: PortfolioSnapshot, plan_items: list[PlanItemView]) -> dict[str, AccountSummaryView]:
        projections = self._app.portfolio_projections
        curves = projections.account_curves()
        cash_map = projections.account_cash_map(snapshot)
        accounts: dict[str, AccountSummaryView] = {}
        for account in projections.account_keys():
            positions = projections.account_positions(snapshot, account)
            nav = snapshot.nav if account == "total" else round(
                sum(position.market_value for position in snapshot.positions if position.instrument.market.value == account) + cash_map.get(account, 0.0),
                4,
            )
            position_value = round(sum(position["market_value"] for position in positions), 4)
            curve = curves.get(account, [])
            start_value = float(curve[0]["v"]) if curve else nav
            total_return = self._safe_ratio(nav - start_value, start_value)
            account_plan_items = [item for item in plan_items if account == "total" or item.market == account]
            allocation_mix = projections.allocation_mix(position_value, cash_map.get(account, 0.0), positions, nav)
            accounts[account] = AccountSummaryView(
                account=account,
                label=_ACCOUNT_LABELS[account],
                nav=nav,
                cash=cash_map.get(account, 0.0),
                cash_weight=self._safe_ratio(cash_map.get(account, 0.0), nav),
                cash_ratio=self._safe_ratio(cash_map.get(account, 0.0), nav),
                total_return=total_return,
                drawdown=snapshot.drawdown,
                daily_pnl=snapshot.daily_pnl,
                weekly_pnl=snapshot.weekly_pnl,
                position_count=len(positions),
                position_value=position_value,
                positions=[PositionView.model_validate(position) for position in positions],
                nav_curve=curve,
                allocation_mix=allocation_mix,
                plan_items=account_plan_items,
            )
        return accounts

    def _strategies(self, strategy_report: dict[str, object], candidate_scorecard: dict[str, object]) -> dict[str, object]:
        active_ids = set(self._app.active_execution_strategy_ids())
        selection_summary = self._app.selection.summary()
        allocation_summary = self._app.allocations.summary()
        selection_paper_only_ids = set(selection_summary.get("paper_only", []))
        allocation_paper_only_ids = {
            str(item.get("strategy_id"))
            for item in allocation_summary.get("paper_only", [])
            if item.get("strategy_id") is not None
        }
        rows = []
        for row in candidate_scorecard.get("rows", []):
            if row.get("strategy_id") not in active_ids:
                continue
            meta = strategy_metadata(str(row.get("strategy_id")))
            strategy_id = str(row.get("strategy_id"))
            blocked_by_data = bool(row.get("promotion_blocked"))
            selection_paper_only = strategy_id in selection_paper_only_ids
            allocation_paper_only = strategy_id in allocation_paper_only_ids
            display_status = (
                "blocked_by_data"
                if blocked_by_data
                else "paper_only"
                if selection_paper_only or allocation_paper_only or row.get("action") == "paper_only"
                else "active"
            )
            status_reason = (
                (row.get("blocking_reasons") or [None])[0]
                if blocked_by_data
                else "Selection/allocation keeps this strategy in paper-only mode."
                if display_status == "paper_only"
                else "Current execution set includes this strategy."
            )
            rows.append(
                {
                    **row,
                    **meta,
                    "markets": list(meta.get("focus_markets", [])),
                    "action": "active" if row.get("strategy_id") in active_ids else row.get("action"),
                    "display_status": display_status,
                    "status_reason": status_reason,
                }
            )
        return {
            "selection": selection_summary,
            "allocations": allocation_summary,
            "rows": rows,
            "next_actions": candidate_scorecard.get("next_actions", []),
            "active_count": len(rows),
            "blocked_by_data_count": sum(1 for row in rows if row.get("display_status") == "blocked_by_data"),
            "paper_only_count": sum(1 for row in rows if row.get("display_status") == "paper_only"),
            "accepted_strategy_ids": strategy_report.get("accepted_strategy_ids", []),
            "portfolio_metrics": strategy_report.get("portfolio_metrics", {}),
            "portfolio_passed": strategy_report.get("portfolio_passed", False),
        }

    def _recent_orders(self, limit: int = 20) -> list[dict[str, object]]:
        orders = sorted(self._app.execution.list_orders(), key=lambda item: item.timestamp, reverse=True)[:limit]
        rows: list[dict[str, object]] = []
        for order in orders:
            context = self._app.execution.resolve_intent_context(order.order_intent_id) or {}
            price_context = self._app.execution.resolve_price_context(order.order_intent_id)
            rows.append(
                {
                    **order.model_dump(mode="json"),
                    "symbol": context.get("symbol"),
                    "market": context.get("market"),
                    "asset_class": context.get("asset_class"),
                    "strategy_id": context.get("strategy_id"),
                    "expected_price": price_context.get("expected_price"),
                    "realized_price": price_context.get("realized_price"),
                    "reference_source": price_context.get("reference_source"),
                }
            )
        return rows

    def _approval_rows(self) -> dict[str, list[dict[str, object]]]:
        requests = self._app.approvals.list_requests()
        rows = [self._serialize_approval(item) for item in requests]
        return {
            "pending": [row for row in rows if row["status"] == "pending"],
            "recent": rows[:10],
        }

    def _serialize_approval(self, request: ApprovalRequest) -> dict[str, object]:
        intent = request.order_intent
        signal_id = intent.signal_id or ""
        strategy_id = signal_id.split(":", 1)[0] if ":" in signal_id else (signal_id or "manual_trader")
        return {
            "id": request.id,
            "intent_id": intent.id,
            "strategy_id": strategy_id,
            "symbol": intent.instrument.symbol,
            "market": intent.instrument.market.value,
            "side": intent.side.value,
            "quantity": intent.quantity,
            "status": request.status.value,
            "reason": request.decision_reason or intent.notes,
            "created_at": request.created_at,
            "decided_at": request.decided_at,
            "expires_at": request.expires_at,
            "requires_approval": intent.requires_approval,
        }

    @staticmethod
    def _normalize_gate(gate: dict[str, object]) -> dict[str, object]:
        reasons = [
            {"type": "gate", "detail": item} if isinstance(item, str) else item
            for item in gate.get("reasons", [])
        ]
        return {**gate, "reasons": reasons}

    @staticmethod
    def _safe_ratio(numerator: float | None, denominator: float | None) -> float | None:
        if numerator is None or denominator in (None, 0):
            return None
        return round(float(numerator) / float(denominator), 6)


class ResearchFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def scorecard(self, as_of: date, *, include_candidates: bool) -> ResearchScorecardResponse:
        payload = self._app.research_queries.scorecard(as_of, include_candidates=include_candidates)
        return ResearchScorecardResponse.model_validate(payload)

    def report(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.report(as_of)

    def stability(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.stability(as_of)

    def recommendations(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.recommendations(as_of)

    def ideas(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.ideas(as_of)

    def run_backtests(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.run_backtests(as_of)

    def strategy_detail(self, strategy_id: str, as_of: date) -> dict[str, object]:
        return self._app.research_queries.strategy_detail(strategy_id, as_of)

    async def asset_correlation(self, symbols: list[str], days: int) -> dict[str, object]:
        return await self._app.research_queries.asset_correlation(symbols, days)

    def summarize_news(self, items: list[dict[str, object]]) -> dict[str, object]:
        return self._app.research_ideas.summarize_news(items)

    def review_selections(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.review_selections(as_of)

    def review_allocations(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.review_allocations(as_of)


class OperationsFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def readiness(self) -> OperationsReadinessResponse:
        return OperationsReadinessResponse.model_validate(self._app.operations_readiness())

    def risk_config(self) -> dict[str, object]:
        return self._app.risk.config_snapshot()

    def execution_metrics(self) -> dict[str, object]:
        return self._app.operations_execution_metrics()

    def tca(self) -> dict[str, object]:
        return self._app.operations_analytics.tca_summary(
            audit_metrics=self._app.audit.execution_metrics_summary(),
            execution_tca=self._app.execution.transaction_cost_summary(),
        )

    def daily_report(self) -> dict[str, object]:
        return self._app.operations_period_report(window_days=1, label="daily")

    def weekly_report(self) -> dict[str, object]:
        return self._app.operations_period_report(window_days=7, label="weekly")

    def postmortem(self, window_days: int) -> dict[str, object]:
        return self._app.operations_postmortem(window_days)

    def incident_replay(self, window_days: int) -> dict[str, object]:
        return self._app.incident_replay(window_days)

    def record_journal(self) -> dict[str, object]:
        return self._app.record_operations_journal()

    def rollout(self) -> dict[str, object]:
        return self._app.operations_rollout()

    def rollout_checklist(self, stage: str | None, as_of: date | None) -> dict[str, object]:
        return self._app.rollout_checklist(stage, as_of)

    def rollout_policy_summary(self) -> dict[str, object]:
        return self._app.rollout_policy_summary()

    def apply_rollout_policy_recommendation(self) -> dict[str, object]:
        return self._app.rollout_policy.apply_recommendation(self._app.operations_rollout())

    def go_live(self, as_of: date | None = None) -> dict[str, object]:
        return self._app.go_live_summary(as_of)

    def live_acceptance(self, as_of: date | None = None, incident_window_days: int = 14) -> dict[str, object]:
        return self._app.live_acceptance_summary(as_of, incident_window_days)


class JournalFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def latest_plan(self, account: str = "total", as_of: date | None = None):
        note = self._app.trading_journal.latest_plan(account=account, as_of=as_of)
        return note or self._app.generate_daily_trading_plan(as_of or date.today(), account=account)

    def generate_plan(self, as_of: date | None = None):
        return self._app.generate_daily_trading_plan(as_of or date.today())

    def latest_summary(self, account: str = "total", as_of: date | None = None):
        note = self._app.trading_journal.latest_summary(account=account, as_of=as_of)
        return note or self._app.generate_daily_trading_summary(as_of or date.today())

    def generate_summary(self, as_of: date | None = None):
        return self._app.generate_daily_trading_summary(as_of or date.today())


class AlertsFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def evaluate(self) -> dict[str, object]:
        broker_status_payload = self._app.broker_status()
        broker_validation = self._app.broker_validation()
        market_data = self._app.run_market_data_smoke_test()
        execution_reconciliation = self._app.execution.reconcile_live_state()
        portfolio_reconciliation = self._app.reconcile_portfolio_with_live_broker()
        return self._app.alerts.evaluate(
            broker_status_payload,
            broker_validation,
            market_data,
            execution_reconciliation,
            portfolio_reconciliation,
        )

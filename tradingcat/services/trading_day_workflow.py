from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from tradingcat.domain.models import Market
from tradingcat.services.trading_session import TradingSessionService

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


class TradingDayWorkflowService:
    """Read-only trading-day cockpit aggregator."""

    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app
        self._sessions = TradingSessionService(app.market_calendar)

    def snapshot(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        generated_at = datetime.now(UTC)
        dashboard = self._safe_call("dashboard_summary", lambda: self._app.dashboard_summary(evaluation_date), {})
        operations = self._safe_call("operations_readiness", self._app.operations_readiness, {})
        data_quality = self._safe_call("data_quality_summary", self._app.data_quality_summary, {})
        markets = [self._market_snapshot(market, generated_at) for market in Market]
        blockers = self._blockers(operations, dashboard, data_quality)
        plan = (dashboard.get("journal", {}) or {}).get("latest_plan") if isinstance(dashboard, dict) else None
        summary = (dashboard.get("journal", {}) or {}).get("latest_summary") if isinstance(dashboard, dict) else None
        decision = self._decision(markets=markets, blockers=blockers, plan=plan)
        recent_orders = ((dashboard.get("details", {}) or {}).get("recent_orders", []) if isinstance(dashboard, dict) else [])
        return {
            "as_of": evaluation_date.isoformat(),
            "generated_at": generated_at.isoformat(),
            "markets": markets,
            "decision": decision,
            "pre_market": {
                "plan": plan,
                "market_awareness": ((dashboard.get("details", {}) or {}).get("market_awareness", {}) if isinstance(dashboard, dict) else {}),
                "blockers": blockers,
            },
            "intraday": {
                "insight_matrix": self._insight_matrix(markets, recent_orders, plan, dashboard),
                "recent_orders": recent_orders,
                "execution_gate": ((dashboard.get("details", {}) or {}).get("execution_gate", {}) if isinstance(dashboard, dict) else {}),
            },
            "post_market": {
                "summary": summary,
                "execution_review": self._execution_review(recent_orders),
            },
            "provenance": [
                {"source_service": "DashboardFacade", "source_field": "dashboard_summary"},
                {"source_service": "ReadinessQueryService", "source_field": "operations_readiness"},
                {"source_service": "DataQualityQueryService", "source_field": "data_quality_summary"},
                {"source_service": "MarketStateService", "source_field": "latest_or_snapshot"},
            ],
        }

    def _market_snapshot(self, market: Market, observed_at: datetime) -> dict[str, object]:
        phase = self._safe_call(
            f"{market.value}.phase",
            lambda: self._sessions.get_phase(market, now=observed_at),
            None,
        )
        market_state = self._safe_call(
            f"{market.value}.market_state",
            lambda: self._app.market_state.latest_or_snapshot(market=market).model_dump(mode="json"),
            {},
        )
        return {
            "market": market.value,
            "label": {"CN": "A股", "HK": "港股", "US": "美股"}[market.value],
            "phase": getattr(getattr(phase, "phase", None), "value", "unknown"),
            "local_date": str(getattr(phase, "local_date", date.today())),
            "is_trading_day": bool(getattr(getattr(phase, "underlying_session", None), "is_trading_day", False)),
            "state": {
                "bias_label": market_state.get("bias_label"),
                "risk_score": market_state.get("risk_score"),
                "confidence": market_state.get("confidence"),
                "blockers": market_state.get("blockers", []),
            },
            "source_service": "MarketStateService",
            "source_field": f"market_state.{market.value}",
        }

    def _decision(
        self,
        *,
        markets: list[dict[str, object]],
        blockers: list[dict[str, object]],
        plan: object,
    ) -> dict[str, object]:
        tradable_markets = [row["market"] for row in markets if row.get("is_trading_day")]
        plan_status = plan.get("status") if isinstance(plan, dict) else None
        if blockers:
            status = "blocked"
            next_step = "先处理阻塞项，再考虑计划或执行。"
        elif not tradable_markets:
            status = "no_trade"
            next_step = "等待下一个交易时段，或只做研究复盘。"
        elif plan_status == "planned":
            status = "ready"
            next_step = "查看计划条目和待审批事项，保持人工确认边界。"
        else:
            status = "watch"
            next_step = "先确认市场状态和计划归档，再决定是否进入执行流程。"
        return {
            "status": status,
            "tradable_markets": tradable_markets,
            "why": [item["detail"] for item in blockers[:5]] or ([plan.get("headline")] if isinstance(plan, dict) and plan.get("headline") else []),
            "next_step": next_step,
            "blockers": blockers,
        }

    def _blockers(
        self,
        operations: dict[str, object],
        dashboard: dict[str, object],
        data_quality: dict[str, object],
    ) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for item in operations.get("blockers", []) if isinstance(operations, dict) else []:
            rows.append({"detail": str(item), "source_service": "ReadinessQueryService", "source_field": "operations_readiness.blockers"})
        gate = ((dashboard.get("details", {}) or {}).get("execution_gate", {}) if isinstance(dashboard, dict) else {})
        for reason in gate.get("reasons", []) if isinstance(gate, dict) else []:
            detail = reason.get("detail") if isinstance(reason, dict) else reason
            rows.append({"detail": str(detail), "source_service": "DashboardFacade", "source_field": "details.execution_gate.reasons"})
        for item in data_quality.get("blockers", []) if isinstance(data_quality, dict) else []:
            rows.append({"detail": str(item), "source_service": "DataQualityQueryService", "source_field": "data_quality.blockers"})
        unique: list[dict[str, object]] = []
        seen: set[str] = set()
        for row in rows:
            detail = str(row["detail"])
            if detail and detail not in seen:
                unique.append(row)
                seen.add(detail)
        return unique

    def _insight_matrix(
        self,
        markets: list[dict[str, object]],
        recent_orders: object,
        plan: object,
        dashboard: dict[str, object],
    ) -> dict[str, object]:
        order_rows = recent_orders if isinstance(recent_orders, list) else []
        plan_items = list(plan.get("items", []) if isinstance(plan, dict) else [])
        positions = self._position_rows()
        approvals = self._approval_rows()
        insights = self._insight_rows()
        gate = ((dashboard.get("details", {}) or {}).get("execution_gate", {}) if isinstance(dashboard, dict) else {})
        market_by_symbol = self._symbol_market_index(plan_items, positions, order_rows, approvals, insights)
        plan_by_symbol = self._group_by_symbol(plan_items)
        orders_by_symbol = self._group_by_symbol(order_rows)
        positions_by_symbol = self._group_by_symbol(positions)
        approvals_by_symbol = self._group_by_symbol(approvals)
        insights_by_symbol: dict[str, list[dict[str, object]]] = {}
        for insight in insights:
            for subject in insight.get("subjects", []) or [""]:
                symbol = str(subject).upper()
                if symbol:
                    insights_by_symbol.setdefault(symbol, []).append(insight)

        ordered_symbols = self._ordered_matrix_symbols(insights_by_symbol, plan_by_symbol, orders_by_symbol, positions_by_symbol)
        rows: list[dict[str, object]] = []
        for symbol in ordered_symbols[:30]:
            market = market_by_symbol.get(symbol)
            market_state = self._market_state_for_symbol(markets, market)
            plan_item = (plan_by_symbol.get(symbol) or [None])[0]
            order = (orders_by_symbol.get(symbol) or [None])[0]
            approval = (approvals_by_symbol.get(symbol) or [None])[0]
            position = (positions_by_symbol.get(symbol) or [None])[0]
            insight_rows = insights_by_symbol.get(symbol, [])
            rows.append(
                {
                    "symbol": symbol,
                    "market": market,
                    "relation_type": self._relation_type(insight_rows, position, plan_item, order, approval),
                    "causal_chain": self._causal_chain_for_row(insight_rows, market_state, plan_item, order, approval),
                    "insights": insight_rows,
                    "market_state": market_state,
                    "position": position,
                    "plan_item": plan_item,
                    "order_intent": self._order_intent_from(plan_item, approval),
                    "order": order,
                    "approval": approval,
                    "risk_rules": self._risk_rules_for_row(
                        symbol=symbol,
                        market_state=market_state,
                        plan_item=plan_item,
                        order=order,
                        approval=approval,
                        gate=gate,
                    ),
                    "source_service": "TradingDayWorkflowService",
                    "source_field": "intraday.insight_matrix.rows",
                }
            )
        return {
            "market_count": len(markets),
            "recent_order_count": len(order_rows),
            "insight_count": len(insights),
            "row_count": len(rows),
            "risk_markets": [row["market"] for row in markets if (row.get("state") or {}).get("blockers")],
            "rows": rows,
            "counts": {
                "insights": len(insights),
                "plan_items": len(plan_items),
                "positions": len(positions),
                "orders": len(order_rows),
                "approvals": len(approvals),
                "linked_rows": len(rows),
            },
            "source_service": "TradingDayWorkflowService",
            "source_field": "intraday.insight_matrix",
        }

    def _position_rows(self) -> list[dict[str, object]]:
        snapshot = self._safe_call("portfolio.current_snapshot", self._app.portfolio.current_snapshot, None)
        positions = getattr(snapshot, "positions", []) if snapshot is not None else []
        rows: list[dict[str, object]] = []
        for position in positions:
            instrument = getattr(position, "instrument", None)
            symbol = getattr(instrument, "symbol", None)
            if not symbol:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "market": getattr(getattr(instrument, "market", None), "value", getattr(instrument, "market", None)),
                    "quantity": getattr(position, "quantity", 0.0),
                    "market_value": getattr(position, "market_value", 0.0),
                    "weight": getattr(position, "weight", 0.0),
                    "average_cost": getattr(position, "average_cost", 0.0),
                    "unrealized_pnl": getattr(position, "unrealized_pnl", None),
                    "unrealized_return": getattr(position, "unrealized_return", None),
                }
            )
        return rows

    def _approval_rows(self) -> list[dict[str, object]]:
        approvals = self._safe_call("approvals.list_requests", self._app.approvals.list_requests, [])
        rows: list[dict[str, object]] = []
        for approval in approvals if isinstance(approvals, list) else []:
            intent = getattr(approval, "order_intent", None)
            instrument = getattr(intent, "instrument", None)
            symbol = getattr(instrument, "symbol", None)
            if not symbol:
                continue
            rows.append(
                {
                    "id": getattr(approval, "id", None),
                    "intent_id": getattr(intent, "id", None),
                    "symbol": symbol,
                    "market": getattr(getattr(instrument, "market", None), "value", getattr(instrument, "market", None)),
                    "side": getattr(getattr(intent, "side", None), "value", getattr(intent, "side", None)),
                    "quantity": getattr(intent, "quantity", None),
                    "status": getattr(getattr(approval, "status", None), "value", getattr(approval, "status", None)),
                    "created_at": getattr(approval, "created_at", None),
                    "decided_at": getattr(approval, "decided_at", None),
                    "expires_at": getattr(approval, "expires_at", None),
                    "decision_reason": getattr(approval, "decision_reason", None),
                    "requires_approval": getattr(intent, "requires_approval", None),
                }
            )
        return rows

    def _insight_rows(self) -> list[dict[str, object]]:
        store = getattr(self._app, "insight_store", None)
        if store is None:
            return []
        insights = self._safe_call("insight_store.list", lambda: store.list(include_dismissed=False), [])
        rows: list[dict[str, object]] = []
        for insight in insights if isinstance(insights, list) else []:
            recommendation = getattr(insight, "recommendation", None)
            rows.append(
                {
                    "id": getattr(insight, "id", None),
                    "kind": getattr(getattr(insight, "kind", None), "value", getattr(insight, "kind", None)),
                    "severity": getattr(getattr(insight, "severity", None), "value", getattr(insight, "severity", None)),
                    "headline": getattr(insight, "headline", ""),
                    "subjects": [str(subject).upper() for subject in getattr(insight, "subjects", [])],
                    "confidence": getattr(insight, "confidence", 0.0),
                    "triggered_at": getattr(insight, "triggered_at", None),
                    "expires_at": getattr(insight, "expires_at", None),
                    "user_action": getattr(getattr(insight, "user_action", None), "value", getattr(insight, "user_action", None)),
                    "causal_chain": [
                        evidence.model_dump(mode="json")
                        for evidence in getattr(insight, "causal_chain", [])
                        if hasattr(evidence, "model_dump")
                    ],
                    "recommendation": recommendation.model_dump(mode="json") if hasattr(recommendation, "model_dump") else None,
                }
            )
        return rows

    @staticmethod
    def _relation_type(
        insights: list[dict[str, object]],
        position: dict[str, object] | None,
        plan_item: dict[str, object] | None,
        order: dict[str, object] | None,
        approval: dict[str, object] | None,
    ) -> str:
        parts: list[str] = []
        if insights:
            parts.append("insight")
        if position:
            parts.append("position")
        if plan_item:
            parts.append("plan_item")
        if order:
            parts.append("order")
        if approval:
            parts.append("approval")
        return "+".join(parts) if parts else "unlinked"

    @staticmethod
    def _causal_chain_for_row(
        insights: list[dict[str, object]],
        market_state: dict[str, object] | None,
        plan_item: dict[str, object] | None,
        order: dict[str, object] | None,
        approval: dict[str, object] | None,
    ) -> list[dict[str, object]]:
        chain: list[dict[str, object]] = []
        for insight in insights:
            for evidence in insight.get("causal_chain", []) if isinstance(insight, dict) else []:
                if isinstance(evidence, dict):
                    chain.append(evidence)
            chain.append(
                {
                    "source": "InsightStore",
                    "fact": "insight",
                    "value": {
                        "id": insight.get("id"),
                        "kind": insight.get("kind"),
                        "severity": insight.get("severity"),
                        "headline": insight.get("headline"),
                    },
                    "observed_at": insight.get("triggered_at"),
                }
            )
        if market_state:
            chain.append({"source": "MarketStateService", "fact": "market_state", "value": market_state, "observed_at": None})
        if plan_item:
            chain.append({"source": "TradingJournalService", "fact": "plan_item", "value": plan_item, "observed_at": None})
        if order:
            chain.append({"source": "ExecutionService", "fact": "order", "value": order, "observed_at": order.get("timestamp")})
        if approval:
            chain.append({"source": "ApprovalService", "fact": "approval", "value": approval, "observed_at": approval.get("created_at")})
        return chain[:12]

    @staticmethod
    def _symbol_market_index(
        plan_items: list[object],
        positions: list[dict[str, object]],
        orders: list[object],
        approvals: list[dict[str, object]],
        insights: list[dict[str, object]],
    ) -> dict[str, str]:
        market_by_symbol: dict[str, str] = {}
        for row in [*plan_items, *positions, *orders, *approvals]:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            market = row.get("market")
            if symbol and market:
                market_by_symbol.setdefault(symbol, str(market))
        for insight in insights:
            recommendation = insight.get("recommendation") or {}
            if isinstance(recommendation, dict) and recommendation.get("symbol"):
                symbol = str(recommendation["symbol"]).upper()
                market_by_symbol.setdefault(symbol, market_by_symbol.get(symbol, ""))
        return market_by_symbol

    @staticmethod
    def _group_by_symbol(rows: list[object]) -> dict[str, list[dict[str, object]]]:
        grouped: dict[str, list[dict[str, object]]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if symbol:
                grouped.setdefault(symbol, []).append(row)
        return grouped

    @staticmethod
    def _ordered_matrix_symbols(*groups: dict[str, list[dict[str, object]]]) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()
        for group in groups:
            for symbol in group:
                if symbol not in seen:
                    ordered.append(symbol)
                    seen.add(symbol)
        return ordered

    @staticmethod
    def _market_state_for_symbol(markets: list[dict[str, object]], market: str | None) -> dict[str, object] | None:
        if not market:
            return None
        for row in markets:
            if row.get("market") == market:
                return row.get("state") if isinstance(row.get("state"), dict) else None
        return None

    @staticmethod
    def _order_intent_from(plan_item: dict[str, object] | None, approval: dict[str, object] | None) -> dict[str, object] | None:
        if isinstance(plan_item, dict):
            return {
                "intent_id": plan_item.get("intent_id"),
                "strategy_id": plan_item.get("strategy_id"),
                "symbol": plan_item.get("symbol"),
                "market": plan_item.get("market"),
                "side": plan_item.get("side"),
                "quantity": plan_item.get("quantity"),
                "reference_price": plan_item.get("reference_price"),
                "reference_source": plan_item.get("reference_source"),
                "reference_quality": plan_item.get("reference_quality"),
                "requires_approval": plan_item.get("requires_approval"),
            }
        if isinstance(approval, dict):
            return {
                "intent_id": approval.get("intent_id"),
                "symbol": approval.get("symbol"),
                "market": approval.get("market"),
                "side": approval.get("side"),
                "quantity": approval.get("quantity"),
                "requires_approval": approval.get("requires_approval"),
            }
        return None

    @staticmethod
    def _risk_rules_for_row(
        *,
        symbol: str,
        market_state: dict[str, object] | None,
        plan_item: dict[str, object] | None,
        order: dict[str, object] | None,
        approval: dict[str, object] | None,
        gate: dict[str, object],
    ) -> list[dict[str, object]]:
        rules: list[dict[str, object]] = []
        for blocker in (market_state or {}).get("blockers", []) if isinstance(market_state, dict) else []:
            rules.append({"rule": "market_state_blocker", "detail": str(blocker), "source_field": "market_state.blockers"})
        if isinstance(plan_item, dict) and plan_item.get("requires_approval"):
            rules.append({"rule": "manual_approval_required", "detail": "Order intent requires manual approval.", "source_field": "plan_item.requires_approval"})
        reference_quality = str((plan_item or {}).get("reference_quality") or (order or {}).get("reference_quality") or "").lower()
        reference_source = str((plan_item or {}).get("reference_source") or (order or {}).get("reference_source") or "").lower()
        if any(token in reference_quality for token in ("synthetic", "degraded")) or "synthetic" in reference_source:
            rules.append({"rule": "synthetic_reference", "detail": "Quote reference is synthetic/degraded.", "source_field": "reference_quality"})
        if isinstance(approval, dict) and approval.get("status") in {"pending", "rejected", "expired"}:
            rules.append({"rule": "approval_state", "detail": f"Approval status is {approval.get('status')}.", "source_field": "approval.status"})
        if isinstance(order, dict) and order.get("status") in {"rejected", "cancelled"}:
            rules.append({"rule": "order_state", "detail": f"Order status is {order.get('status')}.", "source_field": "order.status"})
        for reason in gate.get("reasons", []) if isinstance(gate, dict) else []:
            detail = reason.get("detail") if isinstance(reason, dict) else reason
            if symbol and detail and symbol in str(detail).upper():
                rules.append({"rule": "execution_gate", "detail": str(detail), "source_field": "details.execution_gate.reasons"})
        return rules

    def _execution_review(self, recent_orders: object) -> dict[str, object]:
        orders = recent_orders if isinstance(recent_orders, list) else []
        return {
            "order_count": len(orders),
            "filled_count": sum(1 for row in orders if isinstance(row, dict) and row.get("status") in {"filled", "partially_filled"}),
            "unfilled_count": sum(1 for row in orders if isinstance(row, dict) and row.get("status") in {"submitted", "pending_approval"}),
            "quality": {},
            "tca": {},
            "source_service": "DashboardFacade",
            "source_field": "details.recent_orders",
        }

    @staticmethod
    def _safe_call(label: str, func, fallback):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{label} unavailable: {exc}"} if isinstance(fallback, dict) else fallback

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

from tradingcat.domain.models import Market
from tradingcat.services.trading_session import TradingSessionService

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


class TradingDayWorkflowService:
    """Read-only trading-day cockpit aggregator."""

    _STATUS_RANK = {"ok": 0, "degraded": 1, "stale": 2, "offline": 3, "blocked": 4}

    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app
        self._sessions = TradingSessionService(app.market_calendar)

    def snapshot(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        generated_at = datetime.now(UTC)
        dashboard = self._safe_call("dashboard_summary", lambda: self._app.dashboard_summary(evaluation_date), {})
        operations = self._safe_call("operations_readiness", self._app.operations_readiness, {})
        data_quality = self._safe_call("data_quality_summary", self._app.data_quality_summary, {})
        broker = self._safe_call("broker_status", lambda: self._app.broker_status(), {})
        kill_switch = self._safe_call("kill_switch_status", lambda: self._app.risk.kill_switch_status(), {"enabled": False})
        scheduler_runs = self._safe_call("scheduler.run_history", lambda: self._app.scheduler.run_history(limit=20), [])
        scheduler_running = bool(self._safe_call("scheduler.is_running", lambda: self._app.scheduler.is_running, False))
        portfolio_snapshot = self._safe_call("portfolio.current_snapshot", self._app.portfolio.current_snapshot, None)
        order_state = self._safe_call("execution.order_state_summary", lambda: self._app.execution.order_state_summary(), {})
        authorization = self._safe_call("execution.authorization_summary", lambda: self._app.execution.authorization_summary(), {})
        ledger_latest = self._safe_call("trade_ledger_reconciliation.latest", lambda: self._app.trade_ledger_reconciliation.latest(), None)
        markets = [self._market_snapshot(market, generated_at) for market in Market]
        plan = (dashboard.get("journal", {}) or {}).get("latest_plan") if isinstance(dashboard, dict) else None
        summary = (dashboard.get("journal", {}) or {}).get("latest_summary") if isinstance(dashboard, dict) else None
        recent_orders = ((dashboard.get("details", {}) or {}).get("recent_orders", []) if isinstance(dashboard, dict) else [])
        approvals = self._approval_rows()
        heartbeat = self._heartbeat(
            generated_at=generated_at,
            broker=broker,
            data_quality=data_quality,
            portfolio_snapshot=portfolio_snapshot,
            recent_orders=recent_orders,
            order_state=order_state,
            scheduler_running=scheduler_running,
            scheduler_runs=scheduler_runs,
            ledger_latest=ledger_latest,
        )
        live_readiness = self._live_readiness(
            broker=broker,
            data_quality=data_quality,
            markets=markets,
            kill_switch=kill_switch,
            order_state=order_state,
            authorization=authorization,
            recent_orders=recent_orders,
        )
        blockers = self._dedupe_rows([*self._blockers(operations, dashboard, data_quality), *live_readiness["blockers"]])
        action_queue = self._action_queue(
            generated_at=generated_at,
            blockers=blockers,
            heartbeat=heartbeat,
            live_readiness=live_readiness,
            approvals=approvals,
            recent_orders=recent_orders,
            data_quality=data_quality,
            kill_switch=kill_switch,
            scheduler_runs=scheduler_runs,
            scheduler_running=scheduler_running,
            ledger_latest=ledger_latest,
        )
        decision = self._decision(markets=markets, blockers=blockers, plan=plan)
        return {
            "as_of": evaluation_date.isoformat(),
            "generated_at": generated_at.isoformat(),
            "markets": markets,
            "decision": decision,
            "heartbeat": heartbeat,
            "live_readiness": live_readiness,
            "action_queue": action_queue,
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
                {"source_service": "TradingDayWorkflowService", "source_field": "action_queue"},
                {"source_service": "TradingDayWorkflowService", "source_field": "heartbeat"},
                {"source_service": "TradingDayWorkflowService", "source_field": "live_readiness"},
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
        underlying = getattr(phase, "underlying_session", None)
        return {
            "market": market.value,
            "label": {"CN": "A股", "HK": "港股", "US": "美股"}[market.value],
            "phase": getattr(getattr(phase, "phase", None), "value", "unknown"),
            "local_date": str(getattr(phase, "local_date", date.today())),
            "is_trading_day": bool(getattr(underlying, "is_trading_day", False)),
            "session_type": getattr(underlying, "session_type", "unknown"),
            "calendar_source": getattr(underlying, "calendar_source", "unknown"),
            "calendar_note": getattr(underlying, "calendar_note", None),
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

    def _heartbeat(
        self,
        *,
        generated_at: datetime,
        broker: dict[str, object],
        data_quality: dict[str, object],
        portfolio_snapshot: object,
        recent_orders: object,
        order_state: dict[str, object],
        scheduler_running: bool,
        scheduler_runs: object,
        ledger_latest: object,
    ) -> dict[str, object]:
        orders = recent_orders if isinstance(recent_orders, list) else []
        components = [
            self._broker_component(broker, generated_at),
            self._account_component(portfolio_snapshot, generated_at),
            self._orders_component(orders, order_state),
            self._data_quality_component(data_quality),
            self._scheduler_component(scheduler_running, scheduler_runs),
            self._reconciliation_component(ledger_latest),
        ]
        counts: dict[str, int] = {status: 0 for status in self._STATUS_RANK}
        for component in components:
            counts[str(component["status"])] = counts.get(str(component["status"]), 0) + 1
        return {
            "generated_at": generated_at.isoformat(),
            "overall_status": self._worst_status([str(component["status"]) for component in components]),
            "components": components,
            "counts": counts,
            "source_service": "TradingDayWorkflowService",
            "source_field": "heartbeat",
        }

    def _live_readiness(
        self,
        *,
        broker: dict[str, object],
        data_quality: dict[str, object],
        markets: list[dict[str, object]],
        kill_switch: dict[str, object],
        order_state: dict[str, object],
        authorization: dict[str, object],
        recent_orders: object,
    ) -> dict[str, object]:
        blockers: list[dict[str, object]] = []
        broker_backend = str(broker.get("backend", "unknown")).lower() if isinstance(broker, dict) else "unknown"
        broker_healthy = bool(broker.get("healthy", False)) if isinstance(broker, dict) else False
        if not broker_healthy:
            blockers.append(self._blocker("Live broker is offline or unavailable.", "AdapterFactory", "broker_status.healthy"))
        if broker_backend in {"simulated", "manual", "unknown"}:
            blockers.append(self._blocker(f"Live broker backend is {broker_backend}; real broker is not active.", "AdapterFactory", "broker_status.backend"))

        if isinstance(data_quality, dict):
            for item in data_quality.get("blockers", []):
                blockers.append(self._blocker(str(item), "DataQualityQueryService", "data_quality.blockers"))
            for item in data_quality.get("fx_blockers", []):
                blockers.append(self._blocker(str(item), "DataQualityQueryService", "data_quality.fx_blockers"))
            for report in data_quality.get("reports", []) or []:
                if not isinstance(report, dict):
                    continue
                qualities = {str(item).lower() for item in report.get("qualities", []) or []}
                sources = {str(item).lower() for item in report.get("sources", []) or []}
                degraded = bool(report.get("synthetic") or report.get("degraded"))
                degraded = degraded or bool(qualities & {"synthetic", "degraded", "fallback"})
                degraded = degraded or "synthetic" in sources
                if degraded:
                    blockers.append(
                        self._blocker(
                            f"{report.get('symbol') or 'Instrument'} history uses synthetic/degraded data.",
                            "DataQualityQueryService",
                            "data_quality.reports",
                        )
                    )
            if data_quality.get("ready") is False and not data_quality.get("blockers"):
                blockers.append(self._blocker("Data quality summary is not live-ready.", "DataQualityQueryService", "data_quality.ready"))

        for row in markets:
            if row.get("session_type") == "calendar_unavailable" or not row.get("calendar_source"):
                blockers.append(
                    self._blocker(
                        f"{row.get('market')} exchange calendar is unavailable.",
                        "MarketCalendarService",
                        f"markets.{row.get('market')}.calendar_source",
                    )
                )

        if isinstance(kill_switch, dict) and bool(kill_switch.get("enabled", False)):
            blockers.append(self._blocker("Kill switch is active.", "RiskEngine", "kill_switch.enabled"))

        pending_reconcile = int(order_state.get("submitted", 0) or 0) + int(order_state.get("partially_filled", 0) or 0)
        if pending_reconcile:
            blockers.append(
                self._blocker(
                    f"{pending_reconcile} live order(s) still need reconciliation.",
                    "ExecutionService",
                    "order_state_summary.submitted",
                )
            )

        unauthorized = int(authorization.get("unauthorized_count", 0) or 0) if isinstance(authorization, dict) else 0
        if unauthorized:
            blockers.append(
                self._blocker(
                    f"{unauthorized} order(s) are missing a clean authorization state.",
                    "ExecutionService",
                    "authorization_summary.unauthorized_count",
                )
            )

        for row in recent_orders if isinstance(recent_orders, list) else []:
            if not isinstance(row, dict):
                continue
            quality = str(row.get("reference_quality") or "").lower()
            source = str(row.get("reference_source") or "").lower()
            if quality in {"synthetic", "degraded", "fallback"} or "synthetic" in source:
                blockers.append(
                    self._blocker(
                        f"{row.get('symbol') or row.get('order_intent_id') or 'Order'} uses synthetic/degraded quote reference.",
                        "ExecutionService",
                        "recent_orders.reference_quality",
                    )
                )

        blockers = self._dedupe_rows(blockers)
        return {
            "ready": len(blockers) == 0,
            "status": "ready" if not blockers else "blocked",
            "blockers": blockers,
            "source_service": "TradingDayWorkflowService",
            "source_field": "live_readiness",
        }

    def _action_queue(
        self,
        *,
        generated_at: datetime,
        blockers: list[dict[str, object]],
        heartbeat: dict[str, object],
        live_readiness: dict[str, object],
        approvals: list[dict[str, object]],
        recent_orders: object,
        data_quality: dict[str, object],
        kill_switch: dict[str, object],
        scheduler_runs: object,
        scheduler_running: bool,
        ledger_latest: object,
    ) -> dict[str, object]:
        actions: list[dict[str, object]] = []
        created_at = generated_at.isoformat()

        for blocker in blockers:
            actions.append(
                self._action(
                    key=f"blocker:{blocker.get('source_field')}:{blocker.get('detail')}",
                    severity="high" if blocker in live_readiness.get("blockers", []) else "medium",
                    category="readiness",
                    title="处理实盘阻塞",
                    detail=str(blocker.get("detail", "")),
                    source_service=str(blocker.get("source_service", "TradingDayWorkflowService")),
                    source_field=str(blocker.get("source_field", "decision.blockers")),
                    target_url="/dashboard/operations",
                    created_at=created_at,
                    status="open",
                )
            )

        if isinstance(kill_switch, dict) and kill_switch.get("enabled"):
            actions.append(
                self._action(
                    key="risk:kill_switch",
                    severity="high",
                    category="risk",
                    title="Kill switch 已开启",
                    detail=str((kill_switch.get("latest") or {}).get("reason") if isinstance(kill_switch.get("latest"), dict) else "Kill switch is active."),
                    source_service="RiskEngine",
                    source_field="kill_switch.enabled",
                    target_url="/dashboard/operations",
                    created_at=created_at,
                    status="open",
                )
            )

        for approval in approvals:
            if approval.get("status") == "pending":
                actions.append(
                    self._action(
                        key=f"approval:{approval.get('id')}",
                        severity="medium",
                        category="approval",
                        title="处理待审批订单",
                        detail=f"{approval.get('symbol')} {approval.get('side')} {approval.get('quantity')} requires manual approval.",
                        source_service="ApprovalService",
                        source_field="approvals.pending",
                        target_url="/dashboard",
                        created_at=self._iso(approval.get("created_at")) or created_at,
                        status="open",
                    )
                )

        for row in recent_orders if isinstance(recent_orders, list) else []:
            if not isinstance(row, dict):
                continue
            status = str(row.get("status") or "").lower()
            if status in {"submitted", "partially_filled", "pending_approval"}:
                category = "manual_fill" if str(row.get("broker_order_id", "")).startswith("manual-") else "reconciliation"
                actions.append(
                    self._action(
                        key=f"order:{row.get('order_intent_id') or row.get('broker_order_id')}",
                        severity="high" if status == "partially_filled" else "medium",
                        category=category,
                        title="跟进未完成订单",
                        detail=f"{row.get('symbol') or row.get('order_intent_id')} is {status}; verify fill/reconcile state.",
                        source_service="ExecutionService",
                        source_field="recent_orders.status",
                        target_url="/dashboard",
                        created_at=self._iso(row.get("timestamp")) or created_at,
                        status="open",
                    )
                )

        if isinstance(data_quality, dict):
            for item in data_quality.get("fx_blockers", []):
                actions.append(
                    self._action(
                        key=f"fx:{item}",
                        severity="high",
                        category="data_quality",
                        title="修复 FX 数据质量",
                        detail=str(item),
                        source_service="DataQualityQueryService",
                        source_field="data_quality.fx_blockers",
                        target_url="/dashboard/operations",
                        created_at=created_at,
                        status="open",
                    )
                )

        for component in heartbeat.get("components", []) if isinstance(heartbeat, dict) else []:
            if not isinstance(component, dict):
                continue
            status = str(component.get("status", "ok"))
            if status not in {"degraded", "stale", "offline", "blocked"}:
                continue
            actions.append(
                self._action(
                    key=f"heartbeat:{component.get('id')}",
                    severity="high" if status in {"offline", "blocked"} else "medium",
                    category=str(component.get("id") or "heartbeat"),
                    title=f"{component.get('label')} 状态异常",
                    detail=str(component.get("detail") or status),
                    source_service=str(component.get("source_service") or "TradingDayWorkflowService"),
                    source_field=str(component.get("source_field") or "heartbeat.components"),
                    target_url=str(component.get("target_url") or "/dashboard/operations"),
                    created_at=str(component.get("observed_at") or created_at),
                    status="open",
                )
            )

        for run in scheduler_runs if isinstance(scheduler_runs, list) else []:
            status = getattr(run, "status", None)
            if status == "error":
                actions.append(
                    self._action(
                        key=f"scheduler:{getattr(run, 'job_id', 'unknown')}:{self._iso(getattr(run, 'executed_at', None))}",
                        severity="high",
                        category="scheduler",
                        title="调度任务失败",
                        detail=f"{getattr(run, 'job_name', getattr(run, 'job_id', 'unknown'))}: {getattr(run, 'detail', '')}",
                        source_service="SchedulerService",
                        source_field="scheduler.run_history.status",
                        target_url="/dashboard",
                        created_at=self._iso(getattr(run, "executed_at", None)) or created_at,
                        status="open",
                    )
                )
        if not scheduler_running:
            actions.append(
                self._action(
                    key="scheduler:not_running",
                    severity="medium",
                    category="scheduler",
                    title="Scheduler 未运行",
                    detail="Background scheduler is not running; scheduled evidence may be stale.",
                    source_service="SchedulerService",
                    source_field="scheduler.is_running",
                    target_url="/dashboard",
                    created_at=created_at,
                    status="open",
                )
            )

        ledger_status = getattr(ledger_latest, "status", None)
        if ledger_latest is None:
            actions.append(
                self._action(
                    key="reconciliation:no_ledger_run",
                    severity="medium",
                    category="reconciliation",
                    title="缺少交易流水对账记录",
                    detail="No trade ledger reconciliation run is available.",
                    source_service="TradeLedgerReconciliationService",
                    source_field="latest",
                    target_url="/dashboard/operations",
                    created_at=created_at,
                    status="open",
                )
            )
        elif ledger_status in {"drift", "critical"}:
            actions.append(
                self._action(
                    key=f"reconciliation:{getattr(ledger_latest, 'as_of', '')}",
                    severity="high" if ledger_status == "critical" else "medium",
                    category="reconciliation",
                    title="交易流水对账异常",
                    detail=f"Latest trade ledger reconciliation status is {ledger_status}.",
                    source_service="TradeLedgerReconciliationService",
                    source_field="latest.status",
                    target_url="/dashboard/operations",
                    created_at=self._iso(getattr(ledger_latest, "captured_at", None)) or created_at,
                    status="open",
                )
            )

        rows = self._dedupe_actions(actions)
        severity_order = {"high": 0, "medium": 1, "low": 2}
        rows.sort(key=lambda row: (severity_order.get(str(row["severity"]), 9), str(row["category"]), str(row["title"])))
        return {
            "status": "clear" if not rows else "open",
            "count": len(rows),
            "open_count": sum(1 for row in rows if row["status"] == "open"),
            "highest_severity": rows[0]["severity"] if rows else "none",
            "items": rows[:50],
            "source_service": "TradingDayWorkflowService",
            "source_field": "action_queue",
        }

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

    def _broker_component(self, broker: dict[str, object], observed_at: datetime) -> dict[str, object]:
        backend = str(broker.get("backend", "unknown")).lower() if isinstance(broker, dict) else "unknown"
        healthy = bool(broker.get("healthy", False)) if isinstance(broker, dict) else False
        if not healthy:
            status = "offline"
        elif backend == "simulated":
            status = "degraded"
        else:
            status = "ok"
        return self._component(
            component_id="broker",
            label="券商连接",
            status=status,
            detail=str(broker.get("detail", "broker status unavailable")) if isinstance(broker, dict) else "broker status unavailable",
            source_service="AdapterFactory",
            source_field="broker_status",
            observed_at=observed_at.isoformat(),
            target_url="/dashboard/operations",
            extra={"backend": backend, "healthy": healthy},
        )

    def _account_component(self, snapshot: object, generated_at: datetime) -> dict[str, object]:
        if snapshot is None:
            return self._component(
                component_id="account",
                label="账户快照",
                status="offline",
                detail="Portfolio snapshot is unavailable.",
                source_service="PortfolioService",
                source_field="current_snapshot",
                target_url="/dashboard",
            )
        timestamp = getattr(snapshot, "timestamp", None)
        source = str(getattr(snapshot, "source", "unknown"))
        age_seconds = self._age_seconds(timestamp, generated_at)
        if source == "degraded":
            status = "degraded"
        elif age_seconds is not None and age_seconds > 15 * 60:
            status = "stale"
        else:
            status = "ok"
        return self._component(
            component_id="account",
            label="账户快照",
            status=status,
            detail=f"NAV={getattr(snapshot, 'nav', 0.0):.2f}, source={source}",
            source_service="PortfolioService",
            source_field="current_snapshot",
            observed_at=self._iso(timestamp),
            target_url="/dashboard",
            extra={"nav": getattr(snapshot, "nav", 0.0), "source": source, "age_seconds": age_seconds},
        )

    def _orders_component(self, orders: list[object], state_counts: dict[str, object]) -> dict[str, object]:
        submitted = int(state_counts.get("submitted", 0) or 0) if isinstance(state_counts, dict) else 0
        partial = int(state_counts.get("partially_filled", 0) or 0) if isinstance(state_counts, dict) else 0
        pending_approval = int(state_counts.get("pending_approval", 0) or 0) if isinstance(state_counts, dict) else 0
        latest_timestamp = None
        for row in orders:
            if isinstance(row, dict):
                observed = self._iso(row.get("timestamp"))
                if observed and (latest_timestamp is None or observed > latest_timestamp):
                    latest_timestamp = observed
        status = "degraded" if submitted or partial or pending_approval else "ok"
        return self._component(
            component_id="orders",
            label="订单状态",
            status=status,
            detail=f"open={submitted + partial}, pending_approval={pending_approval}",
            source_service="ExecutionService",
            source_field="order_state_summary",
            observed_at=self._iso(latest_timestamp),
            target_url="/dashboard",
            extra={"state_counts": state_counts},
        )

    def _data_quality_component(self, data_quality: dict[str, object]) -> dict[str, object]:
        if not isinstance(data_quality, dict):
            return self._component(
                component_id="market_data",
                label="数据质量",
                status="offline",
                detail="Data quality summary is unavailable.",
                source_service="DataQualityQueryService",
                source_field="data_quality_summary",
                target_url="/dashboard/operations",
            )
        blockers = list(data_quality.get("blockers", []) or [])
        fx_blockers = list(data_quality.get("fx_blockers", []) or [])
        status = "blocked" if blockers or fx_blockers or data_quality.get("ready") is False else "ok"
        detail = "; ".join(str(item) for item in [*blockers, *fx_blockers][:2]) or "Data quality is live-ready."
        return self._component(
            component_id="market_data",
            label="行情/FX/历史",
            status=status,
            detail=detail,
            source_service="DataQualityQueryService",
            source_field="data_quality_summary",
            target_url="/dashboard/operations",
            extra={
                "ready": data_quality.get("ready"),
                "minimum_coverage_ratio": data_quality.get("minimum_coverage_ratio"),
                "fx_ready": data_quality.get("fx_ready"),
            },
        )

    def _scheduler_component(self, running: bool, runs: object) -> dict[str, object]:
        run_rows = runs if isinstance(runs, list) else []
        latest = run_rows[0] if run_rows else None
        latest_status = getattr(latest, "status", None)
        if latest_status == "error":
            status = "blocked"
        elif not running:
            status = "degraded"
        elif latest is None:
            status = "stale"
        else:
            status = "ok"
        detail = (
            f"latest={getattr(latest, 'job_id', 'none')} {latest_status}"
            if latest is not None
            else ("scheduler stopped" if not running else "no scheduler run history")
        )
        return self._component(
            component_id="scheduler",
            label="调度器",
            status=status,
            detail=detail,
            source_service="SchedulerService",
            source_field="scheduler.run_history",
            observed_at=self._iso(getattr(latest, "executed_at", None)) if latest is not None else None,
            target_url="/dashboard",
            extra={"running": running, "latest_status": latest_status},
        )

    def _reconciliation_component(self, latest: object) -> dict[str, object]:
        if latest is None:
            return self._component(
                component_id="reconciliation",
                label="交易流水对账",
                status="stale",
                detail="No trade ledger reconciliation run is available.",
                source_service="TradeLedgerReconciliationService",
                source_field="latest",
                target_url="/dashboard/operations",
            )
        latest_status = str(getattr(latest, "status", "unknown"))
        status = "ok" if latest_status == "ok" else ("blocked" if latest_status == "critical" else "degraded")
        return self._component(
            component_id="reconciliation",
            label="交易流水对账",
            status=status,
            detail=f"latest status={latest_status}",
            source_service="TradeLedgerReconciliationService",
            source_field="latest.status",
            observed_at=self._iso(getattr(latest, "captured_at", None)),
            target_url="/dashboard/operations",
            extra={"latest_status": latest_status, "as_of": self._iso(getattr(latest, "as_of", None))},
        )

    @staticmethod
    def _blocker(detail: str, source_service: str, source_field: str) -> dict[str, object]:
        return {"detail": detail, "source_service": source_service, "source_field": source_field}

    @staticmethod
    def _component(
        *,
        component_id: str,
        label: str,
        status: str,
        detail: str,
        source_service: str,
        source_field: str,
        observed_at: str | None = None,
        target_url: str = "/dashboard/operations",
        extra: dict[str, object] | None = None,
    ) -> dict[str, object]:
        return {
            "id": component_id,
            "label": label,
            "status": status,
            "detail": detail,
            "observed_at": observed_at,
            "source_service": source_service,
            "source_field": source_field,
            "target_url": target_url,
            **(extra or {}),
        }

    @staticmethod
    def _action(
        *,
        key: str,
        severity: str,
        category: str,
        title: str,
        detail: str,
        source_service: str,
        source_field: str,
        target_url: str,
        created_at: str,
        status: str,
    ) -> dict[str, object]:
        return {
            "id": key.replace(" ", "_")[:160],
            "severity": severity,
            "category": category,
            "title": title,
            "detail": detail,
            "source_service": source_service,
            "source_field": source_field,
            "target_url": target_url,
            "created_at": created_at,
            "status": status,
        }

    def _worst_status(self, statuses: list[str]) -> str:
        if not statuses:
            return "ok"
        return max(statuses, key=lambda status: self._STATUS_RANK.get(status, 0))

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
        unique: list[dict[str, object]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (str(row.get("detail", "")), str(row.get("source_service", "")), str(row.get("source_field", "")))
            if key in seen:
                continue
            seen.add(key)
            unique.append(row)
        return unique

    @staticmethod
    def _dedupe_actions(actions: list[dict[str, object]]) -> list[dict[str, object]]:
        unique: list[dict[str, object]] = []
        seen: set[str] = set()
        for action in actions:
            key = str(action.get("id") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            unique.append(action)
        return unique

    @staticmethod
    def _iso(value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.isoformat()
        return str(value)

    @staticmethod
    def _age_seconds(timestamp: object, now: datetime) -> float | None:
        if not isinstance(timestamp, datetime):
            return None
        observed = timestamp.astimezone(UTC) if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
        return max(0.0, (now - observed).total_seconds())

    @staticmethod
    def _safe_call(label: str, func, fallback):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            return {"error": f"{label} unavailable: {exc}"} if isinstance(fallback, dict) else fallback

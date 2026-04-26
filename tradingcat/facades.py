from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any

from tradingcat.api.view_models import (
    AccountSummaryView,
    AlertsSummaryView,
    ComplianceSummaryView,
    DataQualityResponse,
    DiagnosticsSummaryView,
    DashboardSummaryResponse,
    MarketAwarenessResponse,
    OperationsReadinessResponse,
    PlanItemView,
    PositionView,
    ResearchScorecardResponse,
    _default_research_readiness_response,
    _default_startup_preflight_response,
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

logger = logging.getLogger(__name__)


class DashboardFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def build_summary(self, as_of: date | None = None) -> DashboardSummaryResponse:
        evaluation_date = as_of or date.today()
        snapshot = self._app.portfolio.current_snapshot()
        projections = self._app.portfolio_projections
        plan_note = self._ensure_plan_note(evaluation_date)
        summary_note = self._ensure_summary_note(evaluation_date)
        dashboard_context = self._app.dashboard_queries.summary_context(evaluation_date)
        gate = self._normalize_gate(dashboard_context["gate"])
        plan_items = [PlanItemView.model_validate(item) for item in plan_note.items]
        approvals = self._approval_rows()
        candidate_scorecard = dashboard_context["candidate_scorecard"]

        payload = DashboardSummaryResponse(
            as_of=evaluation_date,
            overview=self._overview(snapshot),
            assets={
                "position_value": round(sum(position.market_value for position in snapshot.positions), 4),
                "cash": snapshot.cash,
                "positions": [projections.serialize_position(position) for position in snapshot.positions],
            },
            accounts=self._accounts(snapshot, plan_items),
            strategies=self._strategies(candidate_scorecard, dashboard_context),
            candidates=self._candidate_summary(candidate_scorecard),
            trading_plan=self._trading_plan_summary(
                plan_note,
                plan_items,
                approvals,
                gate,
                dashboard_context.get("market_awareness", {}),
            ),
            journal=self._journal_summary(plan_note, summary_note),
            summaries=self._summaries_summary(plan_note, summary_note, dashboard_context["daily_report"], dashboard_context["weekly_report"]),
            details=self._details_summary(gate, dashboard_context),
        )
        return payload

    def _ensure_plan_note(self, evaluation_date: date):
        note = self._app.trading_journal.latest_plan(as_of=evaluation_date)
        if note is not None and all("intent_id" in item and "target_weight" in item for item in note.items):
            return note
        return DailyTradingPlanNote(
            as_of=evaluation_date,
            status="no_trade",
            headline="当前日期还没有归档交易计划。",
            reasons=["生成或归档一份每日交易计划后，这个面板会展示计划内容。"],
            metrics={"source": "dashboard_fallback"},
            items=[],
        )

    def _ensure_summary_note(self, evaluation_date: date):
        note = self._app.trading_journal.latest_summary(as_of=evaluation_date)
        return note or DailyTradingSummaryNote(
            as_of=evaluation_date,
            headline="当前日期还没有归档交易总结。",
            highlights=["完成复盘后生成每日总结，这个面板会展示总结内容。"],
            next_actions=["日终复盘结束后运行总结归档流程。"],
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
        market_awareness_snapshot: dict[str, object] | None = None,
    ) -> dict[str, object]:
        raw_metrics = getattr(plan_note, "metrics", {})
        metrics = raw_metrics if isinstance(raw_metrics, dict) else {}
        market_awareness = metrics.get("market_awareness") if isinstance(metrics, dict) else None
        if not isinstance(market_awareness, dict) or not market_awareness:
            market_awareness = market_awareness_snapshot if isinstance(market_awareness_snapshot, dict) else {}
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
            "market_awareness": market_awareness,
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

    def _details_summary(self, gate: dict[str, object], dashboard_context: dict[str, object]) -> dict[str, object]:
        live_acceptance = dashboard_context["live_acceptance"]
        rollout = dashboard_context["rollout"]
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
            "data_quality": dashboard_context["data_quality"],
            "market_awareness": dashboard_context.get("market_awareness", {}),
            "operations": dashboard_context["operations"],
            "recent_orders": dashboard_context["recent_orders"],
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

    def _strategies(self, strategy_report: dict[str, object], dashboard_context: dict[str, object]) -> dict[str, object]:
        active_ids = set(dashboard_context["active_strategy_ids"])
        selection_summary = dashboard_context["selection_summary"]
        allocation_summary = dashboard_context["allocation_summary"]
        selection_paper_only_ids = set(selection_summary.get("paper_only", []))
        allocation_paper_only_ids = {
            str(item.get("strategy_id"))
            for item in allocation_summary.get("paper_only", [])
            if item.get("strategy_id") is not None
        }
        rows_source = list(strategy_report.get("rows", []))
        if not rows_source:
            readiness = dashboard_context.get("operations", {}).get("research_readiness", {})
            rows_source = [
                {
                    "strategy_id": item.get("strategy_id"),
                    "action": "paper_only" if item.get("promotion_blocked") else "keep",
                    "promotion_blocked": item.get("promotion_blocked", not item.get("data_ready", True)),
                    "blocking_reasons": list(item.get("blocking_reasons", [])),
                    "data_source": item.get("data_source"),
                    "data_ready": item.get("data_ready"),
                    "minimum_coverage_ratio": item.get("minimum_coverage_ratio"),
                    "validation_status": item.get("validation_status"),
                }
                for item in readiness.get("strategies", [])
                if item.get("strategy_id") is not None
            ]
        rows = []
        for row in rows_source:
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
            "next_actions": strategy_report.get("next_actions", []),
            "snapshot_status": strategy_report.get("snapshot_status"),
            "snapshot_reason": strategy_report.get("snapshot_reason"),
            "snapshot_as_of": strategy_report.get("snapshot_as_of"),
            "snapshot_generated_at": strategy_report.get("snapshot_generated_at"),
            "active_count": len(rows),
            "blocked_by_data_count": sum(1 for row in rows if row.get("display_status") == "blocked_by_data"),
            "paper_only_count": sum(1 for row in rows if row.get("display_status") == "paper_only"),
            "accepted_strategy_ids": strategy_report.get("accepted_strategy_ids", []),
            "portfolio_metrics": strategy_report.get("portfolio_metrics", {}),
            "portfolio_passed": strategy_report.get("portfolio_passed", False),
        }

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

    # ---- existing methods (unchanged) ----

    def scorecard(self, as_of: date, *, include_candidates: bool) -> ResearchScorecardResponse:
        payload = self._app.research_queries.scorecard(as_of, include_candidates=include_candidates)
        if include_candidates:
            self._app.dashboard_snapshot_service.save_scorecard(
                as_of,
                payload,
                snapshot_reason="Persisted from the latest research candidate scorecard.",
            )
        return ResearchScorecardResponse.model_validate(payload)

    def report(self, as_of: date) -> dict[str, object]:
        payload = self._app.research_queries.report(as_of)
        try:
            self._app.dashboard_snapshot_service.refresh(as_of)
        except Exception:
            logger.exception("Failed to refresh dashboard scorecard snapshot", extra={"as_of": as_of.isoformat()})
        return payload

    def stability(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.stability(as_of)

    def recommendations(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.recommendations(as_of)

    def ideas(self, as_of: date) -> dict[str, object]:
        return self._app.research_queries.ideas(as_of)

    def run_backtests(self, as_of: date) -> dict[str, object]:
        payload = self._app.research_queries.run_backtests(as_of)
        try:
            self._app.dashboard_snapshot_service.refresh(as_of)
        except Exception:
            logger.exception("Failed to refresh dashboard snapshot after backtests", extra={"as_of": as_of.isoformat()})
        return payload

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

    def market_awareness(self, as_of: date) -> MarketAwarenessResponse:
        return MarketAwarenessResponse.model_validate(self._app.research_queries.market_awareness(as_of))

    # ---- Phase 1-3 services ----

    def _fetch_bars_for_symbol(self, symbol: str, days: int = 180) -> list:
        end = date.today()
        start = end - __import__("datetime").timedelta(days=days)
        try:
            return self._app.market_history.fetch_bars(symbol, start, end)
        except Exception:
            return []

    def features(self, symbols: list[str], days: int = 180) -> dict[str, object]:
        from tradingcat.services.feature_engineering import FeaturePipeline
        all_features: dict[str, dict[str, float | None]] = {}
        for sym in symbols:
            bars = self._fetch_bars_for_symbol(sym, days)
            if bars:
                pipeline = FeaturePipeline(bars)
                all_features[sym] = pipeline.compute_all()
        return {
            "symbols": symbols,
            "features": all_features,
            "feature_count": len(all_features.get(symbols[0], {})) if symbols and symbols[0] in all_features else 0,
        }

    def factors(self, symbols: list[str], days: int = 180) -> dict[str, object]:
        from tradingcat.services.feature_engineering import FeaturePipeline
        from tradingcat.services.factor_analysis import FactorAnalyzer
        end = date.today()
        start = end - __import__("datetime").timedelta(days=days)
        # Build per-symbol features
        feature_map: dict[str, dict[str, float | None]] = {}
        for sym in symbols:
            bars = self._fetch_bars_for_symbol(sym, days)
            if bars:
                pipeline = FeaturePipeline(bars)
                feature_map[sym] = pipeline.compute_all()
        # Transpose to {feature_name: {symbol: value}}
        feature_names = list(next(iter(feature_map.values()), {}).keys())
        transposed: dict[str, dict[str, float | None]] = {name: {} for name in feature_names}
        for sym, feats in feature_map.items():
            for name, val in feats.items():
                transposed[name][sym] = val
        # Use latest return as proxy forward return
        forward: dict[str, float] = {}
        for sym in symbols:
            bars = self._fetch_bars_for_symbol(sym, min(days, 30))
            if len(bars) >= 2:
                forward[sym] = (bars[-1].close - bars[-2].close) / bars[-2].close
            else:
                forward[sym] = 0.0
        analyzer = FactorAnalyzer(transposed, forward)
        results = {}
        for name in feature_names:
            ic_result = analyzer.rank_ic(name)
            if ic_result is not None:
                results[name] = {"rank_ic": round(float(ic_result), 4)}
        return {"factor_count": len(results), "factors": results, "symbols": symbols}

    def optimize(self, symbols: list[str], method: str = "risk_parity") -> dict[str, object]:
        # Try to build returns matrix from historical data for meaningful optimization
        import numpy as np
        returns_list = []
        end = date.today()
        start = end - __import__("datetime").timedelta(days=180)
        for sym in symbols:
            bars = self._fetch_bars_for_symbol(sym, 180)
            closes = np.array([b.close for b in bars], dtype=np.float64)
            if len(closes) >= 10:
                rets = (closes[1:] - closes[:-1]) / closes[:-1]
                returns_list.append(rets[-60:] if len(rets) >= 60 else np.pad(rets, (60 - len(rets), 0)))
            else:
                returns_list.append(np.zeros(60))
        cov_matrix = None
        if len(returns_list) == len(symbols) and len(returns_list[0]) > 0:
            returns_matrix = np.column_stack(returns_list)
            if returns_matrix.shape[1] > 1:
                cov_matrix = self._app.portfolio_optimizer.ledoit_wolf_covariance(returns_matrix)

        result = self._app.portfolio_optimizer.optimize(
            symbols=symbols, method=method, cov_matrix=cov_matrix,
        )
        return {
            "weights": result.weights,
            "expected_return": result.expected_return,
            "expected_volatility": result.expected_volatility,
            "sharpe_ratio": result.sharpe_ratio,
            "concentration": result.concentration,
            "success": result.success,
        }

    def ml_predict(self, symbols: list[str]) -> dict[str, object]:
        models = self._app.ml_pipeline._registry.list_models() if hasattr(self._app.ml_pipeline, '_registry') else []
        return {
            "symbols": symbols,
            "models_available": [str(m) for m in (models or [])],
            "note": "Train a model via POST /research/ml/train to enable predictions",
            "predictions": {},
        }

    def alternative_data_snapshot(self, symbols: list[str] | None = None) -> dict[str, object]:
        snap = self._app.alternative_data.snapshot(symbols)
        return {
            "social_media": {s: {"mention_count": m.mention_count, "positive_ratio": m.positive_ratio} for s, m in snap.social_media.items()},
            "capital_flow_count": len(snap.capital_flows),
            "macro_event_count": len(snap.macro_events),
            "sources_healthy": snap.sources_healthy,
            "sources_degraded": snap.sources_degraded,
        }

    def ai_briefing(self) -> dict[str, object]:
        report = self._app.ai_researcher.market_briefing()
        return {
            "feature": report.feature.value if hasattr(report.feature, 'value') else str(report.feature),
            "content": report.content,
            "summary": report.summary,
            "confidence": report.confidence,
            "generated_at": report.generated_at.isoformat() if hasattr(report.generated_at, 'isoformat') else str(report.generated_at),
            "model": report.model,
        }

    def auto_research_report(self) -> dict[str, object]:
        report = self._app.auto_research.run_weekly()
        latest = self._app.auto_research.latest_report()
        return {"report": latest, "summary": report.summary}

    def attribution(self, start: date, end: date) -> dict[str, object]:
        portfolio_returns = {}
        benchmark_returns = {}
        weights = {}
        return self._app.performance_attribution.brinson_attribution(
            portfolio_weights=weights,
            portfolio_returns=portfolio_returns,
            benchmark_returns=benchmark_returns,
        )


class OperationsFacade:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def readiness(self) -> OperationsReadinessResponse:
        payload = self._app.operations_readiness()
        preflight_payload = payload.get("preflight", {})
        research_payload = payload.get("research_readiness", {})

        if isinstance(research_payload, dict):
            payload["research_readiness"] = (
                _default_research_readiness_response()
                .model_copy(update=research_payload)
                .model_dump(mode="json")
            )
        if isinstance(preflight_payload, dict):
            normalized_preflight = dict(preflight_payload)
            nested_research_payload = normalized_preflight.get("research_readiness")
            if isinstance(nested_research_payload, dict):
                normalized_preflight["research_readiness"] = (
                    _default_research_readiness_response()
                    .model_copy(update=nested_research_payload)
                    .model_dump(mode="json")
                )
            payload["preflight"] = (
                _default_startup_preflight_response()
                .model_copy(update=normalized_preflight)
                .model_dump(mode="json")
            )
        if isinstance(payload.get("diagnostics"), dict):
            payload["diagnostics"] = DiagnosticsSummaryView.model_validate(payload["diagnostics"]).model_dump(mode="json")
        if isinstance(payload.get("data_quality"), dict):
            payload["data_quality"] = (
                DataQualityResponse(ready=True, scope="unknown")
                .model_copy(update=payload["data_quality"])
                .model_dump(mode="json")
            )
        if isinstance(payload.get("alerts"), dict):
            normalized_alerts = dict(payload["alerts"])
            latest_alert = normalized_alerts.get("latest")
            if hasattr(latest_alert, "model_dump"):
                normalized_alerts["latest"] = latest_alert.model_dump(mode="json")
            normalized_alerts["active"] = [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in normalized_alerts.get("active", [])
            ]
            payload["alerts"] = AlertsSummaryView.model_validate(normalized_alerts).model_dump(mode="json")
        if isinstance(payload.get("compliance"), dict):
            payload["compliance"] = ComplianceSummaryView.model_validate(payload["compliance"]).model_dump(mode="json")
        return OperationsReadinessResponse.model_validate(payload)

    def risk_config(self) -> dict[str, object]:
        return self._app.risk.config_snapshot()

    def execution_metrics(self) -> dict[str, object]:
        return self._app.operations_execution_metrics()

    def acceptance_gates(self) -> dict[str, object]:
        return self._app.acceptance_gates()

    def trade_ledger(
        self,
        *,
        start: date | None = None,
        end: date | None = None,
        market: str | None = None,
    ) -> dict[str, object]:
        return self._app.trade_ledger_export(start=start, end=end, market=market)

    def capture_acceptance_evidence(
        self,
        *,
        as_of: date | None = None,
        notes: list[str] | None = None,
    ) -> dict[str, object]:
        return self._app.capture_acceptance_evidence(as_of=as_of, notes=notes)

    def acceptance_evidence_timeline(self, *, window_days: int = 42) -> dict[str, object]:
        return self._app.acceptance_evidence_timeline(window_days=window_days)

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

from __future__ import annotations

import csv
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, time, timedelta
from io import StringIO
import math
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from tradingcat.adapters.factory import AdapterFactory
from tradingcat.adapters.market import sample_instruments
from tradingcat.backtest.engine import EventDrivenBacktester
from tradingcat.config import AppConfig
from tradingcat.domain.models import AssetClass, DailyTradingPlanNote, DailyTradingSummaryNote, Instrument, ManualFill, Market, OrderIntent, OrderSide, Signal
from tradingcat.repositories.research import BacktestExperimentRepository
from tradingcat.repositories.market_data import HistoricalMarketDataRepository, InstrumentCatalogRepository
from tradingcat.repositories.state import AlertRepository, ApprovalRepository, AuditLogRepository, ComplianceRepository, DailyTradingPlanRepository, DailyTradingSummaryRepository, ExecutionStateRepository, HistorySyncRunRepository, KillSwitchRepository, OperationsJournalRepository, OrderRepository, PortfolioHistoryRepository, PortfolioRepository, RecoveryAttemptRepository, RolloutPolicyRepository, RolloutPromotionRepository, StrategyAllocationRepository, StrategySelectionRepository
from tradingcat.services.allocation import StrategyAllocationService
from tradingcat.services.audit import AuditService
from tradingcat.services.alerts import AlertService
from tradingcat.services.approval import ApprovalService
from tradingcat.services.compliance import ComplianceService
from tradingcat.services.data_sync import HistorySyncService
from tradingcat.services.execution import ExecutionService
from tradingcat.services.market_data import MarketDataService
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.operations import OperationsJournalService, RecoveryService
from tradingcat.services.portfolio import PortfolioService
from tradingcat.services.preflight import build_startup_preflight, summarize_validation_diagnostics
from tradingcat.services.reporting import (
    build_operations_period_report,
    build_postmortem_report,
    build_incident_replay,
    filter_recent_items,
    latest_report_dir,
    load_report_summary,
    resolve_report_dir,
    summarize_report_for_dashboard,
)
from tradingcat.services.research import ResearchService
from tradingcat.services.risk import RiskEngine, RiskViolation
from tradingcat.services.rollout import RolloutPolicyService, RolloutPromotionService
from tradingcat.services.scheduler import SchedulerService
from tradingcat.services.selection import StrategySelectionService
from tradingcat.services.trading_journal import TradingJournalService
from tradingcat.strategies.simple import DefensiveTrendStrategy, EquityMomentumStrategy, EtfRotationStrategy, MeanReversionStrategy, OptionHedgeStrategy, strategy_metadata



class DecisionPayload(BaseModel):
    reason: str | None = None


class ChecklistItemPayload(BaseModel):
    status: str
    notes: str | None = None


class RiskStatePayload(BaseModel):
    drawdown: float
    daily_pnl: float
    weekly_pnl: float


class MarketDataSmokePayload(BaseModel):
    symbols: list[str] | None = None
    include_bars: bool = True
    include_option_chain: bool = False


class HistorySyncPayload(BaseModel):
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    include_corporate_actions: bool = True


class HistoryRepairPayload(BaseModel):
    symbols: list[str] | None = None
    start: date | None = None
    end: date | None = None
    include_corporate_actions: bool = True


class FxSyncPayload(BaseModel):
    base_currency: str = "CNY"
    quote_currencies: list[str] | None = None
    start: date | None = None
    end: date | None = None


class ResearchNewsItemPayload(BaseModel):
    title: str
    body: str | None = None
    symbols: list[str] = []


class ResearchNewsSummaryPayload(BaseModel):
    items: list[ResearchNewsItemPayload]


class ManualFillImportPayload(BaseModel):
    csv_text: str
    delimiter: str = ","


class ExecutionPreviewPayload(BaseModel):
    as_of: date | None = None


class ExecutionRunPayload(BaseModel):
    as_of: date | None = None
    enforce_gate: bool = False


class BrokerOrderCheckPayload(BaseModel):
    pass


class RebalancePlanPayload(BaseModel):
    as_of: date | None = None



class TradingCatApplication:
    def __init__(self) -> None:
        self.config = AppConfig.from_env()
        self.adapter_factory = AdapterFactory(self.config)

        data_dir = self.config.data_dir
        data_dir.mkdir(parents=True, exist_ok=True)

        self._runtime_repositories: dict[str, object] = {
            "orders": OrderRepository(data_dir / "orders.json"),
            "execution_state": ExecutionStateRepository(data_dir / "execution_state.json"),
            "market_history": HistoricalMarketDataRepository(data_dir / "market_history"),
            "instrument_catalog": InstrumentCatalogRepository(data_dir / "instruments.json"),
            "research": BacktestExperimentRepository(data_dir / "research.json"),
        }

        self.risk = RiskEngine(
            config=self.config.risk,
            kill_switch_repository=KillSwitchRepository(data_dir / "kill_switch.json"),
        )
        self.audit = AuditService(
            repository=AuditLogRepository(data_dir / "audit.json"),
        )
        self.alerts = AlertService(
            repository=AlertRepository(data_dir / "alerts.json"),
        )
        self.approvals = ApprovalService(
            repository=ApprovalRepository(data_dir / "approvals.json"),
        )
        self.compliance = ComplianceService(
            repository=ComplianceRepository(data_dir / "compliance.json"),
        )
        self.portfolio = PortfolioService(
            repository=PortfolioRepository(data_dir / "portfolio.json"),
            history_repository=PortfolioHistoryRepository(data_dir / "portfolio_history.json"),
            config=self.config,
        )
        self.allocations = StrategyAllocationService(
            repository=StrategyAllocationRepository(data_dir / "allocations.json"),
        )
        self.selection = StrategySelectionService(
            repository=StrategySelectionRepository(data_dir / "selection.json"),
        )
        self.data_sync = HistorySyncService(
            run_repository=HistorySyncRunRepository(data_dir / "history_sync_runs.json"),
        )
        self.market_calendar = MarketCalendarService()
        self.operations = OperationsJournalService(
            repository=OperationsJournalRepository(data_dir / "operations_journal.json"),
        )
        self.recovery = RecoveryService(
            repository=RecoveryAttemptRepository(data_dir / "recovery_attempts.json"),
        )
        self.rollout_policy = RolloutPolicyService(
            repository=RolloutPolicyRepository(data_dir / "rollout_policy.json"),
        )
        self.rollout_promotions = RolloutPromotionService(
            repository=RolloutPromotionRepository(data_dir / "rollout_promotions.json"),
        )
        self.trading_journal = TradingJournalService(
            plan_repository=DailyTradingPlanRepository(data_dir / "trading_plans.json"),
            summary_repository=DailyTradingSummaryRepository(data_dir / "trading_summaries.json"),
        )
        self.scheduler = SchedulerService(config=self.config.scheduler)

        self._build_runtime_components()
        self._register_jobs()

    @property
    def research_strategies(self):
        strategies = [
            DefensiveTrendStrategy(),
            EquityMomentumStrategy(),
            EtfRotationStrategy(),
            MeanReversionStrategy(),
            OptionHedgeStrategy(),
        ]
        instruments = sample_instruments()
        for strategy in strategies:
            strategy.instruments = instruments
        return strategies

    def active_execution_strategies(self):
        active_ids = {str(record["strategy_id"]) for record in self.allocations.summary()["active"]}
        return [s for s in self.research_strategies if s.strategy_id in active_ids]

    def strategy_by_id(self, strategy_id: str):
        for strategy in self.research_strategies:
            if strategy.strategy_id == strategy_id:
                return strategy
        raise KeyError(f"Strategy {strategy_id!r} not found")

    def get_signals(self, as_of: date) -> list[Signal]:
        signals = []
        for strategy in self.active_execution_strategies():
            signals.extend(strategy.generate_signals(as_of))
        return signals

    def run_execution_cycle(self, as_of: date, *, enforce_gate: bool = False) -> dict[str, object]:
        gate = self.execution_gate_summary(as_of)
        if enforce_gate and gate["should_block"]:
            from tradingcat.services.risk import RiskViolation
            raise RiskViolation(f"Execution gate blocked: {gate['reasons']}")

        signals = self.get_signals(as_of)
        intents: list[OrderIntent] = []
        for strategy in self.active_execution_strategies():
            strategy_signals = [s for s in signals if s.strategy_id == strategy.strategy_id]
            for signal in strategy_signals:
                try:
                    intent = self.compliance.build_order_intent(signal, self.portfolio.snapshot())
                    intents.append(intent)
                except Exception:
                    pass

        prices: dict[str, float] = {}
        try:
            prices = self.market_history.get_latest_prices([intent.instrument.symbol for intent in intents])
        except Exception:
            pass

        self.execution.register_expected_prices(intents, prices)
        submitted = []
        failed = []
        approval_count = 0
        for intent in intents:
            try:
                report = self.execution.submit(intent)
                submitted.append(report)
                if intent.requires_approval:
                    approval_count += 1
            except Exception as exc:
                failed.append({"intent_id": intent.id, "error": str(exc)})

        return {
            "as_of": as_of,
            "signal_count": len(signals),
            "intent_count": len(intents),
            "submitted_orders": submitted,
            "failed_orders": failed,
            "approval_count": approval_count,
            "gate": gate,
        }

    def preview_execution(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        gate = self.execution_gate_summary(evaluation_date)
        signals = self.get_signals(evaluation_date)
        intents: list[OrderIntent] = []
        for strategy in self.active_execution_strategies():
            strategy_signals = [s for s in signals if s.strategy_id == strategy.strategy_id]
            for signal in strategy_signals:
                try:
                    intent = self.compliance.build_order_intent(signal, self.portfolio.snapshot())
                    intents.append(intent)
                except Exception:
                    pass

        prices: dict[str, float] = {}
        try:
            prices = self.market_history.get_latest_prices([intent.instrument.symbol for intent in intents])
        except Exception:
            pass

        manual_count = sum(1 for intent in intents if intent.requires_approval)
        automated_count = len(intents) - manual_count
        return {
            "as_of": evaluation_date,
            "signal_count": len(signals),
            "intent_count": len(intents),
            "manual_count": manual_count,
            "automated_count": automated_count,
            "gate": gate,
            "signals": signals,
            "order_intents": intents,
            "prices": prices,
        }

    def _apply_fill_to_portfolio(self, order_intent_id: str, filled_quantity: float, average_price: float):
        try:
            context = self.execution.resolve_intent_context(order_intent_id)
            if context is None:
                return None
            instrument_data = context.get("instrument")
            if instrument_data is None:
                return None
            instrument = Instrument(**instrument_data) if isinstance(instrument_data, dict) else instrument_data
            side_str = context.get("side", "buy")
            side = OrderSide.BUY if side_str == "buy" else OrderSide.SELL
            snapshot = self.portfolio.apply_fill(
                instrument=instrument,
                side=side,
                filled_quantity=filled_quantity,
                average_price=average_price,
            )
            return snapshot
        except Exception:
            return None

    def operations_readiness(self) -> dict[str, object]:
        broker_diagnostics = self.adapter_factory.broker_diagnostics()
        broker_validation = self.adapter_factory.validate_futu_connection()
        history_sync = self.data_sync.status_summary()
        alerts_summary = self.alerts.summary()
        allocation_summary = self.allocations.summary()
        kill_switch = self.risk.kill_switch_status()
        rollout = self.operations_rollout()
        policy = self.rollout_policy_summary()

        preflight = build_startup_preflight(self.config)
        diagnostics = summarize_validation_diagnostics(preflight)

        return {
            "broker": broker_diagnostics,
            "broker_validation": broker_validation,
            "history_sync": history_sync,
            "alerts": alerts_summary,
            "allocation": allocation_summary,
            "kill_switch": kill_switch,
            "rollout": rollout,
            "policy": policy,
            "preflight": preflight,
            "diagnostics": diagnostics,
        }

    def operations_rollout(self) -> dict[str, object]:
        acceptance = self.operations.acceptance_summary()
        milestones = self.operations.rollout_milestones()
        policy = self.rollout_policy_summary()
        stage = str(policy.get("stage", "hold"))
        stage_rank = {"hold": 0, "10%": 1, "30%": 2, "CN_manual_gate": 3, "100%": 4}
        recommended_stage = str(milestones.get("current_recommendation", "hold"))
        recommendations: list[str] = []
        if stage_rank.get(stage, 0) < stage_rank.get(recommended_stage, 0):
            recommendations.append(f"Consider promoting to {recommended_stage} stage.")
        ready_for_rollout = bool(acceptance.get("ready_weeks", 0)) >= 1
        return {
            "stage": stage,
            "recommended_stage": recommended_stage,
            "ready_for_rollout": ready_for_rollout,
            "milestones": milestones,
            "acceptance": acceptance,
            "recommendations": recommendations,
        }

    def rollout_policy_summary(self) -> dict[str, object]:
        return self.rollout_policy.summary()

    def operations_execution_metrics(self) -> dict[str, object]:
        quality = self.execution.execution_quality_summary()
        state_summary = self.execution.order_state_summary()
        authorization = self.execution.authorization_summary()
        total_orders = sum(state_summary.values())
        filled_orders = state_summary.get("filled", 0)
        failed_orders = state_summary.get("failed", 0)
        exception_rate = round(failed_orders / total_orders, 4) if total_orders > 0 else 0.0
        return {
            "total_orders": total_orders,
            "filled_orders": filled_orders,
            "failed_orders": failed_orders,
            "exception_rate": exception_rate,
            "quality": quality,
            "authorization": authorization,
        }

    def data_quality_summary(self) -> dict[str, object]:
        return self.market_history.data_quality_summary()

    def history_sync_repair_plan(self, symbols: list[str] | None = None) -> dict[str, object]:
        return self.market_history.repair_plan(symbols)

    def sync_market_history(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        return self.market_history.sync(
            symbols=symbols,
            start=start,
            end=end,
            include_corporate_actions=include_corporate_actions,
            run_repository=self.data_sync._run_repository,
        )

    def repair_market_history_gaps(
        self,
        symbols: list[str] | None = None,
        start: date | None = None,
        end: date | None = None,
        include_corporate_actions: bool = True,
    ) -> dict[str, object]:
        return self.market_history.repair_gaps(
            symbols=symbols,
            start=start,
            end=end,
            include_corporate_actions=include_corporate_actions,
            run_repository=self.data_sync._run_repository,
        )

    def run_market_data_smoke_test(
        self,
        symbols: list[str] | None = None,
        include_bars: bool = True,
        include_option_chain: bool = False,
    ) -> dict[str, object]:
        return self.market_history.smoke_test(
            symbols=symbols or self.config.smoke_symbols,
            include_bars=include_bars,
            include_option_chain=include_option_chain,
        )

    def recover_runtime(self, *, trigger: str = "manual", retries: int = 0) -> dict[str, object]:
        before = self.operations_readiness()
        try:
            self._close_runtime_components()
            self._build_runtime_components()
        except Exception:
            pass
        after = self.operations_readiness()
        attempt = self.recovery.record(
            trigger=trigger,
            retries=retries,
            before_healthy=bool(before["broker"]["healthy"]),
            after_healthy=bool(after["broker"]["healthy"]),
            changed=(
                before["broker"] != after["broker"]
            ),
            detail=str(after["broker"]["detail"]),
            before_backend=str(before["broker"]["backend"]),
            after_backend=str(after["broker"]["backend"]),
        )
        return {
            "attempted": True,
            "attempt": attempt,
            "before": before,
            "after": after,
            "changed": attempt.changed,
        }

    def broker_validation(self) -> dict[str, object]:
        diagnostics = self.adapter_factory.broker_diagnostics()
        validation = self.adapter_factory.validate_futu_connection()
        return {
            "diagnostics": diagnostics,
            "validation": validation,
            "live_broker_adapter": str(type(self.execution._live_broker).__name__),
            "market_data_adapter": str(type(self.market_data).__name__),
            "broker": diagnostics,
            "checks": validation.get("checks", {}),
            "futu_enabled": self.config.futu.enabled,
            "host": self.config.futu.host,
            "port": self.config.futu.port,
            "environment": self.config.futu.environment,
        }

    def review_strategy_allocations(self, as_of: date) -> dict[str, object]:
        strategy_signals = {
            strategy.strategy_id: strategy.generate_signals(as_of)
            for strategy in self.research_strategies
        }
        recommendation = self.research.recommend_strategy_actions(as_of, strategy_signals)
        accepted_ids = set(recommendation.get("accepted_strategy_ids", []))
        for strategy in self.research_strategies:
            sid = strategy.strategy_id
            meta = strategy_metadata(sid)
            if sid in accepted_ids:
                self.allocations.set_allocation(
                    strategy_id=sid,
                    target_weight=float(meta.get("default_weight", 0.2)),
                    market=str(meta.get("market", "CN")),
                )
        return {
            "as_of": as_of,
            "recommendation": recommendation,
            "summary": self.allocations.summary(),
        }

    def _run_market_history_sync_job(self) -> str:
        result = self.sync_market_history()
        synced = result.get("synced_count", 0)
        return f"Synced {synced} history records"

    def _run_market_history_gap_repair_job(self) -> str:
        result = self.repair_market_history_gaps()
        repaired = result.get("repaired_count", 0)
        return f"Repaired {repaired} history gaps"

    def _run_research_selection_review_job(self) -> str:
        result = self.review_strategy_allocations(date.today())
        accepted = len(result["recommendation"].get("accepted_strategy_ids", []))
        return f"Reviewed {accepted} strategies for allocation"

    def _run_portfolio_snapshot_job(self) -> str:
        snapshot = self.portfolio.snapshot()
        self.portfolio.persist_history(snapshot)
        return f"Persisted portfolio snapshot: NAV={snapshot.nav:.2f}"

    def _run_broker_auto_recovery_job(self) -> str:
        broker_diag = self.adapter_factory.broker_diagnostics()
        if broker_diag.get("healthy", True):
            return "Broker healthy, no recovery needed"
        result = self.recover_runtime(trigger="auto_recovery")
        status = result["attempt"].status
        return f"Auto recovery attempt: {status}"

    def _run_approval_expiry_job(self) -> str:
        expired = self.approvals.expire_stale(
            max_age=__import__("datetime").timedelta(hours=24),
            reason="Expired by approval_expiry_sweep job",
        )
        return f"Expired {len(expired)} stale approvals"

    def _run_operations_journal_job(self) -> str:
        result = self.record_operations_journal()
        return f"Recorded operations journal entry"

    def _run_daily_trading_plan_job(self) -> str:
        plan = self.generate_daily_trading_plan(date.today())
        self.trading_journal.save_plan(plan)
        return f"Archived daily trading plan: {plan.status}"

    def _run_daily_trading_summary_job(self) -> str:
        summary = self.generate_daily_trading_summary(date.today())
        self.trading_journal.save_summary(summary)
        return f"Archived daily trading summary"

    def _account_summary(self, snapshot, risk_state: dict, plan: dict) -> dict[str, object]:
        result = {}
        for account in self._account_keys():
            positions = self._account_positions(snapshot, account)
            curves = self._account_curves()
            result[account] = {
                "positions": positions,
                "curves": curves.get(account, []),
                "nav": sum(p.get("market_value", 0) for p in positions),
                "risk": risk_state,
                "plan_items": [item for item in plan.get("items", []) if item.get("market") == account],
            }
        return result


    def _register_jobs(self) -> None:
        self.scheduler.register(
            job_id="us_signal_generation",
            name="US Signal Generation",
            description="Generate and risk-check daily US/HK/CN signals",
            timezone="America/New_York",
            local_time=time(8, 45),
            market=Market.US,
            handler=self._run_daily_signal_cycle,
        )
        self.scheduler.register(
            job_id="market_data_history_sync",
            name="Market Data History Sync",
            description="Refresh recent local history coverage for tracked instruments",
            timezone="Asia/Shanghai",
            local_time=time(7, 30),
            market=Market.CN,
            handler=self._run_market_history_sync_job,
        )
        self.scheduler.register(
            job_id="market_data_gap_repair",
            name="Market Data Gap Repair",
            description="Repair missing history windows for tracked instruments",
            timezone="Asia/Shanghai",
            local_time=time(7, 40),
            market=Market.CN,
            handler=self._run_market_history_gap_repair_job,
        )
        self.scheduler.register(
            job_id="research_backtest_refresh",
            name="Research Backtest Refresh",
            description="Run all strategy backtests and persist experiment snapshots",
            timezone="Asia/Shanghai",
            local_time=time(7, 0),
            market=Market.CN,
            handler=self._run_backtests_job,
        )
        self.scheduler.register(
            job_id="research_selection_review",
            name="Research Selection Review",
            description="Refresh persisted strategy admission decisions and target allocations from the latest research recommendations",
            timezone="Asia/Shanghai",
            local_time=time(7, 10),
            market=Market.CN,
            handler=self._run_research_selection_review_job,
        )
        self.scheduler.register(
            job_id="portfolio_risk_snapshot",
            name="Portfolio Risk Snapshot",
            description="Persist current portfolio snapshot for dashboard and audit review",
            timezone="Asia/Shanghai",
            local_time=time(18, 0),
            market=Market.CN,
            handler=self._run_portfolio_snapshot_job,
        )
        self.scheduler.register(
            job_id="broker_auto_recovery",
            name="Broker Auto Recovery",
            description="Attempt runtime rebuild when broker validation degrades or disconnects",
            timezone="Asia/Shanghai",
            local_time=time(8, 55),
            market=Market.CN,
            handler=self._run_broker_auto_recovery_job,
        )
        self.scheduler.register(
            job_id="approval_expiry_sweep",
            name="Approval Expiry Sweep",
            description="Expire stale manual approval requests before the next trading session",
            timezone="Asia/Shanghai",
            local_time=time(8, 30),
            market=Market.CN,
            handler=self._run_approval_expiry_job,
        )
        self.scheduler.register(
            job_id="operations_readiness_journal",
            name="Operations Readiness Journal",
            description="Persist daily readiness evidence for paper trading acceptance tracking",
            timezone="Asia/Shanghai",
            local_time=time(18, 15),
            market=Market.CN,
            handler=self._run_operations_journal_job,
        )
        self.scheduler.register(
            job_id="daily_trading_plan_archive",
            name="Daily Trading Plan Archive",
            description="Generate and archive the daily trading plan even when there are no orders",
            timezone="Asia/Shanghai",
            local_time=time(8, 20),
            market=Market.CN,
            handler=self._run_daily_trading_plan_job,
        )
        self.scheduler.register(
            job_id="daily_trading_summary_archive",
            name="Daily Trading Summary Archive",
            description="Generate and archive the daily trading summary for operator review",
            timezone="Asia/Shanghai",
            local_time=time(18, 20),
            market=Market.CN,
            handler=self._run_daily_trading_summary_job,
        )




    def _run_daily_signal_cycle(self) -> str:
        result = self.run_execution_cycle(date.today(), enforce_gate=True)
        return (
            f"Generated {result['signal_count']} signals, "
            f"submitted {len(result['submitted_orders'])} intents, "
            f"failed {len(result['failed_orders'])}"
        )




    def _run_backtests_job(self) -> str:
        experiments = []
        evaluation_date = date.today()
        for strategy in self.research_strategies:
            signals = strategy.generate_signals(evaluation_date)
            experiments.append(self.research.run_experiment(strategy.strategy_id, evaluation_date, signals))



    def _account_keys(self) -> list[str]:
        return ["total", Market.CN.value, Market.HK.value, Market.US.value]




    def _account_positions(self, snapshot, account: str):
        if account == "total":
            return list(snapshot.positions)
        return [position for position in snapshot.positions if position.instrument.market.value == account]




    def _account_cash_map(self, snapshot) -> dict[str, float]:
        cash_by_market = self._resolve_available_cash_by_market()
        return {
            "total": snapshot.cash,
            Market.CN.value: round(cash_by_market.get(Market.CN, 0.0), 4),
            Market.HK.value: round(cash_by_market.get(Market.HK, 0.0), 4),
            Market.US.value: round(cash_by_market.get(Market.US, 0.0), 4),
        }




    def _account_curves(self, limit: int = 90) -> dict[str, list[dict[str, object]]]:
        curves = {key: [] for key in self._account_keys()}
        history = self.portfolio.nav_history(limit=limit)
        if not history:
            return curves
        current_cash_map = self._account_cash_map(history[-1])
        for item in history:
            market_values = {
                Market.CN.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.CN), 4),
                Market.HK.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.HK), 4),
                Market.US.value: round(sum(pos.market_value for pos in item.positions if pos.instrument.market == Market.US), 4),
            }
            curves["total"].append({"t": item.timestamp.isoformat(), "v": round(item.nav, 4)})
            for market_key in (Market.CN.value, Market.HK.value, Market.US.value):
                curves[market_key].append(
                    {
                        "t": item.timestamp.isoformat(),
                        "v": round(market_values[market_key] + current_cash_map.get(market_key, 0.0), 4),
                    }
                )
        return curves



    def go_live_summary(self, as_of: date | None = None) -> dict[str, object]:
        gate = self.execution_gate_summary(as_of)
        rollout = self.operations_rollout()
        milestones = self.operations.rollout_milestones()
        policy = self.rollout_policy_summary()
        promotion_allowed = gate["ready"] and rollout["ready_for_rollout"]
        return {
            "as_of": gate["as_of"],
            "promotion_allowed": promotion_allowed,
            "gate": gate,
            "rollout": rollout,
            "milestones": milestones,
            "policy": policy,
            "promotion_history": self.rollout_promotions.summary(),
            "next_actions": (
                rollout["recommendations"]
                if not promotion_allowed
                else [f"Current evidence supports operation at {policy['stage']} capital allocation."]
            ),
        }




    def live_acceptance_summary(self, as_of: date | None = None, incident_window_days: int = 7) -> dict[str, object]:
        go_live = self.go_live_summary(as_of)
        gate = go_live["gate"]
        quality = self.execution.execution_quality_summary()
        authorization = self.execution.authorization_summary()
        metrics = self.operations_execution_metrics()
        incidents = self.incident_replay(window_days=incident_window_days)

        blockers: list[str] = []
        if not go_live["promotion_allowed"]:
            blockers.append("Go-live gate has not cleared for promotion.")
        if gate["should_block"]:
            blockers.append("Execution gate still has hard blockers.")
        if not quality["within_limits"]:
            blockers.append("Execution slippage quality is outside the allowed envelope.")
        if not authorization["all_authorized"]:
            blockers.append("Unauthorized executions were detected.")
        if float(metrics.get("exception_rate", 0.0)) > 0.05:
            blockers.append("Recent execution exception rate is above 5%.")

        return {
            "as_of": go_live["as_of"],
            "ready_for_live": len(blockers) == 0,
            "go_live": go_live,
            "execution_gate": gate,
            "execution_quality": quality,
            "execution_authorization": authorization,
            "execution_metrics": metrics,
            "incident_window_days": incident_window_days,
            "incident_count": incidents["event_count"],
            "promotion_history": go_live["promotion_history"],
            "blockers": blockers,
            "next_actions": blockers or go_live["next_actions"],
        }




    def generate_daily_trading_summary(self, as_of: date | None = None) -> DailyTradingSummaryNote:
        evaluation_date = as_of or date.today()
        report = self.operations_period_report(window_days=1, label="daily")
        live_acceptance = self.live_acceptance_summary(evaluation_date)
        headline = "今日运行摘要已生成。"
        if live_acceptance["blockers"]:
            headline = "今日运行存在阻塞项，仍已归档。"
        note = DailyTradingSummaryNote(
            as_of=evaluation_date,
            headline=headline,
            highlights=list(report.get("highlights", [])),
            blockers=list(live_acceptance.get("blockers", [])),
            next_actions=list(report.get("next_actions", [])),
            metrics={
                "ready": report.get("readiness", {}).get("ready"),
                "alert_count": report.get("counts", {}).get("alerts", 0),
                "execution_errors": report.get("counts", {}).get("execution_errors", 0),
                "risk_violations": report.get("counts", {}).get("risk_violations", 0),
                "live_ready": live_acceptance.get("ready_for_live"),
            },
        )
        return self.trading_journal.save_summary(note)




    def dashboard_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        snapshot = self.portfolio.snapshot()
        total_position_value = round(sum(position.market_value for position in snapshot.positions), 4)



    def rollout_checklist(self, stage: str, as_of: date | None = None) -> dict[str, object]:
        valid_stages = {"10%", "30%", "100%", "CN_manual_gate"}
        if stage not in valid_stages:
            raise ValueError("stage must be one of 10%, 30%, 100%, CN_manual_gate")

        acceptance = self.operations.acceptance_summary()
        milestones = self.operations.rollout_milestones()
        go_live = self.go_live_summary(as_of)
        live = self.live_acceptance_summary(as_of)
        milestone = next((item for item in milestones["milestones"] if item["stage"] == stage), None)
        stage_rank = {"hold": 0, "10%": 1, "30%": 2, "100%": 3}

        checks: list[dict[str, object]] = []
        if stage in {"10%", "30%", "100%"}:
            checks.extend(
                [
                    {
                        "id": "go_live",
                        "label": "Go-live verdict clears current stage",
                        "passed": bool(go_live["promotion_allowed"]),
                        "detail": "Promotion gate must be green before capital is raised.",
                    },
                    {
                        "id": "live_acceptance",
                        "label": "Live acceptance verdict is green",
                        "passed": bool(live["ready_for_live"]),
                        "detail": "Execution quality, authorization, incidents, and gate must all be within limits.",
                    },
                    {
                        "id": "stage_recommendation",
                        "label": f"Current recommendation supports {stage}",
                        "passed": stage_rank.get(str(go_live["rollout"]["current_recommendation"]), 0)
                        >= stage_rank[stage],
                        "detail": f"Current recommendation is {go_live['rollout']['current_recommendation']}.",
                    },
                ]
            )
        if stage == "CN_manual_gate":
            checks.append(
                {
                    "id": "cn_manual_weeks",
                    "label": "CN manual process has 4 clean weeks",
                    "passed": int(acceptance.get("cn_manual_weeks", 0)) >= 4,
                    "detail": f"Current clean CN manual weeks: {acceptance.get('cn_manual_weeks', 0)}.",
                }
            )
        if milestone is not None:
            checks.append(
                {
                    "id": "milestone",
                    "label": f"Milestone for {stage} is complete",
                    "passed": milestone["status"] == "done",
                    "detail": milestone["requirement"],
                }
            )

        blockers = [item["label"] for item in checks if not item["passed"]]
        return {
            "as_of": go_live["as_of"],
            "stage": stage,
            "ready": len(blockers) == 0,
            "checks": checks,
            "blockers": blockers,
            "current_recommendation": go_live["rollout"]["current_recommendation"],
            "policy_stage": go_live["policy"]["stage"],
            "next_actions": blockers or live["next_actions"],
        }




    def promote_rollout_stage(self, stage: str, reason: str | None = None) -> dict[str, object]:
        summary = self.go_live_summary()
        recommended_stage = str(summary["rollout"]["current_recommendation"])
        current_stage = str(summary["policy"]["stage"])
        rank = {"hold": 0, "10%": 1, "30%": 2, "100%": 3}
        if stage not in rank:
            raise ValueError("stage must be one of hold, 10%, 30%, 100%")
        if summary["gate"]["should_block"]:
            self.rollout_promotions.record(
                requested_stage=stage,
                recommended_stage=recommended_stage,
                current_stage=current_stage,
                allowed=False,
                reason=reason,
                blocker="Execution gate still blocks rollout promotion.",
            )
            raise ValueError("Execution gate still blocks rollout promotion.")
        if rank[stage] > rank.get(recommended_stage, 0):
            self.rollout_promotions.record(
                requested_stage=stage,
                recommended_stage=recommended_stage,
                current_stage=current_stage,
                allowed=False,
                reason=reason,
                blocker=f"Requested stage {stage} exceeds current recommendation {recommended_stage}.",
            )
            raise ValueError(f"Requested stage {stage} exceeds current recommendation {recommended_stage}.")
        policy = self.rollout.set_policy(stage, reason=reason or "promoted via go-live gate", source="manual")
        self.rollout_promotions.record(
            requested_stage=stage,
            recommended_stage=recommended_stage,
            current_stage=current_stage,
            allowed=True,
            reason=reason,
            blocker=None,
        )
        self.audit.log(
            category="operations",
            action="rollout_policy_promote",
            details={
                "stage": policy.stage,
                "allocation_ratio": policy.allocation_ratio,
                "recommended_stage": recommended_stage,
                "reason": reason,
            },
        )
        return self.go_live_summary()




    def review_strategy_allocations(self, as_of: date) -> dict[str, object]:
        strategy_signals = {
            strategy.strategy_id: strategy.generate_signals(as_of)
            for strategy in self.research_strategies
        }
        recommendation_report = self.research.recommend_strategy_actions(as_of, strategy_signals)
        result = self.allocations.review(recommendation_report)
        self.audit.log(
            category="research",
            action="allocation_review",
            details={
                "active_count": len(result["summary"]["active"]),
                "paper_only_count": len(result["summary"]["paper_only"]),
            },
        )
        return result




    def execution_gate_summary(self, as_of: date | None = None) -> dict[str, object]:
        evaluation_date = as_of or date.today()
        alerts_summary = self.alerts.latest_summary()
        broker_diagnostics = self.adapter_factory.broker_diagnostics()
        broker_validation = self.adapter_factory.validate_futu_connection()
        data_quality = self.data_quality_summary()
        history_sync = self.history_sync.summary()
        acceptance = self.operations.acceptance_summary()
        rollout = acceptance.get("rollout", {}) if isinstance(acceptance, dict) else {}
        policy = self.rollout.summary()
        allocation_summary = self.allocations.summary()
        backend = str(broker_diagnostics.get("backend", self.adapter_factory.broker_backend_name()))
        stage_rank = {"hold": 0, "10%": 1, "30%": 2, "100%": 3}
        reasons: list[dict[str, object]] = []

        if int(alerts_summary.get("count", 0)) > 0:
            reasons.append(
                {
                    "type": "alerts",
                    "severity": "warning" if backend == "simulated" else "error",
                    "detail": f"{alerts_summary['count']} active alerts require review before execution.",
                }
            )
        if not data_quality["ready"]:
            reasons.append(
                {
                    "type": "data_quality",
                    "severity": "warning" if backend == "simulated" else "error",
                    "detail": "Local history coverage is incomplete for the current review window.",
                }
            )
        if not history_sync["healthy"] or history_sync["stale"]:
            reasons.append(
                {
                    "type": "history_sync",
                    "severity": "warning" if backend == "simulated" else "error",
                    "detail": "History sync is unhealthy or stale.",
                }
            )
        if backend == "futu":
            checks = broker_validation.get("checks", {}) if isinstance(broker_validation, dict) else {}
            quote_ok = checks.get("quote", {}).get("status") in {"ok", "skipped"} if isinstance(checks, dict) else False
            trade_ok = checks.get("trade", {}).get("status") in {"ok", "skipped"} if isinstance(checks, dict) else False
            if not broker_diagnostics.get("healthy", False) or not quote_ok or not trade_ok:
                reasons.append(
                    {
                        "type": "broker",
                        "severity": "error",
                        "detail": "Broker health or validation checks are not green.",
                    }
                )
        if not allocation_summary["active"]:
            reasons.append(
                {
                    "type": "allocation",
                    "severity": "warning",
                    "detail": "No active strategy allocations are available for the next cycle; execution should remain idle or paper-only.",
                }
            )
        recommended_stage = str(rollout.get("current_recommendation", "hold"))
        active_stage = str(policy.get("stage", "100%"))
        if stage_rank.get(active_stage, 3) > stage_rank.get(recommended_stage, 0):
            reasons.append(
                {
                    "type": "rollout_policy",
                    "severity": "warning" if backend == "simulated" else "error",
                    "detail": f"Active rollout stage {active_stage} exceeds recommendation {recommended_stage}.",
                }
            )

        hard_blocks = [reason for reason in reasons if reason["severity"] == "error"]
        return {
            "as_of": evaluation_date,
            "backend": backend,
            "ready": len(reasons) == 0,
            "should_block": len(hard_blocks) > 0,
            "policy_stage": active_stage,
            "recommended_stage": recommended_stage,
            "active_strategy_count": len(allocation_summary["active"]),
            "alerts_count": alerts_summary.get("count", 0),
            "history_sync_healthy": history_sync["healthy"],
            "history_sync_stale": history_sync["stale"],
            "reasons": reasons,
        }




    def rebalance_plan(self, as_of: date) -> dict[str, object]:
        allocation_summary = self.allocations.summary()
        active_records = allocation_summary["active"]
        if not active_records:
            allocation_summary = self.review_strategy_allocations(as_of)["summary"]
            active_records = allocation_summary["active"]

        snapshot = self.portfolio.snapshot()
        current_weights = {position.instrument.symbol: round(position.weight, 6) for position in snapshot.positions}
        strategy_signals = {
            strategy.strategy_id: strategy.generate_signals(as_of)
            for strategy in self.active_execution_strategies()
        }
        target_weights: dict[str, float] = {}
        for record in active_records:
            strategy_id = str(record["strategy_id"])
            strategy_weight = float(record["target_weight"])
            signals = strategy_signals.get(strategy_id, [])
            positive_signals = [signal for signal in signals if signal.side == OrderSide.BUY and signal.target_weight > 0]
            total_signal_weight = sum(signal.target_weight for signal in positive_signals) or 1.0
            for signal in positive_signals:
                target_weights[signal.instrument.symbol] = round(
                    target_weights.get(signal.instrument.symbol, 0.0)
                    + strategy_weight * (signal.target_weight / total_signal_weight),
                    6,
                )

        rebalance_actions = []
        for symbol in sorted(set(current_weights) | set(target_weights)):
            current_weight = round(current_weights.get(symbol, 0.0), 6)
            target_weight = round(target_weights.get(symbol, 0.0), 6)
            delta = round(target_weight - current_weight, 6)
            if abs(delta) < 0.0001:
                continue
            rebalance_actions.append(
                {
                    "symbol": symbol,
                    "current_weight": current_weight,
                    "target_weight": target_weight,
                    "delta_weight": delta,
                    "action": "buy" if delta > 0 else "trim",
                    "estimated_notional": round(abs(delta) * snapshot.nav, 2),
                }
            )
        return {
            "as_of": as_of,
            "nav": snapshot.nav,
            "allocation_summary": allocation_summary,
            "current_weights": current_weights,
            "target_weights": target_weights,
            "rebalance_actions": rebalance_actions,
            "market_budget": allocation_summary["market_weights"],
        }




    def operations_period_report(self, window_days: int, label: str) -> dict[str, object]:
        readiness = self.operations_readiness()
        acceptance = self.operations.acceptance_summary()
        rollout = self.operations_rollout()
        execution_metrics = self.operations_execution_metrics()
        audit_events = filter_recent_items(self.audit.list_events(limit=1000), timestamp_attr="created_at", window_days=window_days)
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days)
        recoveries = filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days)
        journal_entries = filter_recent_items(self.operations.list_entries(), timestamp_attr="recorded_at", window_days=window_days)
        return build_operations_period_report(
            label=label,
            window_days=window_days,
            readiness=readiness,
            acceptance=acceptance,
            rollout=rollout,
            execution_metrics=execution_metrics,
            audit_events=audit_events,
            alerts=alerts,
            recoveries=recoveries,
            journal_entries=journal_entries,
        )




    def operations_postmortem(self, window_days: int = 7) -> dict[str, object]:
        readiness = self.operations_readiness()
        execution_metrics = self.operations_execution_metrics()
        audit_events = filter_recent_items(self.audit.list_events(limit=1000), timestamp_attr="created_at", window_days=window_days)
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days)
        recoveries = filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days)
        return build_postmortem_report(
            window_days=window_days,
            readiness=readiness,
            execution_metrics=execution_metrics,
            audit_events=audit_events,
            alerts=alerts,
            recoveries=recoveries,
        )




    def incident_replay(self, window_days: int = 7) -> dict[str, object]:
        audit_events = filter_recent_items(self.audit.list_events(limit=1000), timestamp_attr="created_at", window_days=window_days)
        alerts = filter_recent_items(self.alerts.list_alerts(), timestamp_attr="created_at", window_days=window_days)
        recoveries = filter_recent_items(self.recovery.list_attempts(), timestamp_attr="attempted_at", window_days=window_days)
        return build_incident_replay(
            window_days=window_days,
            audit_events=audit_events,
            alerts=alerts,
            recoveries=recoveries,
        )




    def record_operations_journal(self) -> dict[str, object]:
        entry = self.operations.record(self.operations_readiness())
        return {
            "entry": entry,
            "summary": self.operations.summary(),
        }




    def verify_kill_switch(self) -> dict[str, object]:
        if not self.risk.kill_switch_status()["enabled"]:
            return {
                "verified": False,
                "blocked_within_cycle": False,
                "detail": "Kill switch is not enabled",
            }
        try:
            self.run_execution_cycle(date.today())
        except RiskViolation as exc:
            return {
                "verified": True,
                "blocked_within_cycle": True,
                "detail": str(exc),
            }
        return {
            "verified": False,
            "blocked_within_cycle": False,
            "detail": "Execution cycle was not blocked",
        }




    def recovery_summary(self) -> dict[str, object]:
        return self.recovery.summary()




    def startup(self) -> None:
        if self.config.scheduler.autostart:
            self.scheduler.start()




    def shutdown(self) -> None:
        self.scheduler.stop()
        self._close_runtime_components()




    def _build_runtime_components(self) -> None:
        self.market_data = self.adapter_factory.create_market_data_adapter()
        self.market_history = MarketDataService(
            adapter=self.market_data,
            instruments=self._runtime_repositories["instrument_catalog"],
            history=self._runtime_repositories["market_history"],
        )
        self.execution = ExecutionService(
            live_broker=self.adapter_factory.create_live_broker_adapter(),
            manual_broker=self.adapter_factory.create_manual_broker_adapter(),
            approvals=self.approvals,
            repository=self._runtime_repositories["orders"],
            state_repository=self._runtime_repositories["execution_state"],
        )
        self.research = ResearchService(
            repository=self._runtime_repositories["research"],
            backtester=EventDrivenBacktester(),
            market_data=self.market_history,
        )




    def _close_runtime_components(self) -> None:
        for component in (
            getattr(self, "market_data", None),
            getattr(getattr(self, "execution", None), "_live_broker", None),
        ):
            close = getattr(component, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass







PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
TEMPLATE_DIR = PROJECT_ROOT / "templates"

app_state = TradingCatApplication()


@asynccontextmanager
async def lifespan(_: FastAPI):
    app_state.startup()
    try:
        yield
    finally:
        app_state.shutdown()


app = FastAPI(title="TradingCat V1 Control Panel", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")




JOURNAL_ACCOUNT_LABELS = {
    "total": "总账户",
    "CN": "A股账户",
    "HK": "港股账户",
    "US": "美股账户",
}




def _validate_journal_account(account: str) -> str:
    if account not in JOURNAL_ACCOUNT_LABELS:
        raise HTTPException(status_code=400, detail="account must be one of total, CN, HK, US")
    return account



def _journal_status_label(status: str | None) -> str:
    if status == "planned":
        return "有计划"
    if status == "no_trade":
        return "无交易"
    if status == "blocked":
        return "已阻塞"
    return status or "N/A"



def _journal_side_label(side: str | None) -> str:
    if side == "buy":
        return "买入"
    if side == "sell":
        return "卖出"
    return side or "N/A"



def _render_journal_metric(value: object, *, percent: bool = False) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, (int, float)):
        if percent:
            return f"{float(value) * 100:.2f}%"
        if isinstance(value, float) and not float(value).is_integer():
            return f"{float(value):.2f}"
        return f"{int(value)}"
    return str(value)



def _derive_account_plan(note: DailyTradingPlanNote, account: str) -> DailyTradingPlanNote:
    if account == "total":
        return note
    label = JOURNAL_ACCOUNT_LABELS[account]
    filtered_items = [item for item in note.items if str(item.get("market", "")) == account]
    manual_count = sum(1 for item in filtered_items if bool(item.get("requires_approval")))
    automated_count = max(len(filtered_items) - manual_count, 0)
    reasons = list(note.reasons)
    status = note.status
    if note.status == "blocked":
        headline = f"{label}今日交易计划已阻塞。"
        if not reasons:
            reasons = [f"{label}当前被执行 gate 或运行异常阻塞。"]
    elif filtered_items:
        headline = f"{label}今日有可执行交易计划。"
        reasons = [f"来自总账户计划的 {len(filtered_items)} 笔{label}计划。", *reasons[:2]]
    else:
        status = "no_trade"
        headline = f"{label}今日无交易计划。"
        reasons = [f"{label}今天没有生成可执行计划。", *reasons[:2]]
    return DailyTradingPlanNote(
        as_of=note.as_of,
        generated_at=note.generated_at,
        status=status,
        account=account,
        headline=headline,
        reasons=reasons,
        counts={
            "signal_count": len(filtered_items),
            "intent_count": len(filtered_items),
            "manual_count": manual_count,
            "automated_count": automated_count,
        },
        metrics={
            **dict(note.metrics),
            "source_account": note.account,
            "source_intent_count": int(note.counts.get("intent_count", 0)),
        },
        items=filtered_items,
    )



def _journal_plan_note(account: str = "total", as_of: date | None = None) -> DailyTradingPlanNote:
    account = _validate_journal_account(account)
    note = app_state.trading_journal.latest_plan(account=account, as_of=as_of)
    if note is not None:
        return note
    base_note = app_state.trading_journal.latest_plan(account="total", as_of=as_of)
    if base_note is None:
        base_note = app_state.generate_daily_trading_plan(as_of)
    return _derive_account_plan(base_note, account)



def _derive_account_summary(note: DailyTradingSummaryNote, plan: DailyTradingPlanNote, account: str) -> DailyTradingSummaryNote:
    if account == "total":
        return note
    label = JOURNAL_ACCOUNT_LABELS[account]
    highlights = list(note.highlights)
    blockers = list(note.blockers)
    next_actions = list(note.next_actions)
    if plan.status == "blocked" and not blockers:
        blockers = [f"{label}计划当前处于阻塞状态。"]
    if plan.status == "no_trade":
        highlights = [f"{label}今天没有生成交易计划。", *highlights[:2]]
    elif plan.items:
        symbols = "、".join(str(item.get("symbol", "?")) for item in plan.items[:3])
        highlights = [f"{label}今天关注 {symbols} 等 {len(plan.items)} 笔计划。", *highlights[:2]]
    if not next_actions:
        if plan.status == "blocked":
            next_actions = [f"优先处理 {label}的阻塞项或审批链路。"]
        elif plan.status == "planned":
            next_actions = [f"继续跟踪 {label}计划单是否进入订单与成交。"]
        else:
            next_actions = [f"继续观察 {label}，若无新信号则维持现状。"]
    headline = f"{label}今日运行摘要已生成。"
    if blockers:
        headline = f"{label}今日运行摘要已生成，存在 {len(blockers)} 个阻塞项。"
    return DailyTradingSummaryNote(
        as_of=note.as_of,
        generated_at=note.generated_at,
        account=account,
        headline=headline,
        highlights=highlights,
        blockers=blockers,
        next_actions=next_actions,
        counts=dict(note.counts),
        metrics=dict(note.metrics),
    )


def _journal_summary_note(account: str = "total", as_of: date | None = None) -> DailyTradingSummaryNote:
    account = _validate_journal_account(account)
    note = app_state.trading_journal.latest_summary(account=account, as_of=as_of)
    if note is not None:
        return note
    base_note = app_state.trading_journal.latest_summary(account="total", as_of=as_of)
    if base_note is None:
        base_note = app_state.generate_daily_trading_summary(as_of)
    plan = _journal_plan_note(account=account, as_of=as_of)
    return _derive_account_summary(base_note, plan, account)




@app.get("/signals/today")
def get_signals_today() -> list[Signal]:
    try:
        app_state.run_execution_cycle(date.today())
    except RiskViolation as exc:
        app_state.audit.log(category="risk", action="violation", status="warning", details={"source": "signals_today", "detail": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return app_state.get_signals(date.today())



@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    return HTMLResponse((TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8"))



@app.get("/dashboard/strategies/{strategy_id}", response_class=HTMLResponse)
def dashboard_strategy_page(strategy_id: str):
    try:
        app_state.strategy_by_id(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Strategy not found") from exc
    return HTMLResponse((TEMPLATE_DIR / "strategy.html").read_text(encoding="utf-8"))



@app.get("/dashboard/accounts/{account_id}", response_class=HTMLResponse)
def dashboard_account_page(account_id: str):
    if account_id not in {"total", "CN", "HK", "US"}:
        raise HTTPException(status_code=404, detail="Account not found")
    return HTMLResponse((TEMPLATE_DIR / "account.html").read_text(encoding="utf-8"))



@app.get("/dashboard/research", response_class=HTMLResponse)
def dashboard_research_page():
    return HTMLResponse((TEMPLATE_DIR / "research.html").read_text(encoding="utf-8"))



@app.get("/dashboard/journal", response_class=HTMLResponse)
def dashboard_journal_page():
    return HTMLResponse((TEMPLATE_DIR / "journal.html").read_text(encoding="utf-8"))



@app.get("/dashboard/operations", response_class=HTMLResponse)
def dashboard_operations_page():
    return HTMLResponse((TEMPLATE_DIR / "operations.html").read_text(encoding="utf-8"))



@app.get("/dashboard/summary")
def dashboard_summary(as_of: date | None = None):
    return app_state.dashboard_summary(as_of)



@app.get("/portfolio")
def get_portfolio():
    return app_state.portfolio.snapshot()



@app.get("/orders")
def get_orders():
    return app_state.execution.list_orders()



@app.post("/orders/{broker_order_id}/cancel")
def cancel_order(broker_order_id: str):
    try:
        return app_state.execution.cancel(broker_order_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.post("/orders/cancel-open")
def cancel_open_orders():
    try:
        result = app_state.execution.cancel_open_orders()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "cancelled_count": len(result["cancelled"]),
        "failed_count": len(result["failed"]),
        "reports": result["cancelled"],
        "failures": result["failed"],
    }



@app.post("/execution/reconcile")
def reconcile_execution_state():
    try:
        summary = app_state.execution.reconcile_live_state()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    applied_snapshots = []
    for order_id in summary.applied_fill_order_ids:
        report = next((item for item in app_state.execution.list_orders() if item.order_intent_id == order_id), None)
        if report is None:
            continue
        snapshot = app_state._apply_fill_to_portfolio(order_id, report.filled_quantity, report.average_price)
        if snapshot is not None:
            applied_snapshots.append({"order_intent_id": order_id, "nav": snapshot.nav, "cash": snapshot.cash})
    payload = summary.model_dump(mode="json")
    payload["applied_portfolio_updates"] = applied_snapshots
    return payload



@app.get("/execution/quality")
def execution_quality():
    return app_state.execution.execution_quality_summary()


@app.get("/execution/authorization")
def execution_authorization():
    return app_state.execution.authorization_summary()

@app.post("/approvals/{request_id}/approve")
def approve_request(request_id: str, payload: DecisionPayload):
    try:
        request = app_state.approvals.approve(request_id, payload.reason)
        report = app_state.execution.submit_approved(request_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval request not found") from exc
    app_state.audit.log(
        category="approval",
        action="approve",
        details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""},
    )
    return {"approval": request, "execution_report": report}



@app.post("/approvals/{request_id}/reject")
def reject_request(request_id: str, payload: DecisionPayload):
    try:
        request = app_state.approvals.reject(request_id, payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval request not found") from exc
    app_state.audit.log(
        category="approval",
        action="reject",
        details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""},
    )
    return request



@app.post("/approvals/{request_id}/expire")
def expire_request(request_id: str, payload: DecisionPayload):
    try:
        request = app_state.approvals.expire(request_id, payload.reason)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Approval request not found") from exc
    app_state.audit.log(
        category="approval",
        action="expire",
        details={"request_id": request.id, "status": request.status.value, "reason": payload.reason or ""},
    )
    return request



@app.post("/approvals/expire-stale")
def expire_stale_requests(hours: int = 24):
    try:
        requests = app_state.approvals.expire_stale(
            max_age=timedelta(hours=hours),
            reason=f"Expired by operator sweep after {hours}h pending window",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    app_state.audit.log(
        category="approval",
        action="expire_stale",
        details={"hours": hours, "expired_count": len(requests)},
    )
    return {
        "expired_count": len(requests),
        "requests": requests,
    }



@app.post("/kill-switch")
def set_kill_switch(enabled: bool = True, reason: str | None = None):
    event = app_state.risk.set_kill_switch(enabled, reason=reason)
    app_state.audit.log(
        category="risk",
        action="kill_switch_set",
        details={"enabled": enabled, "reason": reason or ""},
    )
    return {"enabled": enabled, "event": event}



@app.get("/kill-switch")
def get_kill_switch():
    return app_state.risk.kill_switch_status()



@app.post("/kill-switch/verify")
def verify_kill_switch():
    return app_state.verify_kill_switch()



@app.post("/reconcile/manual-fill")
def reconcile_manual_fill(fill: ManualFill):
    report = app_state.execution.reconcile_manual_fill(fill)
    snapshot = app_state._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price)
    app_state.audit.log(
        category="execution",
        action="manual_fill_reconcile",
        details={"broker_order_id": fill.broker_order_id, "order_intent_id": fill.order_intent_id},
    )
    return {
        "report": report,
        "portfolio": snapshot,
    }



@app.post("/reconcile/manual-fills/import")
def import_manual_fills(payload: ManualFillImportPayload):
    try:
        reader = csv.DictReader(StringIO(payload.csv_text), delimiter=payload.delimiter)
        fills = [ManualFill(**row) for row in reader]
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"CSV parse error: {exc}") from exc
    results = []
    for fill in fills:
        report = app_state.execution.reconcile_manual_fill(fill)
        snapshot = app_state._apply_fill_to_portfolio(fill.order_intent_id, fill.filled_quantity, fill.average_price)
        results.append({"report": report, "portfolio": snapshot})
    app_state.audit.log(
        category="execution",
        action="manual_fills_import",
        details={"count": len(fills)},
    )
    return {"imported_count": len(fills), "results": results}

@app.get("/journal/plans")
def list_trading_plans(account: str | None = None):
    return app_state.trading_journal.list_plans(account)



@app.get("/journal/plans/latest")
def latest_trading_plan(account: str = "total", as_of: date | None = None):
    note = app_state.trading_journal.latest_plan(account=account, as_of=as_of)
    return note or app_state.generate_daily_trading_plan(as_of)



@app.post("/journal/plans/generate")
def generate_trading_plan(as_of: date | None = None):
    return app_state.generate_daily_trading_plan(as_of)



@app.get("/journal/summaries")
def list_trading_summaries(account: str | None = None):
    return app_state.trading_journal.list_summaries(account)



@app.get("/journal/summaries/latest")
def latest_trading_summary(account: str = "total", as_of: date | None = None):
    note = app_state.trading_journal.latest_summary(account=account, as_of=as_of)
    return note or app_state.generate_daily_trading_summary(as_of)



@app.post("/journal/summaries/generate")
def generate_trading_summary(as_of: date | None = None):
    return app_state.generate_daily_trading_summary(as_of)



@app.get("/ops/postmortem")
def operations_postmortem(window_days: int = 7):
    if window_days < 1 or window_days > 30:
        raise HTTPException(status_code=400, detail="window_days must be between 1 and 30")
    return app_state.operations_postmortem(window_days=window_days)



@app.get("/ops/incidents/replay")
def operations_incident_replay(window_days: int = 7):
    if window_days < 1 or window_days > 30:
        raise HTTPException(status_code=400, detail="window_days must be between 1 and 30")
    return app_state.incident_replay(window_days=window_days)

@app.post("/portfolio/rebalance-plan")
def portfolio_rebalance_plan(payload: RebalancePlanPayload):
    return app_state.rebalance_plan(payload.as_of or date.today())



@app.get("/broker/probe")
def probe_broker():
    try:
        return {
            "live": app_state.execution._live_broker.probe(),
            "manual": app_state.execution._manual_broker.probe(),
        }
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc



@app.post("/broker/recover")
def recover_broker_runtime():
    try:
        result = app_state.recover_runtime()
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    app_state.audit.log(
        category="recovery",
        action="broker_recover",
        status="ok" if result["attempt"].status != "failed" else "error",
        details={"status": result["attempt"].status, "changed": result["changed"]},
    )
    return result



@app.get("/broker/recovery-attempts")
def list_recovery_attempts():
    return app_state.recovery.list_attempts()



@app.get("/broker/recovery-summary")
def broker_recovery_summary():
    return app_state.recovery_summary()



@app.post("/market-data/smoke-test")
def market_data_smoke_test(payload: MarketDataSmokePayload):
    try:
        return app_state.run_market_data_smoke_test(
            symbols=payload.symbols,
            include_bars=payload.include_bars,
            include_option_chain=payload.include_option_chain,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/data/instruments")
def list_instruments():
    return app_state.market_history.list_instruments()



@app.post("/data/history/sync")
def sync_history(payload: HistorySyncPayload):
    try:
        return app_state.sync_market_history(
            symbols=payload.symbols,
            start=payload.start,
            end=payload.end,
            include_corporate_actions=payload.include_corporate_actions,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/data/history/bars")
def get_history_bars(symbol: str, start: date, end: date):
    try:
        return app_state.market_history.get_bars(symbol, start, end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/data/history/coverage")
def get_history_coverage(symbols: str | None = None, start: date | None = None, end: date | None = None):
    requested_symbols = [item.strip() for item in symbols.split(",") if item.strip()] if symbols else None
    try:
        return app_state.market_history.summarize_history_coverage(requested_symbols, start, end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@app.get("/data/history/sync-runs")
def get_history_sync_runs():
    return app_state.history_sync.list_runs()



@app.get("/data/history/sync-status")
def get_history_sync_status():
    return app_state.history_sync.summary()



@app.get("/data/history/repair-plan")
def get_history_repair_plan(symbols: str | None = None, start: date | None = None, end: date | None = None):
    requested_symbols = symbols.split(",") if symbols else None
    try:
        return app_state.history_sync_repair_plan(requested_symbols, start, end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc



@app.post("/data/history/repair")
def repair_history(payload: HistoryRepairPayload):
    try:
        return app_state.repair_market_history_gaps(
            symbols=payload.symbols,
            start=payload.start,
            end=payload.end,
            include_corporate_actions=payload.include_corporate_actions,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.post("/data/fx/sync")
def sync_fx_rates(payload: FxSyncPayload):
    try:
        return app_state.market_history.sync_fx_rates(
            base_currency=payload.base_currency,
            quote_currencies=payload.quote_currencies,
            start=payload.start,
            end=payload.end,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/data/fx/rates")
def get_fx_rates(base_currency: str, quote_currency: str, start: date, end: date):
    try:
        return app_state.market_history.get_fx_rates(base_currency, quote_currency, start, end)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.get("/data/quality")
def get_data_quality(lookback_days: int = 30):
    if lookback_days < 1 or lookback_days > 365:
        raise HTTPException(status_code=400, detail="lookback_days must be between 1 and 365")
    return app_state.data_quality_summary(lookback_days=lookback_days)



@app.get("/data/history/corporate-actions")
def get_corporate_actions(symbol: str, start: date, end: date):
    try:
        return app_state.market_history.get_corporate_actions(symbol, start, end)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc



@app.post("/execution/preview")
def execution_preview(payload: ExecutionPreviewPayload):
    try:
        result = app_state.preview_execution(payload.as_of)
    except RiskViolation as exc:
        app_state.audit.log(category="risk", action="violation", status="warning", details={"source": "execution_preview", "detail": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        app_state.audit.log(category="execution", action="preview_error", status="error", details={"detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    app_state.audit.log(
        category="execution",
        action="preview_ok",
        details={
            "intent_count": result["intent_count"],
            "manual_count": result["manual_count"],
            "gate_ready": result["gate"]["ready"],
            "gate_should_block": result["gate"]["should_block"],
        },
    )
    return result


@app.post("/execution/run")
def run_execution(payload: ExecutionRunPayload):
    try:
        result = app_state.run_execution_cycle(payload.as_of or date.today(), enforce_gate=payload.enforce_gate)
    except RiskViolation as exc:
        app_state.audit.log(category="risk", action="violation", status="warning", details={"source": "execution_run", "detail": str(exc)})
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        app_state.audit.log(category="execution", action="run_error", status="error", details={"detail": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    app_state.audit.log(
        category="execution",
        action="run_ok",
        details={
            "signal_count": result["signal_count"],
            "intent_count": result["intent_count"],
            "submitted_count": len(result["submitted_orders"]),
            "failed_count": len(result["failed_orders"]),
        },
    )
    return result


@app.post("/portfolio/risk-state")
def update_portfolio_risk_state(payload: RiskStatePayload):
    snapshot = app_state.portfolio.update_risk_state(
        drawdown=payload.drawdown,
        daily_pnl=payload.daily_pnl,
        weekly_pnl=payload.weekly_pnl,
    )
    return snapshot


@app.get("/execution/gate")
def execution_gate(as_of: date | None = None):
    return app_state.execution_gate_summary(as_of)


@app.get("/market-sessions")
def market_sessions():
    return app_state.market_calendar.sessions()


@app.get("/scheduler/jobs")
def list_scheduler_jobs():
    return app_state.scheduler.list_jobs()


@app.post("/scheduler/jobs/{job_id}/run")
def run_scheduler_job(job_id: str):
    try:
        result = app_state.scheduler.run_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found") from exc
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result


@app.get("/broker/validate")
def validate_broker():
    return app_state.broker_validation()


@app.get("/ops/readiness")
def operations_readiness():
    return app_state.operations_readiness()


@app.get("/ops/rollout")
def operations_rollout():
    return app_state.operations_rollout()


@app.get("/ops/rollout/checklist")
def rollout_checklist(stage: str, as_of: date | None = None):
    try:
        return app_state.rollout_checklist(stage, as_of)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ops/rollout/promote")
def promote_rollout(stage: str, reason: str | None = None):
    try:
        return app_state.promote_rollout_stage(stage, reason)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/ops/go-live")
def go_live_summary(as_of: date | None = None):
    return app_state.go_live_summary(as_of)


@app.get("/ops/acceptance")
def live_acceptance(as_of: date | None = None, incident_window_days: int = 7):
    return app_state.live_acceptance_summary(as_of, incident_window_days)


@app.get("/ops/execution-metrics")
def operations_execution_metrics():
    return app_state.operations_execution_metrics()


@app.post("/ops/journal/record")
def record_operations_journal():
    return app_state.record_operations_journal()


@app.get("/ops/journal")
def list_operations_journal():
    return app_state.operations.list_entries()


@app.get("/reports/latest")
@app.get("/ops/daily-report")
def operations_daily_report():
    return app_state.operations_period_report(window_days=1, label="daily")


@app.post("/research/allocations/review")
def review_strategy_allocations(as_of: date | None = None):
    return app_state.review_strategy_allocations(as_of or date.today())


@app.get("/research/allocations/summary")
def research_allocations_summary():
    return app_state.allocations.summary()


@app.get("/research/strategies/{strategy_id}")
def research_strategy_detail(strategy_id: str, as_of: date | None = None):
    try:
        strategy = app_state.strategy_by_id(strategy_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Strategy not found") from exc
    evaluation_date = as_of or date.today()
    signals = strategy.generate_signals(evaluation_date)
    strategy_signals = {strategy_id: signals}
    detail = app_state.research.strategy_detail(strategy_id, evaluation_date, signals)
    return detail


@app.get("/research/scorecard")
def research_scorecard(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    strategy_signals = {
        strategy.strategy_id: strategy.generate_signals(evaluation_date)
        for strategy in app_state.research_strategies
    }
    return app_state.research.summarize_strategy_report(evaluation_date, strategy_signals)


@app.post("/research/scorecard/run")
def research_scorecard_run(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    strategy_signals = {
        strategy.strategy_id: strategy.generate_signals(evaluation_date)
        for strategy in app_state.research_strategies
    }
    return app_state.research.recommend_strategy_actions(evaluation_date, strategy_signals)


@app.get("/research/candidates/scorecard")
def research_candidates_scorecard(as_of: date | None = None):
    evaluation_date = as_of or date.today()
    strategy_signals = {
        strategy.strategy_id: strategy.generate_signals(evaluation_date)
        for strategy in app_state.research_strategies
    }
    return app_state.research.build_profit_scorecard(evaluation_date, strategy_signals)


@app.get("/research/backtests")
def list_backtests():
    return app_state.research.list_experiments()


@app.get("/research/backtests/compare")
def compare_backtests(left_id: str, right_id: str):
    try:
        return app_state.research.compare_experiments(left_id, right_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/research/news/summarize")
def summarize_news(payload: ResearchNewsSummaryPayload):
    items = [{"title": item.title, "body": item.body, "symbols": item.symbols} for item in payload.items]
    return app_state.research.summarize_news(items)


@app.get("/preflight")
def preflight():
    result = build_startup_preflight(app_state.config)
    return {"preflight": result, "diagnostics": summarize_validation_diagnostics(result)}


@app.get("/audit/events")
def list_audit_events(limit: int = 100):
    return app_state.audit.list_events(limit=limit)


@app.get("/alerts")
def list_alerts():
    return app_state.alerts.list_alerts()


@app.post("/compliance/checklist/{item_id}")
def update_compliance_checklist(item_id: str, payload: ChecklistItemPayload):
    try:
        return app_state.compliance.update_checklist_item(item_id, payload.status, payload.notes)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/compliance/checklist")
def get_compliance_checklist():
    return app_state.compliance.checklist()


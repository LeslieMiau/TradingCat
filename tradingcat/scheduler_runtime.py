from __future__ import annotations

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Callable

from tradingcat.domain.models import Market

if TYPE_CHECKING:
    from tradingcat.app import TradingCatApplication


@dataclass(frozen=True, slots=True)
class SchedulerRegistration:
    job_id: str
    name: str
    description: str
    timezone: str
    local_time: time
    market: Market | None
    handler_name: str


class ApplicationSchedulerRuntime:
    def __init__(self, app: "TradingCatApplication") -> None:
        self._app = app

    def register_jobs(self) -> None:
        for job in _JOB_REGISTRATIONS:
            handler: Callable[[], str] = getattr(self, job.handler_name)
            self._app.scheduler.register(
                job_id=job.job_id,
                name=job.name,
                description=job.description,
                timezone=job.timezone,
                local_time=job.local_time,
                market=job.market,
                handler=handler,
            )
        interval = int(getattr(self._app.config, "intraday_risk_tick_seconds", 60))
        if interval > 0:
            self._app.scheduler.register_interval(
                job_id="intraday_risk_tick",
                name="Intraday Risk Tick",
                description="Poll portfolio risk state; auto-activate kill switch on hard breach or NAV unavailability",
                interval_seconds=interval,
                handler=self.run_intraday_risk_tick_job,
            )

    def run_intraday_risk_tick_job(self) -> str:
        result = self._app.run_intraday_risk_tick()
        if result["kill_switch_activated"]:
            return f"Kill switch activated (severity={result['severity']})"
        if not result["nav_available"]:
            return "NAV unavailable (kill switch already active)"
        if result["breached"]:
            return f"Breached rules: {len(result['breached'])} (kill switch was already active)"
        return "ok"

    def run_daily_signal_cycle(self) -> str:
        result = self._app.run_execution_cycle(date.today(), enforce_gate=False)
        if "submitted_orders" not in result:
            return "Execution gate blocked"
        return f"Generated {result['signal_count']} signals and submitted {len(result['submitted_orders'])} orders"

    def run_market_history_sync_job(self) -> str:
        result = self._app.sync_market_history(start=date.today() - timedelta(days=7), end=date.today())
        return f"Synced {result['instrument_count']} instruments"

    def run_market_history_gap_repair_job(self) -> str:
        result = self._app.repair_market_history_gaps(start=date.today() - timedelta(days=30), end=date.today())
        return f"Repaired {result['repair_count']} symbols"

    def run_backtests_job(self) -> str:
        experiments = []
        evaluation_date = date.today()
        for strategy in self._app.research_strategies:
            signals = strategy.generate_signals(evaluation_date)
            experiments.append(self._app.research.run_experiment(strategy.strategy_id, evaluation_date, signals))
        return f"Ran {len(experiments)} backtests"

    def run_research_selection_review_job(self) -> str:
        result = self._app.review_strategy_selections(date.today())
        self._app.review_strategy_allocations(date.today())
        return f"Updated {len(result['updated'])} strategy selections"

    def run_portfolio_snapshot_job(self) -> str:
        snapshot = self._app.portfolio.snapshot()
        return f"Persisted portfolio snapshot: NAV={snapshot.nav:.2f}"

    def run_broker_auto_recovery_job(self) -> str:
        result = self._app.recover_runtime(trigger="automatic")
        return str(result["after"]["broker_status"]["detail"])

    def run_approval_expiry_job(self) -> str:
        expired = self._app.approvals.expire_stale(
            timedelta(minutes=self._app.config.approval_expiry_minutes),
            reason="Scheduled expiry sweep",
        )
        return f"Expired {len(expired)} approval requests"

    def run_operations_journal_job(self) -> str:
        self._app.record_operations_journal()
        return "Recorded operations journal entry"

    def run_acceptance_evidence_job(self) -> str:
        snapshot = self._app.capture_acceptance_evidence(notes=["scheduled_eod_capture"])
        return f"Captured acceptance gates ({snapshot['status']}) for {snapshot['as_of']}"

    def run_history_audit_job(self) -> str:
        run = self._app.run_history_audit(window_days=90, notes=["scheduled_weekly_audit"])
        return (
            f"History audit ({run['status']}): min_coverage={run['minimum_coverage_ratio']} "
            f"missing={run['missing_symbol_count']}"
        )

    def run_trade_ledger_reconciliation_job(self) -> str:
        run = self._app.run_trade_ledger_reconciliation(
            notes=["scheduled_eod_ledger_audit"]
        )
        return (
            f"Trade ledger reconciliation ({run['status']}): "
            f"broker_fills={run['broker_fill_count']} ledger_rows={run['ledger_entry_count']} "
            f"missing_ledger={run['missing_ledger_count']} "
            f"missing_broker={run['missing_broker_count']} "
            f"amount_drift={run['amount_drift_count']}"
        )

    def run_daily_trading_plan_job(self) -> str:
        return self._app.generate_daily_trading_plan(date.today()).headline

    def run_daily_trading_summary_job(self) -> str:
        return self._app.generate_daily_trading_summary(date.today()).headline

    def run_sentiment_history_persist_job(self) -> str:
        """Snapshot current sentiment and persist to DuckDB for sparkline history."""
        try:
            snapshot = self._app.market_sentiment.snapshot()
            snapshot_dict = snapshot.model_dump(mode="json")
            rows = self._app.sentiment_history.persist_snapshot(snapshot_dict)
            pruned = self._app.sentiment_history.prune(keep_days=90)
            return f"Persisted {rows} indicator rows, pruned {pruned} old rows"
        except Exception as exc:
            return f"Sentiment persist failed: {exc}"


_JOB_REGISTRATIONS = [
    SchedulerRegistration(
        job_id="us_signal_generation",
        name="US Signal Generation",
        description="Generate and risk-check daily US/HK/CN signals",
        timezone="America/New_York",
        local_time=time(8, 45),
        market=Market.US,
        handler_name="run_daily_signal_cycle",
    ),
    SchedulerRegistration(
        job_id="market_data_history_sync",
        name="Market Data History Sync",
        description="Refresh recent local history coverage for tracked instruments",
        timezone="Asia/Shanghai",
        local_time=time(7, 30),
        market=Market.CN,
        handler_name="run_market_history_sync_job",
    ),
    SchedulerRegistration(
        job_id="market_data_gap_repair",
        name="Market Data Gap Repair",
        description="Repair missing history windows for tracked instruments",
        timezone="Asia/Shanghai",
        local_time=time(7, 40),
        market=Market.CN,
        handler_name="run_market_history_gap_repair_job",
    ),
    SchedulerRegistration(
        job_id="research_backtest_refresh",
        name="Research Backtest Refresh",
        description="Run all strategy backtests and persist experiment snapshots",
        timezone="Asia/Shanghai",
        local_time=time(7, 0),
        market=Market.CN,
        handler_name="run_backtests_job",
    ),
    SchedulerRegistration(
        job_id="research_selection_review",
        name="Research Selection Review",
        description="Refresh persisted strategy admission decisions and target allocations",
        timezone="Asia/Shanghai",
        local_time=time(7, 10),
        market=Market.CN,
        handler_name="run_research_selection_review_job",
    ),
    SchedulerRegistration(
        job_id="portfolio_risk_snapshot",
        name="Portfolio Risk Snapshot",
        description="Persist current portfolio snapshot for dashboard review",
        timezone="Asia/Shanghai",
        local_time=time(18, 0),
        market=Market.CN,
        handler_name="run_portfolio_snapshot_job",
    ),
    SchedulerRegistration(
        job_id="broker_auto_recovery",
        name="Broker Auto Recovery",
        description="Attempt runtime rebuild when broker validation degrades",
        timezone="Asia/Shanghai",
        local_time=time(8, 55),
        market=Market.CN,
        handler_name="run_broker_auto_recovery_job",
    ),
    SchedulerRegistration(
        job_id="approval_expiry_sweep",
        name="Approval Expiry Sweep",
        description="Expire stale manual approval requests",
        timezone="Asia/Shanghai",
        local_time=time(8, 30),
        market=Market.CN,
        handler_name="run_approval_expiry_job",
    ),
    SchedulerRegistration(
        job_id="operations_readiness_journal",
        name="Operations Readiness Journal",
        description="Persist daily readiness evidence for paper trading acceptance",
        timezone="Asia/Shanghai",
        local_time=time(18, 15),
        market=Market.CN,
        handler_name="run_operations_journal_job",
    ),
    SchedulerRegistration(
        job_id="daily_trading_plan_archive",
        name="Daily Trading Plan Archive",
        description="Generate and archive the daily trading plan",
        timezone="Asia/Shanghai",
        local_time=time(8, 20),
        market=Market.CN,
        handler_name="run_daily_trading_plan_job",
    ),
    SchedulerRegistration(
        job_id="acceptance_evidence_capture",
        name="Acceptance Gate Evidence Capture",
        description="Snapshot Stage-C acceptance gates for the wall-clock paper-trading timeline",
        timezone="Asia/Shanghai",
        local_time=time(18, 25),
        market=Market.CN,
        handler_name="run_acceptance_evidence_job",
    ),
    SchedulerRegistration(
        job_id="daily_trading_summary_archive",
        name="Daily Trading Summary Archive",
        description="Generate and archive the daily trading summary",
        timezone="Asia/Shanghai",
        local_time=time(18, 20),
        market=Market.CN,
        handler_name="run_daily_trading_summary_job",
    ),
    SchedulerRegistration(
        job_id="history_audit_daily",
        name="History Audit",
        description="Deep 90-day coverage audit to catch silent gaps missed by daily sync",
        timezone="Asia/Shanghai",
        local_time=time(6, 30),
        market=Market.CN,
        handler_name="run_history_audit_job",
    ),
    SchedulerRegistration(
        job_id="trade_ledger_reconciliation_daily",
        name="Trade Ledger Reconciliation",
        description="Daily ledger completeness audit catching silent dropped entries",
        timezone="Asia/Shanghai",
        local_time=time(18, 30),
        market=Market.CN,
        handler_name="run_trade_ledger_reconciliation_job",
    ),
    SchedulerRegistration(
        job_id="sentiment_history_persist",
        name="Sentiment History Persist",
        description="Snapshot market sentiment and persist to DuckDB for 30d sparkline",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        market=None,
        handler_name="run_sentiment_history_persist_job",
    ),
]

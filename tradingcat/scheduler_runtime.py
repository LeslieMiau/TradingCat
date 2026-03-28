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

    def run_daily_trading_plan_job(self) -> str:
        return self._app.generate_daily_trading_plan(date.today()).headline

    def run_daily_trading_summary_job(self) -> str:
        return self._app.generate_daily_trading_summary(date.today()).headline


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
        job_id="daily_trading_summary_archive",
        name="Daily Trading Summary Archive",
        description="Generate and archive the daily trading summary",
        timezone="Asia/Shanghai",
        local_time=time(18, 20),
        market=Market.CN,
        handler_name="run_daily_trading_summary_job",
    ),
]

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import TYPE_CHECKING, Callable

from tradingcat.domain.models import Market


logger = logging.getLogger(__name__)

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
                name="盘中风控巡检",
                description="轮询组合风险状态；遇到硬性违规或 NAV 不可用时自动激活紧急关停",
                interval_seconds=interval,
                handler=self.run_intraday_risk_tick_job,
            )
        advisory_cfg = getattr(self._app.config, "advisory_report", None)
        if advisory_cfg is not None and advisory_cfg.enabled:
            self._app.scheduler.register(
                job_id="advisory_research_daily",
                name="每日投研参考报告",
                description=(
                    "生成每日投研参考报告（股票池筛选 + 资讯 + 可选 LLM 分析师）；"
                    "只读产物保存在 data/reports/advisory/"
                ),
                timezone=advisory_cfg.cron_timezone,
                local_time=time(advisory_cfg.cron_hour, advisory_cfg.cron_minute),
                market=Market.CN,
                handler=self.run_advisory_research_job,
            )

    def run_intraday_risk_tick_job(self) -> str:
        result = self._app.run_intraday_risk_tick()
        if result["kill_switch_activated"]:
            return f"紧急关停已激活（严重级别={result['severity']}）"
        if not result["nav_available"]:
            return "NAV 不可用（紧急关停已处于激活状态）"
        if result["breached"]:
            return f"触发规则数：{len(result['breached'])}（紧急关停此前已激活）"
        return "正常"

    def run_daily_signal_cycle(self) -> str:
        result = self._app.run_execution_cycle(date.today(), enforce_gate=False)
        if "submitted_orders" not in result:
            return "执行门禁阻塞"
        return f"生成 {result['signal_count']} 条信号，提交 {len(result['submitted_orders'])} 笔订单"

    def run_market_history_sync_job(self) -> str:
        result = self._app.sync_market_history(start=date.today() - timedelta(days=7), end=date.today())
        return f"已同步 {result['instrument_count']} 个标的"

    def run_market_history_gap_repair_job(self) -> str:
        result = self._app.repair_market_history_gaps(start=date.today() - timedelta(days=30), end=date.today())
        return f"已修复 {result['repair_count']} 个标的"

    def run_backtests_job(self) -> str:
        experiments = []
        evaluation_date = date.today()
        for strategy in self._app.research_strategies:
            signals = strategy.generate_signals(evaluation_date)
            experiments.append(self._app.research.run_experiment(strategy.strategy_id, evaluation_date, signals))
        return f"已运行 {len(experiments)} 个回测"

    def run_research_selection_review_job(self) -> str:
        result = self._app.review_strategy_selections(date.today())
        self._app.review_strategy_allocations(date.today())
        return f"已更新 {len(result['updated'])} 个策略筛选结果"

    def run_portfolio_snapshot_job(self) -> str:
        snapshot = self._app.portfolio.snapshot()
        return f"已持久化组合快照：NAV={snapshot.nav:.2f}"

    def run_broker_auto_recovery_job(self) -> str:
        result = self._app.recover_runtime(trigger="automatic")
        return str(result["after"]["broker_status"]["detail"])

    def run_approval_expiry_job(self) -> str:
        expired = self._app.approvals.expire_stale(
            timedelta(minutes=self._app.config.approval_expiry_minutes),
            reason="定时审批过期清理",
        )
        return f"已过期 {len(expired)} 条审批请求"

    def run_operations_journal_job(self) -> str:
        self._app.record_operations_journal()
        return "已记录运营日报条目"

    def run_acceptance_evidence_job(self) -> str:
        snapshot = self._app.capture_acceptance_evidence(notes=["scheduled_eod_capture"])
        return f"已采集 {snapshot['as_of']} 的验收门禁证据（{snapshot['status']}）"

    def run_advisory_research_job(self) -> str:
        try:
            result = self._app.run_daily_advisory_research()
        except Exception as exc:
            logger.exception("Advisory research job failed: %s", exc)
            return f"投研参考报告失败：{exc}"
        if result.get("skipped"):
            return f"投研参考报告已跳过（{result.get('reason')}）"
        return (
            f"投研参考报告已写入 {result['output_path']}："
            f"{result['candidate_count']} 个候选，{result['news_count']} 条资讯，"
            f"调用分析师={result['analyst_called']}，清理={result['pruned_count']}"
        )

    def run_history_audit_job(self) -> str:
        run = self._app.run_history_audit(window_days=90, notes=["scheduled_weekly_audit"])
        return (
            f"历史数据审计（{run['status']}）：最低覆盖率={run['minimum_coverage_ratio']} "
            f"缺失标的={run['missing_symbol_count']}"
        )

    def run_trade_ledger_reconciliation_job(self) -> str:
        run = self._app.run_trade_ledger_reconciliation(
            notes=["scheduled_eod_ledger_audit"]
        )
        return (
            f"交易流水对账（{run['status']}）："
            f"券商成交={run['broker_fill_count']} 流水行={run['ledger_entry_count']} "
            f"缺流水={run['missing_ledger_count']} "
            f"缺券商成交={run['missing_broker_count']} "
            f"金额漂移={run['amount_drift_count']}"
        )

    def run_daily_trading_plan_job(self) -> str:
        return self._app.generate_daily_trading_plan(date.today()).headline

    def run_daily_trading_summary_job(self) -> str:
        return self._app.generate_daily_trading_summary(date.today()).headline

    def run_sentiment_history_persist_job(self) -> str:
        """采集当前情绪并持久化到 DuckDB，供趋势线使用。"""
        try:
            snapshot = self._app.market_sentiment.snapshot()
            snapshot_dict = snapshot.model_dump(mode="json")
            rows = self._app.sentiment_history.persist_snapshot(snapshot_dict)
            pruned = self._app.sentiment_history.prune(keep_days=90)
            return f"已持久化 {rows} 行指标，清理 {pruned} 行旧数据"
        except Exception as exc:
            return f"情绪持久化失败：{exc}"


_JOB_REGISTRATIONS = [
    SchedulerRegistration(
        job_id="us_signal_generation",
        name="美股信号生成",
        description="生成并风控检查每日美股/港股/A股信号",
        timezone="America/New_York",
        local_time=time(8, 45),
        market=Market.US,
        handler_name="run_daily_signal_cycle",
    ),
    SchedulerRegistration(
        job_id="market_data_history_sync",
        name="行情历史同步",
        description="刷新跟踪标的的近期本地历史覆盖",
        timezone="Asia/Shanghai",
        local_time=time(7, 30),
        market=Market.CN,
        handler_name="run_market_history_sync_job",
    ),
    SchedulerRegistration(
        job_id="market_data_gap_repair",
        name="行情缺口修复",
        description="修复跟踪标的缺失的历史窗口",
        timezone="Asia/Shanghai",
        local_time=time(7, 40),
        market=Market.CN,
        handler_name="run_market_history_gap_repair_job",
    ),
    SchedulerRegistration(
        job_id="research_backtest_refresh",
        name="研究回测刷新",
        description="运行全部策略回测并持久化实验快照",
        timezone="Asia/Shanghai",
        local_time=time(7, 0),
        market=Market.CN,
        handler_name="run_backtests_job",
    ),
    SchedulerRegistration(
        job_id="research_selection_review",
        name="策略筛选复核",
        description="刷新已持久化的策略准入决策和目标配置",
        timezone="Asia/Shanghai",
        local_time=time(7, 10),
        market=Market.CN,
        handler_name="run_research_selection_review_job",
    ),
    SchedulerRegistration(
        job_id="portfolio_risk_snapshot",
        name="组合风险快照",
        description="持久化当前组合快照供控制台复盘",
        timezone="Asia/Shanghai",
        local_time=time(18, 0),
        market=Market.CN,
        handler_name="run_portfolio_snapshot_job",
    ),
    SchedulerRegistration(
        job_id="broker_auto_recovery",
        name="券商自动恢复",
        description="券商校验降级时尝试重建运行时",
        timezone="Asia/Shanghai",
        local_time=time(8, 55),
        market=Market.CN,
        handler_name="run_broker_auto_recovery_job",
    ),
    SchedulerRegistration(
        job_id="approval_expiry_sweep",
        name="审批过期清理",
        description="将过期的人工审批请求标记为过期",
        timezone="Asia/Shanghai",
        local_time=time(8, 30),
        market=Market.CN,
        handler_name="run_approval_expiry_job",
    ),
    SchedulerRegistration(
        job_id="operations_readiness_journal",
        name="运营就绪日报",
        description="持久化纸面交易验收所需的每日就绪证据",
        timezone="Asia/Shanghai",
        local_time=time(18, 15),
        market=Market.CN,
        handler_name="run_operations_journal_job",
    ),
    SchedulerRegistration(
        job_id="daily_trading_plan_archive",
        name="每日交易计划归档",
        description="生成并归档每日交易计划",
        timezone="Asia/Shanghai",
        local_time=time(8, 20),
        market=Market.CN,
        handler_name="run_daily_trading_plan_job",
    ),
    SchedulerRegistration(
        job_id="acceptance_evidence_capture",
        name="验收门禁证据采集",
        description="为真实时间纸面交易时间线采集 Stage-C 验收门禁快照",
        timezone="Asia/Shanghai",
        local_time=time(18, 25),
        market=Market.CN,
        handler_name="run_acceptance_evidence_job",
    ),
    SchedulerRegistration(
        job_id="daily_trading_summary_archive",
        name="每日交易总结归档",
        description="生成并归档每日交易总结",
        timezone="Asia/Shanghai",
        local_time=time(18, 20),
        market=Market.CN,
        handler_name="run_daily_trading_summary_job",
    ),
    SchedulerRegistration(
        job_id="history_audit_daily",
        name="历史数据审计",
        description="执行 90 日深度覆盖审计，捕捉每日同步漏掉的静默缺口",
        timezone="Asia/Shanghai",
        local_time=time(6, 30),
        market=Market.CN,
        handler_name="run_history_audit_job",
    ),
    SchedulerRegistration(
        job_id="trade_ledger_reconciliation_daily",
        name="交易流水对账",
        description="每日审计流水完整性，捕捉静默丢失条目",
        timezone="Asia/Shanghai",
        local_time=time(18, 30),
        market=Market.CN,
        handler_name="run_trade_ledger_reconciliation_job",
    ),
    SchedulerRegistration(
        job_id="sentiment_history_persist",
        name="市场情绪历史持久化",
        description="采集市场情绪快照并写入 DuckDB，用于 30 日趋势线",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        market=None,
        handler_name="run_sentiment_history_persist_job",
    ),
]

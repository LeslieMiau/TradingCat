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
        insight_interval = int(getattr(self._app.config, "intraday_insight_seconds", 300))
        if insight_interval > 0:
            self._app.scheduler.register_interval(
                job_id="intraday_insight_scan",
                name="盘中洞察扫描",
                description="周期性运行 InsightEngine 检测器，捕捉盘中异常",
                interval_seconds=insight_interval,
                handler=self.run_intraday_insight_scan_job,
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
            reason="定时审批过期清理",
        )
        return f"已过期 {len(expired)} 条审批请求"

    def run_operations_journal_job(self) -> str:
        self._app.record_operations_journal()
        return "已记录运营日报条目"

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

    # ── Autonomous daily-cycle jobs ──────────────────────────────────────────

    def _run_pre_market_briefing(self, market: Market) -> str:
        result = self._app.daily_log.run_briefing(market=market)
        if result.skipped_reason:
            return f"{market.value} 盘前简报跳过：{result.skipped_reason}"
        return (
            f"{market.value} 盘前简报完成：{result.insight_count} 条隔夜洞察"
            + (f"，AI 简报已保存" if result.briefing_path else "")
        )

    def run_pre_market_briefing_job(self) -> str:
        return self._run_pre_market_briefing(Market.CN)

    def run_pre_market_briefing_us_job(self) -> str:
        return self._run_pre_market_briefing(Market.US)

    def run_pre_market_briefing_hk_job(self) -> str:
        return self._run_pre_market_briefing(Market.HK)

    def run_intraday_insight_scan_job(self) -> str:
        try:
            result = self._app.analysis_pipeline.run()
            return f"盘中扫描：产生 {len(result.produced)} 条新洞察，过期 {result.expired} 条"
        except Exception as exc:
            logger.exception("intraday insight scan failed")
            return f"盘中扫描失败：{exc}"

    def _run_post_market_reflection(self, market: Market) -> str:
        try:
            result = self._app.daily_log.run_review(as_of=date.today())
            parts = [f"{market.value} 盘后回顾完成（{result.as_of}）"]
            if result.deviations:
                parts.append(f"偏差：{'；'.join(result.deviations[:3])}")
            parts.append(f"未处理洞察：{result.unresolved_insight_count}")
            if result.ai_journal:
                parts.append("AI 日志已保存")
            return "；".join(parts)
        except Exception as exc:
            logger.exception("post-market reflection failed")
            return f"{market.value} 盘后回顾失败：{exc}"

    def run_post_market_reflection_job(self) -> str:
        return self._run_post_market_reflection(Market.CN)

    def run_post_market_reflection_us_job(self) -> str:
        return self._run_post_market_reflection(Market.US)

    def run_post_market_reflection_hk_job(self) -> str:
        return self._run_post_market_reflection(Market.HK)


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
    # ── Autonomous daily-cycle jobs ──────────────────────────────────────
    SchedulerRegistration(
        job_id="pre_market_briefing",
        name="A股盘前简报",
        description="运行市场感知快照、隔夜洞察引擎、AI 简报 (A股)",
        timezone="Asia/Shanghai",
        local_time=time(8, 0),
        market=Market.CN,
        handler_name="run_pre_market_briefing_job",
    ),
    SchedulerRegistration(
        job_id="pre_market_briefing_us",
        name="美股盘前简报",
        description="运行市场感知快照、隔夜洞察引擎、AI 简报 (美股)",
        timezone="America/New_York",
        local_time=time(8, 0),
        market=Market.US,
        handler_name="run_pre_market_briefing_us_job",
    ),
    SchedulerRegistration(
        job_id="pre_market_briefing_hk",
        name="港股盘前简报",
        description="运行市场感知快照、隔夜洞察引擎、AI 简报 (港股)",
        timezone="Asia/Hong_Kong",
        local_time=time(8, 0),
        market=Market.HK,
        handler_name="run_pre_market_briefing_hk_job",
    ),
    SchedulerRegistration(
        job_id="post_market_reflection",
        name="A股盘后回顾",
        description="计划与实际对比、AI 日志、未处理洞察收集 (A股)",
        timezone="Asia/Shanghai",
        local_time=time(18, 35),
        market=Market.CN,
        handler_name="run_post_market_reflection_job",
    ),
    SchedulerRegistration(
        job_id="post_market_reflection_us",
        name="美股盘后回顾",
        description="计划与实际对比、AI 日志、未处理洞察收集 (美股)",
        timezone="America/New_York",
        local_time=time(16, 30),
        market=Market.US,
        handler_name="run_post_market_reflection_us_job",
    ),
    SchedulerRegistration(
        job_id="post_market_reflection_hk",
        name="港股盘后回顾",
        description="计划与实际对比、AI 日志、未处理洞察收集 (港股)",
        timezone="Asia/Hong_Kong",
        local_time=time(16, 30),
        market=Market.HK,
        handler_name="run_post_market_reflection_hk_job",
    ),

]

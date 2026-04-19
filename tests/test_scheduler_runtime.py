from tradingcat.config import AppConfig, FutuConfig
from tradingcat.main import TradingCatApplication


EXPECTED_JOB_IDS = {
    "approval_expiry_sweep",
    "broker_auto_recovery",
    "daily_trading_plan_archive",
    "daily_trading_summary_archive",
    "intraday_risk_tick",
    "market_data_gap_repair",
    "market_data_history_sync",
    "operations_readiness_journal",
    "portfolio_risk_snapshot",
    "research_backtest_refresh",
    "research_selection_review",
    "sentiment_history_persist",
    "us_signal_generation",
}


def test_scheduler_runtime_registers_expected_jobs(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(
            data_dir=tmp_path,
            futu=FutuConfig(enabled=False),
        )
    )

    jobs = app.scheduler.list_jobs()

    assert len(jobs) == len(EXPECTED_JOB_IDS)
    assert {job.id for job in jobs} == EXPECTED_JOB_IDS

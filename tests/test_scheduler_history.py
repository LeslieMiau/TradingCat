from datetime import time

from tradingcat.config import AppConfig, FutuConfig
from tradingcat.domain.models import Market
from tradingcat.main import TradingCatApplication
from tradingcat.repositories.state import SchedulerRunRecordRepository
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.scheduler import SchedulerRunHistory, SchedulerService


def test_run_history_persists_success_and_failure(tmp_path):
    history = SchedulerRunHistory(SchedulerRunRecordRepository(tmp_path))
    scheduler = SchedulerService(
        MarketCalendarService(),
        backend="lightweight",
        run_history=history,
    )
    scheduler.register(
        job_id="ok_job",
        name="OK Job",
        description="",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        handler=lambda: "ran fine",
        market=Market.CN,
    )

    def broken() -> str:
        raise RuntimeError("boom")

    scheduler.register(
        job_id="bad_job",
        name="Bad Job",
        description="",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        handler=broken,
        market=Market.CN,
    )

    scheduler.run_job("ok_job")
    scheduler.run_job("bad_job")

    rows = scheduler.run_history()
    by_id = {row.job_id: row for row in rows}
    assert by_id["ok_job"].status == "success"
    assert by_id["ok_job"].trigger == "manual"
    assert by_id["ok_job"].detail == "ran fine"
    assert by_id["ok_job"].duration_ms >= 0
    assert by_id["bad_job"].status == "error"
    assert "RuntimeError" in (by_id["bad_job"].detail or "")


def test_run_history_survives_process_restart(tmp_path):
    history = SchedulerRunHistory(SchedulerRunRecordRepository(tmp_path))
    scheduler = SchedulerService(
        MarketCalendarService(), backend="lightweight", run_history=history
    )
    scheduler.register(
        job_id="persistent",
        name="Persist",
        description="",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        handler=lambda: "ok",
        market=Market.CN,
    )
    scheduler.run_job("persistent")

    reloaded_history = SchedulerRunHistory(SchedulerRunRecordRepository(tmp_path))
    rows = reloaded_history.list_recent()
    assert len(rows) == 1
    assert rows[0].job_id == "persistent"
    assert rows[0].status == "success"


def test_run_history_retention_caps_per_job(tmp_path):
    history = SchedulerRunHistory(
        SchedulerRunRecordRepository(tmp_path), max_records_per_job=10
    )
    scheduler = SchedulerService(
        MarketCalendarService(), backend="lightweight", run_history=history
    )
    scheduler.register(
        job_id="noisy",
        name="Noisy",
        description="",
        timezone="Asia/Shanghai",
        local_time=time(9, 0),
        handler=lambda: "tick",
        market=Market.CN,
    )
    for _ in range(25):
        scheduler.run_job("noisy")

    rows = scheduler.run_history(job_id="noisy", limit=100)
    assert len(rows) == 10  # capped at retention limit
    # most-recent first
    assert rows[0].executed_at >= rows[-1].executed_at


def test_run_history_filter_by_job_id(tmp_path):
    history = SchedulerRunHistory(SchedulerRunRecordRepository(tmp_path))
    scheduler = SchedulerService(
        MarketCalendarService(), backend="lightweight", run_history=history
    )
    for job_id in ("alpha", "beta"):
        scheduler.register(
            job_id=job_id,
            name=job_id,
            description="",
            timezone="Asia/Shanghai",
            local_time=time(9, 0),
            handler=lambda jid=job_id: jid,
            market=Market.CN,
        )
        scheduler.run_job(job_id)

    alpha_rows = scheduler.run_history(job_id="alpha")
    beta_rows = scheduler.run_history(job_id="beta")
    assert len(alpha_rows) == 1 and alpha_rows[0].job_id == "alpha"
    assert len(beta_rows) == 1 and beta_rows[0].job_id == "beta"


def test_application_scheduler_history_available(tmp_path):
    app = TradingCatApplication(
        config=AppConfig(data_dir=tmp_path, futu=FutuConfig(enabled=False))
    )
    app.scheduler.run_job("operations_readiness_journal")
    rows = app.scheduler.run_history(job_id="operations_readiness_journal")
    assert len(rows) == 1
    assert rows[0].trigger == "manual"

from datetime import UTC, datetime, time

from tradingcat.domain.models import Market
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.scheduler import SchedulerService


def test_market_session_reports_open_phase():
    service = MarketCalendarService()
    now = datetime(2026, 3, 9, 2, 0, tzinfo=UTC)

    session = service.get_session(Market.HK, now=now)

    assert session.is_trading_day is True
    assert session.phase == "open"


def test_scheduler_computes_next_run_and_executes_handler():
    service = MarketCalendarService()
    scheduler = SchedulerService(service)
    calls: list[str] = []

    scheduler.register(
        job_id="test_job",
        name="Test Job",
        description="Runs a simple handler",
        timezone="Asia/Shanghai",
        local_time=time(10, 0),
        market=Market.CN,
        handler=lambda: calls.append("ran") or "ok",
    )

    jobs = scheduler.list_jobs()
    assert len(jobs) == 1
    assert jobs[0].next_run_at is not None

    result = scheduler.run_job("test_job")
    assert result.status == "success"
    assert calls == ["ran"]


def test_apscheduler_backend_starts_and_stops_cleanly():
    service = MarketCalendarService()
    scheduler = SchedulerService(service, backend="apscheduler")

    scheduler.register(
        job_id="test_job",
        name="Test Job",
        description="Runs a simple handler",
        timezone="Asia/Shanghai",
        local_time=time(10, 0),
        market=Market.CN,
        handler=lambda: "ok",
    )

    scheduler.start()
    try:
        jobs = scheduler.list_jobs()
        assert scheduler.is_running is True
        assert scheduler.backend == "apscheduler"
        assert len(jobs) == 1
        assert jobs[0].next_run_at is not None
    finally:
        scheduler.stop()

    assert scheduler.is_running is False

from datetime import UTC, datetime, time

from tradingcat.domain.models import Market
from tradingcat.services.market_calendar import MarketCalendarService
from tradingcat.services.scheduler import SchedulerService
from tradingcat.services.trading_session import TradingPhase, TradingSessionService


def test_market_session_reports_open_phase():
    service = MarketCalendarService()
    now = datetime(2026, 3, 9, 2, 0, tzinfo=UTC)

    session = service.get_session(Market.HK, now=now)

    assert session.is_trading_day is True
    assert session.phase == "open"
    assert session.calendar_source


def test_market_calendar_uses_hk_and_us_holidays():
    service = MarketCalendarService()

    hk_labour_day = service.get_session(Market.HK, now=datetime(2026, 5, 1, 2, 0, tzinfo=UTC))
    us_thanksgiving = service.get_session(Market.US, now=datetime(2026, 11, 26, 15, 0, tzinfo=UTC))

    assert hk_labour_day.is_trading_day is False
    assert hk_labour_day.phase == "closed"
    assert hk_labour_day.session_type == "holiday"
    assert hk_labour_day.calendar_note == "Labour Day"
    assert "HKEX" in hk_labour_day.calendar_source
    assert us_thanksgiving.is_trading_day is False
    assert us_thanksgiving.session_type == "holiday"
    assert us_thanksgiving.calendar_note == "Thanksgiving Day"
    assert "NYSE" in us_thanksgiving.calendar_source


def test_market_calendar_uses_us_half_day_close():
    service = MarketCalendarService()

    early_session = service.get_session(Market.US, now=datetime(2026, 11, 27, 17, 0, tzinfo=UTC))
    closed_after_early_close = service.get_session(Market.US, now=datetime(2026, 11, 27, 19, 0, tzinfo=UTC))

    assert early_session.is_trading_day is True
    assert early_session.session_type == "half_day"
    assert early_session.close_time == time(13, 0)
    assert early_session.phase == "open"
    assert closed_after_early_close.phase == "closed"


def test_market_calendar_marks_cn_hk_lunch_break_non_open():
    service = MarketCalendarService()

    cn_lunch = service.get_session(Market.CN, now=datetime(2026, 3, 9, 4, 0, tzinfo=UTC))
    hk_lunch = service.get_session(Market.HK, now=datetime(2026, 3, 9, 4, 0, tzinfo=UTC))

    assert cn_lunch.phase == "break"
    assert hk_lunch.phase == "break"
    assert cn_lunch.breaks == [{"start": "11:30", "end": "13:00"}]
    assert TradingSessionService(service).get_phase(Market.CN, now=datetime(2026, 3, 9, 4, 0, tzinfo=UTC)).phase == TradingPhase.BREAK


def test_market_calendar_fails_closed_when_year_not_explicitly_loaded():
    service = MarketCalendarService()

    session = service.get_session(Market.US, now=datetime(2027, 1, 4, 15, 0, tzinfo=UTC))

    assert session.is_trading_day is False
    assert session.phase == "closed"
    assert session.session_type == "calendar_unavailable"
    assert "No explicit exchange calendar" in (session.calendar_note or "")


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


def test_scheduler_failure_listener_receives_job_exception():
    service = MarketCalendarService()
    captured: list[tuple[str, str, str]] = []

    def listener(job_id: str, job_name: str, exc: Exception) -> None:
        captured.append((job_id, job_name, f"{type(exc).__name__}: {exc}"))

    scheduler = SchedulerService(service, failure_listener=listener)

    def boom() -> str:
        raise RuntimeError("sync failed")

    scheduler.register(
        job_id="broken_job",
        name="Broken Job",
        description="Always fails",
        timezone="Asia/Shanghai",
        local_time=time(10, 0),
        market=Market.CN,
        handler=boom,
    )

    result = scheduler.run_job("broken_job")

    assert result.status == "error"
    assert "RuntimeError" in (result.detail or "")
    assert captured == [("broken_job", "Broken Job", "RuntimeError: sync failed")]


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

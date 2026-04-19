from __future__ import annotations

from datetime import UTC, datetime, time
from functools import partial
from threading import RLock
from typing import Callable

from tradingcat.domain.models import Market, SchedulerJob, SchedulerRunResult
from tradingcat.services.market_calendar import MarketCalendarService


class SchedulerBackendUnavailable(RuntimeError):
    pass


def _load_apscheduler():
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.date import DateTrigger
        from apscheduler.triggers.interval import IntervalTrigger
    except Exception as exc:  # pragma: no cover - import guard
        raise SchedulerBackendUnavailable("apscheduler is not installed") from exc
    return BackgroundScheduler, DateTrigger, IntervalTrigger


class SchedulerService:
    def __init__(
        self,
        calendar: MarketCalendarService,
        backend: str = "lightweight",
        failure_listener: Callable[[str, str, Exception], None] | None = None,
    ) -> None:
        self._calendar = calendar
        self._backend = backend
        self._handlers: dict[str, tuple[SchedulerJob, Callable[[], str]]] = {}
        self._lock = RLock()
        self._started = False
        self._apscheduler = None
        self._date_trigger = None
        self._interval_trigger = None
        self._failure_listener = failure_listener
        if backend == "apscheduler":
            BackgroundScheduler, DateTrigger, IntervalTrigger = _load_apscheduler()
            self._apscheduler = BackgroundScheduler(timezone="UTC")
            self._date_trigger = DateTrigger
            self._interval_trigger = IntervalTrigger

    def register(
        self,
        job_id: str,
        name: str,
        description: str,
        timezone: str,
        local_time: time,
        handler: Callable[[], str],
        market: Market | None = None,
    ) -> None:
        with self._lock:
            next_run_at = None
            if market is not None:
                next_run_at = self._calendar.next_run_utc(market, local_time)
            job = SchedulerJob(
                id=job_id,
                name=name,
                description=description,
                market=market,
                timezone=timezone,
                local_time=local_time,
                next_run_at=next_run_at,
            )
            self._handlers[job_id] = (job, handler)
            if self._started:
                self._schedule_registered_job(job_id)

    def register_interval(
        self,
        job_id: str,
        name: str,
        description: str,
        interval_seconds: int,
        handler: Callable[[], str],
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        with self._lock:
            job = SchedulerJob(
                id=job_id,
                name=name,
                description=description,
                market=None,
                timezone="UTC",
                interval_seconds=interval_seconds,
            )
            self._handlers[job_id] = (job, handler)
            if self._started:
                self._schedule_registered_job(job_id)

    @property
    def backend(self) -> str:
        return self._backend

    @property
    def is_running(self) -> bool:
        return self._started

    def start(self) -> None:
        with self._lock:
            if self._started:
                return
            if self._apscheduler is not None:
                self._apscheduler.start()
                for job_id in self._handlers:
                    self._schedule_registered_job(job_id)
            self._started = True

    def stop(self) -> None:
        with self._lock:
            if not self._started:
                return
            if self._apscheduler is not None:
                self._apscheduler.shutdown(wait=False)
                BackgroundScheduler, DateTrigger, IntervalTrigger = _load_apscheduler()
                self._apscheduler = BackgroundScheduler(timezone="UTC")
                self._date_trigger = DateTrigger
                self._interval_trigger = IntervalTrigger
            self._started = False

    def list_jobs(self) -> list[SchedulerJob]:
        with self._lock:
            return [self._sync_job_state(job) for job, _ in self._handlers.values()]

    def run_job(self, job_id: str) -> SchedulerRunResult:
        return self._execute_job(job_id)

    def _execute_job(self, job_id: str) -> SchedulerRunResult:
        with self._lock:
            job, handler = self._handlers[job_id]
            executed_at = datetime.now(UTC)
            if not job.enabled:
                return SchedulerRunResult(
                    job_id=job.id,
                    status="skipped",
                    executed_at=executed_at,
                    detail="Job is disabled",
                )
        try:
            detail = handler()
        except Exception as exc:
            with self._lock:
                job.last_run_at = executed_at
                if job.interval_seconds is None and job.market is not None:
                    job.next_run_at = self._calendar.next_run_utc(job.market, job.local_time, after=executed_at)
                if self._started and job.interval_seconds is None:
                    self._schedule_registered_job(job_id)
            if self._failure_listener is not None:
                try:
                    self._failure_listener(job.id, job.name, exc)
                except Exception:
                    pass
            return SchedulerRunResult(
                job_id=job.id,
                status="error",
                executed_at=executed_at,
                detail=f"{type(exc).__name__}: {exc}",
            )
        with self._lock:
            job.last_run_at = executed_at
            if job.interval_seconds is None and job.market is not None:
                job.next_run_at = self._calendar.next_run_utc(job.market, job.local_time, after=executed_at)
            if self._started and job.interval_seconds is None:
                self._schedule_registered_job(job_id)
            return SchedulerRunResult(job_id=job.id, status="success", executed_at=executed_at, detail=detail)

    def _schedule_registered_job(self, job_id: str) -> None:
        if self._apscheduler is None or self._date_trigger is None or self._interval_trigger is None:
            return
        job, _ = self._handlers[job_id]
        self._sync_job_state(job)
        if self._apscheduler.get_job(job.id) is not None:
            self._apscheduler.remove_job(job.id)
        if not job.enabled:
            return
        if job.interval_seconds is not None:
            self._apscheduler.add_job(
                partial(self._execute_job, job_id),
                trigger=self._interval_trigger(seconds=job.interval_seconds),
                id=job.id,
                replace_existing=True,
                coalesce=True,
                max_instances=1,
                misfire_grace_time=30,
            )
            return
        if job.next_run_at is None:
            return
        self._apscheduler.add_job(
            partial(self._execute_job, job_id),
            trigger=self._date_trigger(run_date=job.next_run_at),
            id=job.id,
            replace_existing=True,
            coalesce=True,
            misfire_grace_time=300,
        )

    def _sync_job_state(self, job: SchedulerJob) -> SchedulerJob:
        if self._apscheduler is None:
            return job
        scheduled_job = self._apscheduler.get_job(job.id)
        if scheduled_job is None:
            return job
        next_run = scheduled_job.next_run_time
        if next_run is not None:
            job.next_run_at = next_run.astimezone(UTC)
        return job

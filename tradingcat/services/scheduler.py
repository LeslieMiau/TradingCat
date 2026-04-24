from __future__ import annotations

from datetime import UTC, datetime, time
from functools import partial
from threading import RLock
from typing import Callable

from tradingcat.domain.models import Market, SchedulerJob, SchedulerRunRecord, SchedulerRunResult
from tradingcat.services.market_calendar import MarketCalendarService


class SchedulerBackendUnavailable(RuntimeError):
    pass


class _NoopRunHistory:
    """Null-object run history for tests or callers that opt out of persistence."""

    def record(self, record: SchedulerRunRecord) -> None:
        return None

    def list_recent(self, limit: int = 50, job_id: str | None = None) -> list[SchedulerRunRecord]:
        return []


class SchedulerRunHistory:
    """Persisted scheduler-run log with per-job retention.

    Keeps at most ``max_records_per_job`` most-recent rows per job so the
    store doesn't grow unbounded over a 16-week rollout. Older rows are
    evicted synchronously on insert — this trades a small O(records) scan
    for zero background work.
    """

    def __init__(self, repository, *, max_records_per_job: int = 200, lock: RLock | None = None) -> None:
        self._repository = repository
        self._records: dict[str, SchedulerRunRecord] = repository.load()
        self._max_per_job = max(10, int(max_records_per_job))
        self._lock = lock or RLock()

    def record(self, record: SchedulerRunRecord) -> None:
        with self._lock:
            self._records[record.id] = record
            self._evict_locked(record.job_id)
            self._repository.save(self._records)

    def list_recent(self, limit: int = 50, job_id: str | None = None) -> list[SchedulerRunRecord]:
        with self._lock:
            rows = list(self._records.values())
        if job_id is not None:
            rows = [row for row in rows if row.job_id == job_id]
        rows.sort(key=lambda row: row.executed_at, reverse=True)
        if limit > 0:
            rows = rows[:limit]
        return rows

    def _evict_locked(self, job_id: str) -> None:
        job_rows = [row for row in self._records.values() if row.job_id == job_id]
        if len(job_rows) <= self._max_per_job:
            return
        job_rows.sort(key=lambda row: row.executed_at, reverse=True)
        for row in job_rows[self._max_per_job :]:
            self._records.pop(row.id, None)


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
        run_history: "SchedulerRunHistory | None" = None,
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
        self._run_history = run_history or _NoopRunHistory()
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
        return self._execute_job(job_id, trigger="manual")

    def run_history(self, *, limit: int = 50, job_id: str | None = None) -> list[SchedulerRunRecord]:
        return self._run_history.list_recent(limit=limit, job_id=job_id)

    def _execute_job(self, job_id: str, *, trigger: str = "scheduled") -> SchedulerRunResult:
        with self._lock:
            job, handler = self._handlers[job_id]
            executed_at = datetime.now(UTC)
            job_name = job.name
            if not job.enabled:
                result = SchedulerRunResult(
                    job_id=job.id,
                    status="skipped",
                    executed_at=executed_at,
                    detail="Job is disabled",
                )
                self._persist_run(result, job_name=job_name, trigger=trigger, completed_at=executed_at)
                return result
        try:
            detail = handler()
        except Exception as exc:
            completed_at = datetime.now(UTC)
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
            result = SchedulerRunResult(
                job_id=job.id,
                status="error",
                executed_at=executed_at,
                detail=f"{type(exc).__name__}: {exc}",
            )
            self._persist_run(result, job_name=job_name, trigger=trigger, completed_at=completed_at)
            return result
        completed_at = datetime.now(UTC)
        with self._lock:
            job.last_run_at = executed_at
            if job.interval_seconds is None and job.market is not None:
                job.next_run_at = self._calendar.next_run_utc(job.market, job.local_time, after=executed_at)
            if self._started and job.interval_seconds is None:
                self._schedule_registered_job(job_id)
            result = SchedulerRunResult(job_id=job.id, status="success", executed_at=executed_at, detail=detail)
        self._persist_run(result, job_name=job_name, trigger=trigger, completed_at=completed_at)
        return result

    def _persist_run(
        self,
        result: SchedulerRunResult,
        *,
        job_name: str,
        trigger: str,
        completed_at: datetime,
    ) -> None:
        duration_ms = int(max(0.0, (completed_at - result.executed_at).total_seconds() * 1000))
        record = SchedulerRunRecord(
            job_id=result.job_id,
            job_name=job_name,
            status=result.status,
            trigger=trigger,
            executed_at=result.executed_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            detail=result.detail,
        )
        try:
            self._run_history.record(record)
        except Exception:
            pass

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
                partial(self._execute_job, job_id, trigger="scheduled"),
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
            partial(self._execute_job, job_id, trigger="scheduled"),
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

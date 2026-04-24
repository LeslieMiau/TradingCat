"""Stage C acceptance gate checks.

Includes both the pure-function gate computation (used by the live
``/ops/acceptance/gates`` endpoint) and the wall-clock evidence pipeline
(:class:`AcceptanceGateEvidenceService`) that persists one snapshot per
day so 6-week paper-trading acceptance has machine-readable evidence.

PLAN.md Stage C hard thresholds (wall-clock acceptance for paper-trading):
  * equity slippage <= 20 bps
  * order exception rate <= 1%
  * daily reconciliation diff == 0
  * kill switch activates within one scheduler tick (<= 60 s)

The functions here are pure: they consume the data that app.py already
gathers from reconciliation, audit, risk, and scheduler services and emit
a structured gate-status payload so the ops console and weekly report can
surface the same judgement.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Iterable


SLIPPAGE_BPS_THRESHOLD = 20.0
EXCEPTION_RATE_THRESHOLD = 0.01
KILL_SWITCH_LATENCY_SECONDS = 60.0
PORTFOLIO_CASH_TOLERANCE = 1.0  # Absolute units in base currency — broker rounding
SCHEDULER_DAILY_STALE_HOURS = 30.0  # 24h + 6h grace across DST / holiday calendars
SCHEDULER_INTERVAL_STALE_MULTIPLIER = 3  # Missed ticks allowed = 3× interval
TRADE_LEDGER_RECONCILIATION_STALE_HOURS = 30.0  # Daily EOD audit + 6h grace


def _gate(status: str, detail: str, metric: dict[str, object] | None = None) -> dict[str, object]:
    return {"status": status, "detail": detail, "metric": metric or {}}


def evaluate_slippage(
    execution_quality: dict[str, object] | None,
) -> dict[str, object]:
    quality = execution_quality or {}
    equity_samples = int(quality.get("equity_samples", 0) or 0)
    equity_breaches = int(quality.get("equity_breaches", 0) or 0)
    threshold = float(quality.get("equity_slippage_limit_bps", SLIPPAGE_BPS_THRESHOLD) or SLIPPAGE_BPS_THRESHOLD)
    metric = {
        "equity_samples": equity_samples,
        "equity_breaches": equity_breaches,
        "threshold_bps": threshold,
    }
    if equity_samples == 0:
        return _gate("pending", "No filled equity samples yet.", metric)
    if equity_breaches == 0:
        return _gate("pass", f"All {equity_samples} equity fills within {threshold:.0f} bps.", metric)
    return _gate(
        "fail",
        f"{equity_breaches}/{equity_samples} equity fills exceeded the {threshold:.0f} bps slippage budget.",
        metric,
    )


def evaluate_exception_rate(
    audit_metrics: dict[str, object] | None,
) -> dict[str, object]:
    metrics = audit_metrics or {}
    cycle_count = int(metrics.get("cycle_count", metrics.get("execution_cycle_count", 0)) or 0)
    exception_count = int(metrics.get("exception_count", 0) or 0)
    metric = {
        "cycle_count": cycle_count,
        "exception_count": exception_count,
        "threshold_ratio": EXCEPTION_RATE_THRESHOLD,
    }
    if cycle_count == 0:
        return _gate("pending", "No execution cycles observed in the window.", metric)
    rate = exception_count / cycle_count
    metric["observed_ratio"] = round(rate, 4)
    if rate <= EXCEPTION_RATE_THRESHOLD:
        return _gate(
            "pass",
            f"{exception_count}/{cycle_count} cycles errored ({rate:.2%}) within the {EXCEPTION_RATE_THRESHOLD:.0%} budget.",
            metric,
        )
    return _gate(
        "fail",
        f"{exception_count}/{cycle_count} cycles errored ({rate:.2%}) exceed the {EXCEPTION_RATE_THRESHOLD:.0%} budget.",
        metric,
    )


def evaluate_reconciliation(
    reconciliation: dict[str, object] | None,
) -> dict[str, object]:
    summary = reconciliation or {}
    duplicate_fills = int(summary.get("duplicate_fills", 0) or 0)
    unmatched = summary.get("unmatched_broker_orders", [])
    unmatched_count = len(unmatched) if hasattr(unmatched, "__len__") else int(unmatched or 0)
    metric = {
        "duplicate_fills": duplicate_fills,
        "unmatched_broker_orders": unmatched_count,
    }
    if duplicate_fills == 0 and unmatched_count == 0:
        return _gate("pass", "Broker reconciliation clean: no duplicates, no unmatched fills.", metric)
    return _gate(
        "fail",
        f"Reconciliation diffs: {duplicate_fills} duplicate fill(s), {unmatched_count} unmatched broker order(s).",
        metric,
    )


def evaluate_portfolio_reconciliation(
    portfolio_reconciliation: dict[str, object] | None,
) -> dict[str, object]:
    """Gate on broker-vs-local portfolio drift.

    Stage C requires daily reconciliation diff == 0. Cash is allowed a tiny
    absolute tolerance (``PORTFOLIO_CASH_TOLERANCE``) to absorb broker rounding;
    any missing or unexpected symbol is a hard fail because positions shouldn't
    silently drift between reconciliation runs.
    """
    summary = portfolio_reconciliation or {}
    cash_difference = float(summary.get("cash_difference", 0.0) or 0.0)
    missing = summary.get("missing_symbols", [])
    unexpected = summary.get("unexpected_symbols", [])
    missing_count = len(missing) if hasattr(missing, "__len__") else int(missing or 0)
    unexpected_count = len(unexpected) if hasattr(unexpected, "__len__") else int(unexpected or 0)
    metric = {
        "cash_difference": round(cash_difference, 4),
        "missing_symbols": missing_count,
        "unexpected_symbols": unexpected_count,
        "cash_tolerance": PORTFOLIO_CASH_TOLERANCE,
    }
    if not portfolio_reconciliation:
        return _gate(
            "pending",
            "No portfolio reconciliation snapshot available (broker disconnected?).",
            metric,
        )
    failures: list[str] = []
    if abs(cash_difference) > PORTFOLIO_CASH_TOLERANCE:
        failures.append(f"cash diff {cash_difference:.2f} (tolerance {PORTFOLIO_CASH_TOLERANCE:.2f})")
    if missing_count:
        failures.append(f"{missing_count} missing symbol(s)")
    if unexpected_count:
        failures.append(f"{unexpected_count} unexpected symbol(s)")
    if not failures:
        return _gate(
            "pass",
            f"Portfolio matches broker within tolerance (cash diff {cash_difference:.2f}).",
            metric,
        )
    return _gate("fail", "Portfolio drift: " + ", ".join(failures) + ".", metric)


def evaluate_trade_ledger_reconciliation(
    latest: dict[str, object] | None,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Gate on daily trade ledger completeness audit.

    Third layer of "对账零差异" evidence (after execution + portfolio
    reconciliation): catches the silent-failure class where a filled
    ExecutionReport never materialises into a TradeLedgerEntry.

    - ``critical`` -> fail (large amount drift or >3 incidents)
    - ``drift``    -> fail (any missing entry / missing fill / minor drift)
    - ``ok``       -> pass, but flipped to ``fail`` if the latest run is stale
      (>30h old) since a missed audit is itself a reconciliation gap.
    - No run on record yet -> pending (fresh install / pre-launch).
    """
    if not latest:
        return _gate(
            "pending",
            "No trade ledger reconciliation run recorded yet.",
            {"stale_hours": TRADE_LEDGER_RECONCILIATION_STALE_HOURS},
        )
    status = str(latest.get("status", "pending"))
    captured_at_raw = latest.get("captured_at") or latest.get("as_of")
    captured_at: datetime | None = None
    if isinstance(captured_at_raw, datetime):
        captured_at = captured_at_raw
    elif isinstance(captured_at_raw, str):
        try:
            captured_at = datetime.fromisoformat(captured_at_raw.replace("Z", "+00:00"))
        except ValueError:
            captured_at = None
        if captured_at is not None and captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
    metric = {
        "status": status,
        "as_of": str(latest.get("as_of", "")),
        "broker_fill_count": int(latest.get("broker_fill_count", 0) or 0),
        "ledger_entry_count": int(latest.get("ledger_entry_count", 0) or 0),
        "missing_ledger_count": int(latest.get("missing_ledger_count", 0) or 0),
        "missing_broker_count": int(latest.get("missing_broker_count", 0) or 0),
        "amount_drift_count": int(latest.get("amount_drift_count", 0) or 0),
        "max_amount_drift_pct": float(latest.get("max_amount_drift_pct", 0.0) or 0.0),
        "stale_hours": TRADE_LEDGER_RECONCILIATION_STALE_HOURS,
    }
    reference = now or datetime.now(UTC)
    if captured_at is not None:
        age_hours = (reference - captured_at).total_seconds() / 3600.0
        metric["age_hours"] = round(age_hours, 2)
        if age_hours > TRADE_LEDGER_RECONCILIATION_STALE_HOURS:
            return _gate(
                "fail",
                f"Trade ledger reconciliation is stale "
                f"({age_hours:.1f}h old, threshold {TRADE_LEDGER_RECONCILIATION_STALE_HOURS:.0f}h).",
                metric,
            )
    if status == "ok":
        return _gate(
            "pass",
            f"Trade ledger reconciliation clean: {metric['broker_fill_count']} fill(s) matched "
            f"{metric['ledger_entry_count']} ledger row(s).",
            metric,
        )
    if status == "drift":
        return _gate(
            "fail",
            f"Trade ledger drift: missing_ledger={metric['missing_ledger_count']} "
            f"missing_broker={metric['missing_broker_count']} amount_drift={metric['amount_drift_count']}.",
            metric,
        )
    if status == "critical":
        return _gate(
            "fail",
            f"Trade ledger critical: max drift {metric['max_amount_drift_pct'] * 100:.2f}% "
            f"across {metric['amount_drift_count']} fill(s); "
            f"missing_ledger={metric['missing_ledger_count']} missing_broker={metric['missing_broker_count']}.",
            metric,
        )
    return _gate("pending", f"Unknown trade ledger reconciliation status: {status}.", metric)


def evaluate_kill_switch_latency(
    events: Iterable[object],
) -> dict[str, object]:
    latencies: list[float] = []
    sampled = 0
    for event in events:
        if not getattr(event, "enabled", False):
            continue
        detected_at = getattr(event, "detected_at", None)
        changed_at = getattr(event, "changed_at", None)
        if not isinstance(detected_at, datetime) or not isinstance(changed_at, datetime):
            continue
        sampled += 1
        elapsed = (changed_at - detected_at).total_seconds()
        if elapsed < 0:
            elapsed = 0.0
        latencies.append(elapsed)
    metric = {
        "sampled_events": sampled,
        "threshold_seconds": KILL_SWITCH_LATENCY_SECONDS,
    }
    if not latencies:
        return _gate(
            "pending",
            "No kill-switch activations with detection timestamps recorded yet.",
            metric,
        )
    max_latency = max(latencies)
    avg_latency = sum(latencies) / len(latencies)
    metric.update(
        {
            "max_seconds": round(max_latency, 3),
            "avg_seconds": round(avg_latency, 3),
        }
    )
    if max_latency <= KILL_SWITCH_LATENCY_SECONDS:
        return _gate(
            "pass",
            f"All {len(latencies)} activations settled within {KILL_SWITCH_LATENCY_SECONDS:.0f}s (max {max_latency:.2f}s).",
            metric,
        )
    return _gate(
        "fail",
        f"{sum(1 for x in latencies if x > KILL_SWITCH_LATENCY_SECONDS)}/{len(latencies)} activations exceeded the {KILL_SWITCH_LATENCY_SECONDS:.0f}s latency budget.",
        metric,
    )


def evaluate_scheduler_health(
    jobs: Iterable[object] | None = None,
    runs: Iterable[object] | None = None,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    """Gate on scheduled-job liveness.

    For each enabled job, check whether a **successful** run happened recently:
      * Daily jobs (``interval_seconds is None``): must have a success within
        ``SCHEDULER_DAILY_STALE_HOURS`` hours — catches calendars where a job
        silently stopped firing after OpenD reconnection or timezone glitches.
      * Interval jobs: must have a success within
        ``SCHEDULER_INTERVAL_STALE_MULTIPLIER`` × interval_seconds.

    Jobs that haven't run at all yet within the required window count as stale.
    Failed last runs also count as stale (a previous success farther back does
    not rescue a current failure).
    """
    job_list = list(jobs or [])
    if not job_list:
        return _gate("pending", "No scheduler jobs registered.", {"enabled_jobs": 0})

    run_list = list(runs or [])
    latest_success_by_job: dict[str, datetime] = {}
    latest_any_by_job: dict[str, tuple[datetime, str]] = {}
    for run in run_list:
        job_id = getattr(run, "job_id", None)
        executed_at = getattr(run, "executed_at", None)
        status = getattr(run, "status", None)
        if not job_id or not isinstance(executed_at, datetime):
            continue
        if status == "success":
            existing = latest_success_by_job.get(job_id)
            if existing is None or executed_at > existing:
                latest_success_by_job[job_id] = executed_at
        existing_any = latest_any_by_job.get(job_id)
        if existing_any is None or executed_at > existing_any[0]:
            latest_any_by_job[job_id] = (executed_at, status or "unknown")

    reference = now or datetime.now(UTC)
    stale: list[dict[str, object]] = []
    enabled_count = 0
    for job in job_list:
        if not getattr(job, "enabled", True):
            continue
        enabled_count += 1
        job_id = getattr(job, "id", None)
        if job_id is None:
            continue
        interval_seconds = getattr(job, "interval_seconds", None)
        if interval_seconds:
            threshold = timedelta(seconds=int(interval_seconds) * SCHEDULER_INTERVAL_STALE_MULTIPLIER)
            job_kind = "interval"
        else:
            threshold = timedelta(hours=SCHEDULER_DAILY_STALE_HOURS)
            job_kind = "daily"
        last_success = latest_success_by_job.get(job_id)
        last_any = latest_any_by_job.get(job_id)
        if last_success is not None and reference - last_success <= threshold:
            continue
        # Stale — collect context for the caller.
        reason = "never_succeeded" if last_success is None else "stale_success"
        if last_any is not None and last_any[1] == "error":
            reason = "last_run_failed"
        stale.append(
            {
                "job_id": job_id,
                "job_kind": job_kind,
                "reason": reason,
                "last_success_at": last_success.isoformat() if last_success else None,
                "last_status": last_any[1] if last_any else None,
            }
        )

    metric = {
        "enabled_jobs": enabled_count,
        "stale_jobs": len(stale),
        "stale": stale[:10],
        "daily_stale_hours": SCHEDULER_DAILY_STALE_HOURS,
        "interval_stale_multiplier": SCHEDULER_INTERVAL_STALE_MULTIPLIER,
    }
    if not stale:
        return _gate(
            "pass",
            f"All {enabled_count} scheduled jobs have a recent successful run.",
            metric,
        )
    # We need at least *some* successful run on record to call this a real pass
    # or real fail — otherwise it's genuinely pending (fresh install).
    total_successes = len(latest_success_by_job)
    if total_successes == 0:
        return _gate(
            "pending",
            f"{len(stale)} job(s) have not run yet — awaiting first scheduler tick.",
            metric,
        )
    return _gate(
        "fail",
        f"{len(stale)} of {enabled_count} scheduled jobs are stale (see metric.stale).",
        metric,
    )


def combined_status(gates: dict[str, dict[str, object]]) -> str:
    statuses = {str(gate.get("status", "pending")) for gate in gates.values()}
    if "fail" in statuses:
        return "fail"
    if statuses == {"pass"}:
        return "pass"
    return "pending"


def compute_acceptance_gates(
    *,
    execution_quality: dict[str, object] | None = None,
    audit_metrics: dict[str, object] | None = None,
    reconciliation: dict[str, object] | None = None,
    portfolio_reconciliation: dict[str, object] | None = None,
    kill_switch_events: Iterable[object] = (),
    scheduler_jobs: Iterable[object] | None = None,
    scheduler_runs: Iterable[object] | None = None,
    trade_ledger_reconciliation: dict[str, object] | None = None,
) -> dict[str, object]:
    gates = {
        "slippage": evaluate_slippage(execution_quality),
        "exception_rate": evaluate_exception_rate(audit_metrics),
        "reconciliation": evaluate_reconciliation(reconciliation),
        "portfolio_reconciliation": evaluate_portfolio_reconciliation(portfolio_reconciliation),
        "trade_ledger_reconciliation": evaluate_trade_ledger_reconciliation(trade_ledger_reconciliation),
        "kill_switch_latency": evaluate_kill_switch_latency(kill_switch_events),
        "scheduler_health": evaluate_scheduler_health(scheduler_jobs, scheduler_runs),
    }
    return {
        "status": combined_status(gates),
        "gates": gates,
        "thresholds": {
            "slippage_bps": SLIPPAGE_BPS_THRESHOLD,
            "exception_rate": EXCEPTION_RATE_THRESHOLD,
            "kill_switch_latency_seconds": KILL_SWITCH_LATENCY_SECONDS,
            "reconciliation_diff": 0,
            "portfolio_cash_tolerance": PORTFOLIO_CASH_TOLERANCE,
            "scheduler_daily_stale_hours": SCHEDULER_DAILY_STALE_HOURS,
            "trade_ledger_reconciliation_stale_hours": TRADE_LEDGER_RECONCILIATION_STALE_HOURS,
        },
    }


class AcceptanceGateEvidenceService:
    """Daily Stage-C wall-clock evidence capture + timeline rollup.

    The capture is idempotent per ISO date — calling :meth:`capture` more
    than once on the same day overwrites the row, which is the desired
    behaviour for both manual ad-hoc captures and the EOD scheduler tick.
    """

    REQUIRED_PASS_DAYS_HK_US = 30  # 6 weeks of trading days (5/week * 6)
    REQUIRED_PASS_DAYS_CN = 20  # 4 weeks for the A-share advisory window

    # Stage-D promotion gates — minimum **current** clean-day streak required
    # before each rollout stage. The numbers correspond to PLAN.md:
    #   * to 10%: Stage C (6 weeks paper trading) completed cleanly
    #   * to 30%: + 4 weeks at 10% with no breach
    #   * to 100%: + 4 weeks at 30% with no breach
    STAGE_PASS_STREAK_REQUIREMENTS = {
        "10%": 30,
        "30%": 50,
        "100%": 70,
    }

    def __init__(self, repository) -> None:
        self._repository = repository
        self._snapshots = repository.load()

    def capture(
        self,
        gates_payload: dict[str, object],
        *,
        as_of: date | None = None,
        notes: list[str] | None = None,
    ):
        from uuid import uuid4

        from tradingcat.domain.models import AcceptanceGateSnapshot

        target = as_of or date.today()
        existing = self._find(target)
        snapshot = AcceptanceGateSnapshot(
            id=existing.id if existing else str(uuid4()),
            as_of=target,
            status=str(gates_payload.get("status", "pending")),
            gates=dict(gates_payload.get("gates", {}) or {}),
            thresholds=dict(gates_payload.get("thresholds", {}) or {}),
            notes=list(notes or []),
        )
        self._snapshots[snapshot.as_of.isoformat()] = snapshot
        self._repository.save(self._snapshots)
        return snapshot

    def list_snapshots(self):
        return sorted(self._snapshots.values(), key=lambda item: item.as_of)

    def timeline(self, *, window_days: int = 42):
        snapshots = {snap.as_of: snap for snap in self.list_snapshots()}
        today = date.today()
        points: list[dict[str, object]] = []
        pass_streak = 0
        max_pass_streak = 0
        for offset in range(window_days):
            day = today - timedelta(days=window_days - 1 - offset)
            snap = snapshots.get(day)
            status = snap.status if snap else "missing"
            if status == "pass":
                pass_streak += 1
                max_pass_streak = max(max_pass_streak, pass_streak)
            else:
                pass_streak = 0
            points.append(
                {
                    "date": day.isoformat(),
                    "status": status,
                    "gate_status": {
                        name: str((gate or {}).get("status", "pending"))
                        for name, gate in (snap.gates if snap else {}).items()
                    },
                }
            )
        passes = sum(1 for point in points if point["status"] == "pass")
        fails = sum(1 for point in points if point["status"] == "fail")
        pendings = sum(1 for point in points if point["status"] == "pending")
        missing = sum(1 for point in points if point["status"] == "missing")
        return {
            "window_days": window_days,
            "points": points,
            "summary": {
                "pass_days": passes,
                "fail_days": fails,
                "pending_days": pendings,
                "missing_days": missing,
                "current_pass_streak": pass_streak,
                "max_pass_streak": max_pass_streak,
                "required_pass_days_hk_us": self.REQUIRED_PASS_DAYS_HK_US,
                "required_pass_days_cn": self.REQUIRED_PASS_DAYS_CN,
                "hk_us_paper_complete": passes >= self.REQUIRED_PASS_DAYS_HK_US,
                "cn_advisory_complete": passes >= self.REQUIRED_PASS_DAYS_CN,
            },
        }

    def gate_readiness(self, target_stage: str, *, window_days: int = 90) -> dict[str, object]:
        """Decide whether Stage-C evidence supports promoting to ``target_stage``.

        Returns a structured payload with ``eligible`` and ``blockers`` so it
        can be folded into the rollout summary as a hard gate alongside the
        existing journal-based readiness check.
        """

        required = self.STAGE_PASS_STREAK_REQUIREMENTS.get(target_stage)
        if required is None:
            return {
                "target_stage": target_stage,
                "required_pass_streak": None,
                "current_pass_streak": 0,
                "max_pass_streak": 0,
                "eligible": True,
                "blockers": [],
            }
        timeline = self.timeline(window_days=window_days)
        summary = timeline["summary"]
        current = int(summary["current_pass_streak"])
        peak = int(summary["max_pass_streak"])
        fail_days = int(summary["fail_days"])
        missing_days = int(summary["missing_days"])
        blockers: list[str] = []
        if current < required:
            blockers.append(
                f"Stage-C evidence: need {required} consecutive clean gate days for {target_stage}, "
                f"currently at {current} (max ever: {peak})."
            )
        if fail_days > 0 and current < required:
            blockers.append(
                f"Stage-C evidence: {fail_days} fail day(s) in the last {window_days} days — "
                "investigate root cause before retry."
            )
        eligible = not blockers
        return {
            "target_stage": target_stage,
            "required_pass_streak": required,
            "current_pass_streak": current,
            "max_pass_streak": peak,
            "fail_days": fail_days,
            "missing_days": missing_days,
            "eligible": eligible,
            "blockers": blockers,
        }

    def _find(self, target: date):
        return self._snapshots.get(target.isoformat())


__all__ = [
    "SLIPPAGE_BPS_THRESHOLD",
    "EXCEPTION_RATE_THRESHOLD",
    "KILL_SWITCH_LATENCY_SECONDS",
    "PORTFOLIO_CASH_TOLERANCE",
    "SCHEDULER_DAILY_STALE_HOURS",
    "SCHEDULER_INTERVAL_STALE_MULTIPLIER",
    "TRADE_LEDGER_RECONCILIATION_STALE_HOURS",
    "evaluate_slippage",
    "evaluate_exception_rate",
    "evaluate_reconciliation",
    "evaluate_portfolio_reconciliation",
    "evaluate_trade_ledger_reconciliation",
    "evaluate_kill_switch_latency",
    "evaluate_scheduler_health",
    "combined_status",
    "compute_acceptance_gates",
    "AcceptanceGateEvidenceService",
]

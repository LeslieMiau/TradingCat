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

from datetime import date, datetime, timedelta
from typing import Iterable


SLIPPAGE_BPS_THRESHOLD = 20.0
EXCEPTION_RATE_THRESHOLD = 0.01
KILL_SWITCH_LATENCY_SECONDS = 60.0
PORTFOLIO_CASH_TOLERANCE = 1.0  # Absolute units in base currency — broker rounding


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
) -> dict[str, object]:
    gates = {
        "slippage": evaluate_slippage(execution_quality),
        "exception_rate": evaluate_exception_rate(audit_metrics),
        "reconciliation": evaluate_reconciliation(reconciliation),
        "portfolio_reconciliation": evaluate_portfolio_reconciliation(portfolio_reconciliation),
        "kill_switch_latency": evaluate_kill_switch_latency(kill_switch_events),
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
    "evaluate_slippage",
    "evaluate_exception_rate",
    "evaluate_reconciliation",
    "evaluate_portfolio_reconciliation",
    "evaluate_kill_switch_latency",
    "combined_status",
    "compute_acceptance_gates",
    "AcceptanceGateEvidenceService",
]

"""Stage C acceptance gate checks.

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

from datetime import datetime, timedelta
from typing import Iterable


SLIPPAGE_BPS_THRESHOLD = 20.0
EXCEPTION_RATE_THRESHOLD = 0.01
KILL_SWITCH_LATENCY_SECONDS = 60.0


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
    kill_switch_events: Iterable[object] = (),
) -> dict[str, object]:
    gates = {
        "slippage": evaluate_slippage(execution_quality),
        "exception_rate": evaluate_exception_rate(audit_metrics),
        "reconciliation": evaluate_reconciliation(reconciliation),
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
        },
    }


__all__ = [
    "SLIPPAGE_BPS_THRESHOLD",
    "EXCEPTION_RATE_THRESHOLD",
    "KILL_SWITCH_LATENCY_SECONDS",
    "evaluate_slippage",
    "evaluate_exception_rate",
    "evaluate_reconciliation",
    "evaluate_kill_switch_latency",
    "combined_status",
    "compute_acceptance_gates",
]

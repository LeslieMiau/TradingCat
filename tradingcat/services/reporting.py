from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tradingcat.domain.models import AlertEvent, AuditLogEntry, OperationsJournalEntry, RecoveryAttempt


def reports_root(data_dir: Path) -> Path:
    return data_dir / "reports"


def latest_report_dir(data_dir: Path) -> Path | None:
    base_dir = reports_root(data_dir)
    if not base_dir.exists():
        return None
    candidates = sorted(path for path in base_dir.iterdir() if path.is_dir())
    return candidates[-1] if candidates else None


def resolve_report_dir(data_dir: Path, report_ref: str) -> Path | None:
    candidate = Path(report_ref)
    if candidate.is_dir():
        return candidate
    scoped = reports_root(data_dir) / report_ref
    if scoped.is_dir():
        return scoped
    return None


def load_report_summary(report_dir: Path) -> dict[str, object]:
    diagnostics_file = report_dir / "01_diagnostics_summary.json"
    doctor_file = report_dir / "doctor.json"
    if diagnostics_file.exists():
        payload = json.loads(diagnostics_file.read_text(encoding="utf-8"))
        summary = payload["summary"]
    elif doctor_file.exists():
        summary = json.loads(doctor_file.read_text(encoding="utf-8"))
    else:
        raise FileNotFoundError(f"No summary JSON found in {report_dir}")

    result: dict[str, object] = {
        "report_dir": str(report_dir),
        "summary": summary,
    }

    optional_files = {
        "operations_readiness": "*_operations_readiness.json",
        "ops_execution_metrics": "*_ops_execution_metrics.json",
        "ops_rollout": "*_ops_rollout.json",
        "ops_go_live": "*_ops_go_live.json",
        "ops_live_acceptance": "*_ops_live_acceptance.json",
        "ops_rollout_checklist": "*_ops_rollout_checklist.json",
        "ops_rollout_milestones": "*_ops_rollout_milestones.json",
        "rollout_policy": "*_rollout_policy.json",
        "data_quality": "*_data_quality.json",
        "history_sync": "*_history_sync.json",
        "selection_summary": "*_selection_summary.json",
        "allocation_summary": "*_allocation_summary.json",
        "alerts_summary": "*_alerts_summary.json",
        "compliance_summary": "*_compliance_summary.json",
        "broker_order_check": "*_broker_order_check.json",
        "execution_gate": "*_execution_gate.json",
        "cancel_open_orders": "*_cancel_open_orders.json",
        "execution_run": "*_execution_run.json",
        "execution_quality": "*_execution_quality.json",
        "execution_authorization": "*_execution_authorization.json",
        "recovery_summary": "*_recovery_summary.json",
        "manual_reconcile": "*_manual_reconcile.json",
    }
    for key, pattern in optional_files.items():
        matches = sorted(report_dir.glob(pattern))
        if matches:
            result[key] = json.loads(matches[-1].read_text(encoding="utf-8"))
    return result


def summarize_report_for_dashboard(payload: dict[str, object]) -> dict[str, object]:
    summary = payload["summary"]
    broker_order_check = payload.get("broker_order_check", {})
    execution_gate = payload.get("execution_gate", {})
    cancel_open_orders = payload.get("cancel_open_orders", {})
    execution_run = payload.get("execution_run", {})
    execution_quality = payload.get("execution_quality", {})
    execution_authorization = payload.get("execution_authorization", {})
    recovery_summary = payload.get("recovery_summary", {})
    manual_reconcile = payload.get("manual_reconcile", {})
    operations_readiness = payload.get("operations_readiness", {})
    ops_execution_metrics = payload.get("ops_execution_metrics", {})
    ops_rollout = payload.get("ops_rollout", {})
    ops_go_live = payload.get("ops_go_live", {})
    ops_live_acceptance = payload.get("ops_live_acceptance", {})
    ops_rollout_checklist = payload.get("ops_rollout_checklist", {})
    ops_rollout_milestones = payload.get("ops_rollout_milestones", {})
    rollout_policy = payload.get("rollout_policy", {})
    data_quality = payload.get("data_quality", {})
    history_sync = payload.get("history_sync", {})
    selection_summary = payload.get("selection_summary", {})
    allocation_summary = payload.get("allocation_summary", {})
    alerts_summary = payload.get("alerts_summary", {})
    compliance_summary = payload.get("compliance_summary", {})

    submission = broker_order_check.get("submission", {}) if isinstance(broker_order_check, dict) else {}
    cancellation = broker_order_check.get("cancellation", {}) if isinstance(broker_order_check, dict) else {}

    return {
        "report_dir": payload["report_dir"],
        "ready": summary.get("ready"),
        "category": summary.get("category"),
        "severity": summary.get("severity"),
        "findings": summary.get("findings", []),
        "cards": {
            "operations": {
                "ready": operations_readiness.get("ready") if isinstance(operations_readiness, dict) else None,
                "alert_count": alerts_summary.get("count") if isinstance(alerts_summary, dict) else None,
                "checklist_count": len(compliance_summary.get("checklists", [])) if isinstance(compliance_summary, dict) else 0,
                "recovery_attempts": recovery_summary.get("count") if isinstance(recovery_summary, dict) else None,
                "data_ready": data_quality.get("ready") if isinstance(data_quality, dict) else None,
                "data_incomplete_count": data_quality.get("incomplete_count") if isinstance(data_quality, dict) else None,
                "history_sync_healthy": history_sync.get("healthy") if isinstance(history_sync, dict) else None,
                "history_sync_stale": history_sync.get("stale") if isinstance(history_sync, dict) else None,
                "active_strategy_count": len(selection_summary.get("active", [])) if isinstance(selection_summary, dict) else 0,
                "paper_only_strategy_count": len(selection_summary.get("paper_only", [])) if isinstance(selection_summary, dict) else 0,
                "allocated_strategy_count": len(allocation_summary.get("active", [])) if isinstance(allocation_summary, dict) else 0,
                "allocated_target_weight": allocation_summary.get("total_target_weight") if isinstance(allocation_summary, dict) else None,
                "exception_rate": ops_execution_metrics.get("exception_rate") if isinstance(ops_execution_metrics, dict) else None,
                "risk_hit_rate": ops_execution_metrics.get("risk_hit_rate") if isinstance(ops_execution_metrics, dict) else None,
                "gate_ready": execution_gate.get("ready") if isinstance(execution_gate, dict) else None,
                "gate_blocked": execution_gate.get("should_block") if isinstance(execution_gate, dict) else None,
                "live_ready": ops_live_acceptance.get("ready_for_live") if isinstance(ops_live_acceptance, dict) else None,
            },
            "rollout": {
                "ready_for_rollout": ops_rollout.get("ready_for_rollout") if isinstance(ops_rollout, dict) else None,
                "current_recommendation": ops_rollout.get("current_recommendation") if isinstance(ops_rollout, dict) else None,
                "next_stage": ops_rollout.get("next_stage") if isinstance(ops_rollout, dict) else None,
                "blocker_count": len(ops_rollout.get("blockers", [])) if isinstance(ops_rollout, dict) else 0,
                "promotion_allowed": ops_go_live.get("promotion_allowed") if isinstance(ops_go_live, dict) else None,
                "ready_for_live": ops_live_acceptance.get("ready_for_live") if isinstance(ops_live_acceptance, dict) else None,
                "checklist_ready": ops_rollout_checklist.get("ready") if isinstance(ops_rollout_checklist, dict) else None,
                "next_pending_stage": ops_rollout_milestones.get("next_pending_stage") if isinstance(ops_rollout_milestones, dict) else None,
                "active_stage": rollout_policy.get("stage") if isinstance(rollout_policy, dict) else None,
                "allocation_ratio": rollout_policy.get("allocation_ratio") if isinstance(rollout_policy, dict) else None,
                "policy_matches_recommendation": rollout_policy.get("policy_matches_recommendation") if isinstance(rollout_policy, dict) else None,
            },
            "broker_order_check": {
                "symbol": broker_order_check.get("instrument", {}).get("symbol") if isinstance(broker_order_check, dict) else None,
                "submission_status": submission.get("status"),
                "cancellation_status": cancellation.get("status"),
                "broker_order_id": submission.get("broker_order_id"),
            },
            "cancel_open_orders": {
                "cancelled_count": cancel_open_orders.get("cancelled_count") if isinstance(cancel_open_orders, dict) else None,
                "failed_count": cancel_open_orders.get("failed_count") if isinstance(cancel_open_orders, dict) else None,
            },
            "execution_run": {
                "submitted_count": len(execution_run.get("submitted_orders", [])) if isinstance(execution_run, dict) else 0,
                "failed_count": len(execution_run.get("failed_orders", [])) if isinstance(execution_run, dict) else 0,
                "approval_count": execution_run.get("approval_count") if isinstance(execution_run, dict) else None,
            },
            "execution_gate": {
                "ready": execution_gate.get("ready") if isinstance(execution_gate, dict) else None,
                "should_block": execution_gate.get("should_block") if isinstance(execution_gate, dict) else None,
                "policy_stage": execution_gate.get("policy_stage") if isinstance(execution_gate, dict) else None,
                "recommended_stage": execution_gate.get("recommended_stage") if isinstance(execution_gate, dict) else None,
                "reason_count": len(execution_gate.get("reasons", [])) if isinstance(execution_gate, dict) else 0,
            },
            "execution_quality": {
                "filled_samples": execution_quality.get("filled_samples") if isinstance(execution_quality, dict) else None,
                "within_limits": execution_quality.get("within_limits") if isinstance(execution_quality, dict) else None,
                "equity_breaches": execution_quality.get("equity_breaches") if isinstance(execution_quality, dict) else None,
                "option_breaches": execution_quality.get("option_breaches") if isinstance(execution_quality, dict) else None,
            },
            "execution_authorization": {
                "order_count": execution_authorization.get("order_count") if isinstance(execution_authorization, dict) else None,
                "unauthorized_count": execution_authorization.get("unauthorized_count") if isinstance(execution_authorization, dict) else None,
                "all_authorized": execution_authorization.get("all_authorized") if isinstance(execution_authorization, dict) else None,
            },
            "live_acceptance": {
                "ready_for_live": ops_live_acceptance.get("ready_for_live") if isinstance(ops_live_acceptance, dict) else None,
                "incident_count": ops_live_acceptance.get("incident_count") if isinstance(ops_live_acceptance, dict) else None,
                "blocker_count": len(ops_live_acceptance.get("blockers", [])) if isinstance(ops_live_acceptance, dict) else 0,
            },
            "rollout_checklist": {
                "stage": ops_rollout_checklist.get("stage") if isinstance(ops_rollout_checklist, dict) else None,
                "ready": ops_rollout_checklist.get("ready") if isinstance(ops_rollout_checklist, dict) else None,
                "blocker_count": len(ops_rollout_checklist.get("blockers", [])) if isinstance(ops_rollout_checklist, dict) else 0,
            },
            "manual_reconcile": {
                "status": manual_reconcile.get("status") if isinstance(manual_reconcile, dict) else None,
                "approval_status": (
                    manual_reconcile.get("approval", {}).get("approval", {}).get("status")
                    if isinstance(manual_reconcile, dict)
                    else None
                ),
                "reconcile_status": (
                    manual_reconcile.get("reconciliation", {}).get("status")
                    if isinstance(manual_reconcile, dict)
                    else None
                ),
            },
        },
    }


def build_operations_period_report(
    *,
    label: str,
    window_days: int,
    readiness: dict[str, object],
    acceptance: dict[str, object],
    rollout: dict[str, object],
    execution_metrics: dict[str, object],
    audit_events: list[AuditLogEntry],
    alerts: list[AlertEvent],
    recoveries: list[RecoveryAttempt],
    journal_entries: list[OperationsJournalEntry],
) -> dict[str, object]:
    execution_errors = [event for event in audit_events if event.category == "execution" and event.status == "error"]
    risk_violations = [event for event in audit_events if event.category == "risk" and event.action == "violation"]
    approval_expiries = [event for event in audit_events if event.category == "approval" and event.action in {"expire", "expire_stale"}]
    kill_switch_events = [event for event in audit_events if event.category == "risk" and event.action == "kill_switch_set"]

    highlights: list[str] = []
    if readiness.get("ready", False):
        highlights.append("Operations readiness stayed green for the current window.")
    else:
        highlights.append(f"Operations readiness is not green: {readiness.get('diagnostics', {}).get('category', 'unknown')}.")
    if alerts:
        highlights.append(f"{len(alerts)} alerts were recorded in the current window.")
    if execution_errors:
        highlights.append(f"{len(execution_errors)} execution-cycle errors need review.")
    if risk_violations:
        highlights.append(f"{len(risk_violations)} risk violations were triggered.")
    if recoveries:
        highlights.append(f"{len(recoveries)} recovery attempts were recorded.")

    blocker_actions = []
    for blocker in rollout.get("blockers", []):
        if isinstance(blocker, dict):
            blocker_actions.extend(str(action) for action in blocker.get("actions", []))
    next_actions = _dedupe_strings(
        blocker_actions
        + [alert.recovery_action for alert in alerts[:5]]
        + [f"Review failed recovery attempt: {attempt.detail}" for attempt in recoveries if attempt.status == "failed"]
    )

    return {
        "label": label,
        "window_days": window_days,
        "generated_at": datetime.now(UTC).isoformat(),
        "readiness": readiness,
        "acceptance": acceptance,
        "rollout": rollout,
        "counts": {
            "audit_events": len(audit_events),
            "alerts": len(alerts),
            "recoveries": len(recoveries),
            "journal_entries": len(journal_entries),
            "execution_errors": len(execution_errors),
            "risk_violations": len(risk_violations),
            "approval_expiries": len(approval_expiries),
            "kill_switch_changes": len(kill_switch_events),
            "unauthorized_count": execution_metrics.get("unauthorized_count", 0),
        },
        "metrics": {
            "exception_rate": execution_metrics.get("exception_rate"),
            "risk_hit_rate": execution_metrics.get("risk_hit_rate"),
            "filled_samples": execution_metrics.get("filled_samples"),
            "slippage_within_limits": execution_metrics.get("slippage_within_limits"),
            "authorization_ok": execution_metrics.get("authorization_ok"),
        },
        "highlights": highlights,
        "alerts": [_alert_summary(alert) for alert in alerts[:10]],
        "exceptions": [_audit_summary(event) for event in execution_errors[:10]],
        "recoveries": [_recovery_summary(attempt) for attempt in recoveries[:10]],
        "next_actions": next_actions,
    }


def build_postmortem_report(
    *,
    window_days: int,
    readiness: dict[str, object],
    execution_metrics: dict[str, object],
    audit_events: list[AuditLogEntry],
    alerts: list[AlertEvent],
    recoveries: list[RecoveryAttempt],
) -> dict[str, object]:
    incidents: list[dict[str, object]] = []
    incidents.extend(
        {
            "source": "alert",
            "timestamp": alert.created_at.isoformat(),
            "category": alert.category,
            "severity": alert.severity,
            "summary": alert.message,
            "details": alert.details,
        }
        for alert in alerts
    )
    incidents.extend(
        {
            "source": "audit",
            "timestamp": event.created_at.isoformat(),
            "category": f"{event.category}:{event.action}",
            "severity": event.status,
            "summary": str(event.details.get("detail", event.action)),
            "details": event.details,
        }
        for event in audit_events
        if event.status in {"warning", "error"}
    )
    incidents.extend(
        {
            "source": "recovery",
            "timestamp": attempt.attempted_at.isoformat(),
            "category": "broker_recovery",
            "severity": "error" if attempt.status == "failed" else "warning",
            "summary": attempt.detail or attempt.status,
            "details": {
                "status": attempt.status,
                "trigger": attempt.trigger,
                "before_backend": attempt.before_backend,
                "after_backend": attempt.after_backend,
            },
        }
        for attempt in recoveries
    )
    incidents.sort(key=lambda item: item["timestamp"], reverse=True)

    latest = incidents[0] if incidents else None
    root_cause_hints: list[str] = []
    if latest is not None:
        if "trade" in str(latest["category"]) or "broker" in str(latest["category"]):
            root_cause_hints.append("Check OpenD connectivity, trade unlock state, and account environment.")
        if "market_data" in str(latest["category"]) or "quote" in str(latest["category"]):
            root_cause_hints.append("Check quote permissions, symbol coverage, and field mappings.")
        if "risk" in str(latest["category"]):
            root_cause_hints.append("Review risk thresholds, recent drawdown state, and option budget usage.")
    if not root_cause_hints and not readiness.get("ready", False):
        root_cause_hints.append("Resolve readiness blockers before the next execution cycle.")

    recommended_actions = _dedupe_strings(
        [alert.recovery_action for alert in alerts[:5]]
        + [f"Inspect audit event {event.action} in category {event.category}." for event in audit_events if event.status in {"warning", "error"}][:5]
        + root_cause_hints
    )

    return {
        "label": "postmortem",
        "window_days": window_days,
        "generated_at": datetime.now(UTC).isoformat(),
        "ready": readiness.get("ready", False),
        "latest_incident": latest,
        "incident_count": len(incidents),
        "execution_metrics": {
            "exception_rate": execution_metrics.get("exception_rate"),
            "risk_hit_rate": execution_metrics.get("risk_hit_rate"),
            "authorization_ok": execution_metrics.get("authorization_ok"),
            "slippage_within_limits": execution_metrics.get("slippage_within_limits"),
        },
        "root_cause_hints": root_cause_hints,
        "recommended_actions": recommended_actions,
        "incidents": incidents[:10],
    }


def build_incident_replay(
    *,
    window_days: int,
    audit_events: list[AuditLogEntry],
    alerts: list[AlertEvent],
    recoveries: list[RecoveryAttempt],
) -> dict[str, object]:
    events: list[dict[str, object]] = []
    events.extend(
        {
            "timestamp": alert.created_at.isoformat(),
            "source": "alert",
            "category": alert.category,
            "severity": alert.severity,
            "summary": alert.message,
        }
        for alert in alerts
    )
    events.extend(
        {
            "timestamp": event.created_at.isoformat(),
            "source": "audit",
            "category": f"{event.category}:{event.action}",
            "severity": event.status,
            "summary": str(event.details.get("detail", event.action)),
        }
        for event in audit_events
    )
    events.extend(
        {
            "timestamp": attempt.attempted_at.isoformat(),
            "source": "recovery",
            "category": "broker_recovery",
            "severity": "error" if attempt.status == "failed" else "warning",
            "summary": attempt.detail or attempt.status,
        }
        for attempt in recoveries
    )
    events.sort(key=lambda item: item["timestamp"])
    return {
        "label": "incident_replay",
        "window_days": window_days,
        "event_count": len(events),
        "events": events,
    }


def filter_recent_items(items: list[object], *, timestamp_attr: str, window_days: int) -> list[object]:
    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    result = []
    for item in items:
        timestamp = getattr(item, timestamp_attr, None)
        if isinstance(timestamp, datetime) and timestamp >= cutoff:
            result.append(item)
    return result


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _alert_summary(alert: AlertEvent) -> dict[str, object]:
    return {
        "created_at": alert.created_at.isoformat(),
        "severity": alert.severity,
        "category": alert.category,
        "message": alert.message,
        "recovery_action": alert.recovery_action,
    }


def _audit_summary(event: AuditLogEntry) -> dict[str, object]:
    return {
        "created_at": event.created_at.isoformat(),
        "category": event.category,
        "action": event.action,
        "status": event.status,
        "details": event.details,
    }


def _recovery_summary(attempt: RecoveryAttempt) -> dict[str, object]:
    return {
        "attempted_at": attempt.attempted_at.isoformat(),
        "trigger": attempt.trigger,
        "status": attempt.status,
        "changed": attempt.changed,
        "detail": attempt.detail,
    }

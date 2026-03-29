#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

REPORT_DIR="$(latest_report_dir || true)"
if [[ -z "${REPORT_DIR:-}" ]]; then
  echo "No reports found under $(reports_root)"
  exit 1
fi

DIAGNOSTICS_FILE="$REPORT_DIR/01_diagnostics_summary.json"
DOCTOR_FILE="$REPORT_DIR/doctor.json"

if [[ -f "$DIAGNOSTICS_FILE" ]]; then
  REPORT_FILE="$DIAGNOSTICS_FILE"
elif [[ -f "$DOCTOR_FILE" ]]; then
  REPORT_FILE="$DOCTOR_FILE"
else
  echo "No diagnostics summary found in $REPORT_DIR"
  exit 1
fi

REPORT_FILE="$REPORT_FILE" REPORT_DIR="$REPORT_DIR" python3 - <<'PY'
import json
import os
from pathlib import Path

report_dir = Path(os.environ["REPORT_DIR"])
report_file = Path(os.environ["REPORT_FILE"])
payload = json.loads(report_file.read_text(encoding="utf-8"))
order_check_file = report_dir / "08_broker_order_check.json"
cancel_open_file = next((path for path in sorted(report_dir.glob("*_cancel_open_orders.json"))), None)
execution_run_file = next((path for path in sorted(report_dir.glob("*_execution_run.json"))), None)
execution_gate_file = next((path for path in sorted(report_dir.glob("*_execution_gate.json"))), None)
manual_reconcile_file = next((path for path in sorted(report_dir.glob("*_manual_reconcile.json"))), None)
acceptance_file = next((path for path in sorted(report_dir.glob("*_ops_acceptance.json"))), None)
go_live_file = next((path for path in sorted(report_dir.glob("*_ops_go_live.json"))), None)
live_acceptance_file = next((path for path in sorted(report_dir.glob("*_ops_live_acceptance.json"))), None)
rollout_checklist_file = next((path for path in sorted(report_dir.glob("*_ops_rollout_checklist.json"))), None)
milestones_file = next((path for path in sorted(report_dir.glob("*_ops_rollout_milestones.json"))), None)

summary = payload["summary"] if "summary" in payload else payload
print(f"report_dir: {report_dir}")
print(f"category: {summary.get('category')}")
print(f"severity: {summary.get('severity', 'n/a')}")
print(f"ready: {str(summary.get('ready', False)).lower()}")

findings = summary.get("findings", [])
if findings:
    print("findings:")
    for item in findings:
        print(f"- {item}")

next_actions = summary.get("next_actions", [])
if next_actions:
    print("next_actions:")
    for item in next_actions:
        print(f"- {item}")

if order_check_file.exists():
    order_check = json.loads(order_check_file.read_text(encoding="utf-8"))
    submission = order_check.get("submission", {})
    cancellation = order_check.get("cancellation", {})
    instrument = order_check.get("instrument", {})
    print("broker_order_check:")
    print(f"- symbol: {instrument.get('symbol')}")
    print(f"- quantity: {order_check.get('quantity')}")
    print(f"- submission_status: {submission.get('status')}")
    print(f"- broker_order_id: {submission.get('broker_order_id')}")
    if cancellation:
        print(f"- cancellation_status: {cancellation.get('status')}")

if cancel_open_file is not None:
    cancel_open = json.loads(cancel_open_file.read_text(encoding="utf-8"))
    print("cancel_open_orders:")
    print(f"- cancelled_count: {cancel_open.get('cancelled_count')}")
    print(f"- failed_count: {cancel_open.get('failed_count')}")
    for failure in cancel_open.get("failures", []):
        print(f"- failed: {failure.get('broker_order_id')} ({failure.get('error')})")

if execution_run_file is not None:
    execution_run = json.loads(execution_run_file.read_text(encoding="utf-8"))
    print("execution_run:")
    print(f"- submitted_count: {len(execution_run.get('submitted_orders', []))}")
    print(f"- failed_count: {len(execution_run.get('failed_orders', []))}")
    print(f"- approval_count: {execution_run.get('approval_count')}")
    for report in execution_run.get("submitted_orders", []):
        print(f"- submitted: {report.get('broker_order_id')} ({report.get('status')})")

if execution_gate_file is not None:
    execution_gate = json.loads(execution_gate_file.read_text(encoding="utf-8"))
    print("execution_gate:")
    print(f"- ready: {str(execution_gate.get('ready', False)).lower()}")
    print(f"- should_block: {str(execution_gate.get('should_block', False)).lower()}")
    print(f"- policy_stage: {execution_gate.get('policy_stage')}")
    print(f"- recommended_stage: {execution_gate.get('recommended_stage')}")

if manual_reconcile_file is not None:
    manual_reconcile = json.loads(manual_reconcile_file.read_text(encoding="utf-8"))
    print("manual_reconcile:")
    print(f"- status: {manual_reconcile.get('status')}")
    if manual_reconcile.get("status") == "ok":
        approval = manual_reconcile.get("approval", {})
        reconciliation = manual_reconcile.get("reconciliation", {})
        print(f"- approval_status: {approval.get('approval', {}).get('status')}")
        print(f"- reconcile_status: {reconciliation.get('status')}")
    else:
        print(f"- detail: {manual_reconcile.get('detail')}")

if acceptance_file is not None:
    acceptance = json.loads(acceptance_file.read_text(encoding="utf-8"))
    evidence = acceptance.get("evidence", {})
    print("acceptance:")
    print(f"- ready_weeks: {acceptance.get('ready_weeks')}")
    print(f"- current_clean_week_streak: {evidence.get('current_clean_week_streak')}")
    print(f"- blocked_days: {evidence.get('blocked_days')}")

if go_live_file is not None:
    go_live = json.loads(go_live_file.read_text(encoding="utf-8"))
    print("go_live:")
    print(f"- promotion_allowed: {str(go_live.get('promotion_allowed', False)).lower()}")
    print(f"- policy_stage: {go_live.get('policy', {}).get('stage')}")
    print(f"- recommended_stage: {go_live.get('rollout', {}).get('current_recommendation')}")

if live_acceptance_file is not None:
    live_acceptance = json.loads(live_acceptance_file.read_text(encoding="utf-8"))
    print("live_acceptance:")
    print(f"- ready_for_live: {str(live_acceptance.get('ready_for_live', False)).lower()}")
    print(f"- incident_count: {live_acceptance.get('incident_count')}")
    print(f"- blocker_count: {len(live_acceptance.get('blockers', []))}")

if rollout_checklist_file is not None:
    rollout_checklist = json.loads(rollout_checklist_file.read_text(encoding="utf-8"))
    print("rollout_checklist:")
    print(f"- stage: {rollout_checklist.get('stage')}")
    print(f"- ready: {str(rollout_checklist.get('ready', False)).lower()}")
    print(f"- blocker_count: {len(rollout_checklist.get('blockers', []))}")

if milestones_file is not None:
    milestones = json.loads(milestones_file.read_text(encoding="utf-8"))
    print("rollout_milestones:")
    print(f"- next_pending_stage: {milestones.get('next_pending_stage')}")
PY

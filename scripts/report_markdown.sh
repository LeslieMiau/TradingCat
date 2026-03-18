#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

REPORT_REF="${1:-latest}"

if [[ "$REPORT_REF" == "latest" ]]; then
  REPORT_DIR="$(latest_report_dir || true)"
else
  REPORT_DIR="$(resolve_report_dir "$REPORT_REF" || true)"
fi

if [[ -z "${REPORT_DIR:-}" ]]; then
  echo "Report not found"
  exit 1
fi

if [[ -f "$REPORT_DIR/01_diagnostics_summary.json" ]]; then
  SUMMARY_FILE="$REPORT_DIR/01_diagnostics_summary.json"
elif [[ -f "$REPORT_DIR/doctor.json" ]]; then
  SUMMARY_FILE="$REPORT_DIR/doctor.json"
else
  echo "No summary JSON found in $REPORT_DIR"
  exit 1
fi

SUMMARY_FILE="$SUMMARY_FILE" REPORT_DIR="$REPORT_DIR" python3 - <<'PY'
import json
import os
from pathlib import Path

report_dir = Path(os.environ["REPORT_DIR"])
payload = json.loads(Path(os.environ["SUMMARY_FILE"]).read_text(encoding="utf-8"))
summary = payload["summary"] if "summary" in payload else payload
order_check_file = report_dir / "08_broker_order_check.json"
cancel_open_file = next((path for path in sorted(report_dir.glob("*_cancel_open_orders.json"))), None)
execution_run_file = next((path for path in sorted(report_dir.glob("*_execution_run.json"))), None)
execution_gate_file = next((path for path in sorted(report_dir.glob("*_execution_gate.json"))), None)
manual_reconcile_file = next((path for path in sorted(report_dir.glob("*_manual_reconcile.json"))), None)
go_live_file = next((path for path in sorted(report_dir.glob("*_ops_go_live.json"))), None)
live_acceptance_file = next((path for path in sorted(report_dir.glob("*_ops_live_acceptance.json"))), None)
rollout_checklist_file = next((path for path in sorted(report_dir.glob("*_ops_rollout_checklist.json"))), None)
milestones_file = next((path for path in sorted(report_dir.glob("*_ops_rollout_milestones.json"))), None)

print(f"# TradingCat Validation Report")
print()
print(f"- Report Dir: `{report_dir}`")
print(f"- Category: `{summary.get('category')}`")
print(f"- Severity: `{summary.get('severity', 'n/a')}`")
print(f"- Ready: `{str(summary.get('ready', False)).lower()}`")
print()

findings = summary.get("findings", [])
print("## Findings")
if findings:
    for item in findings:
        print(f"- {item}")
else:
    print("- None")
print()

actions = summary.get("next_actions", [])
print("## Next Actions")
if actions:
    for item in actions:
        print(f"- {item}")
else:
    print("- None")

if order_check_file.exists():
    order_check = json.loads(order_check_file.read_text(encoding="utf-8"))
    submission = order_check.get("submission", {})
    cancellation = order_check.get("cancellation", {})
    instrument = order_check.get("instrument", {})
    print()
    print("## Broker Order Check")
    print(f"- Symbol: `{instrument.get('symbol')}`")
    print(f"- Quantity: `{order_check.get('quantity')}`")
    print(f"- Submission Status: `{submission.get('status')}`")
    print(f"- Broker Order ID: `{submission.get('broker_order_id')}`")
    if cancellation:
        print(f"- Cancellation Status: `{cancellation.get('status')}`")

if cancel_open_file is not None:
    cancel_open = json.loads(cancel_open_file.read_text(encoding="utf-8"))
    print()
    print("## Cancel Open Orders")
    print(f"- Cancelled Count: `{cancel_open.get('cancelled_count')}`")
    print(f"- Failed Count: `{cancel_open.get('failed_count')}`")
    for failure in cancel_open.get("failures", []):
        print(f"- Failed Cancel: `{failure.get('broker_order_id')}` `{failure.get('error')}`")

if execution_run_file is not None:
    execution_run = json.loads(execution_run_file.read_text(encoding="utf-8"))
    print()
    print("## Execution Run")
    print(f"- Submitted Count: `{len(execution_run.get('submitted_orders', []))}`")
    print(f"- Failed Count: `{len(execution_run.get('failed_orders', []))}`")
    print(f"- Approval Count: `{execution_run.get('approval_count')}`")
    for report in execution_run.get("submitted_orders", []):
        print(f"- Submitted Order: `{report.get('broker_order_id')}` `{report.get('status')}`")

if execution_gate_file is not None:
    execution_gate = json.loads(execution_gate_file.read_text(encoding="utf-8"))
    print()
    print("## Execution Gate")
    print(f"- Ready: `{str(execution_gate.get('ready', False)).lower()}`")
    print(f"- Should Block: `{str(execution_gate.get('should_block', False)).lower()}`")
    print(f"- Policy Stage: `{execution_gate.get('policy_stage')}`")
    print(f"- Recommended Stage: `{execution_gate.get('recommended_stage')}`")

if manual_reconcile_file is not None:
    manual_reconcile = json.loads(manual_reconcile_file.read_text(encoding="utf-8"))
    print()
    print("## Manual Reconcile")
    print(f"- Status: `{manual_reconcile.get('status')}`")
    if manual_reconcile.get("status") == "ok":
        approval = manual_reconcile.get("approval", {})
        reconciliation = manual_reconcile.get("reconciliation", {})
        print(f"- Approval Status: `{approval.get('approval', {}).get('status')}`")
        print(f"- Reconcile Status: `{reconciliation.get('status')}`")
    else:
        print(f"- Detail: `{manual_reconcile.get('detail')}`")

if go_live_file is not None:
    go_live = json.loads(go_live_file.read_text(encoding="utf-8"))
    print()
    print("## Go-Live")
    print(f"- Promotion Allowed: `{str(go_live.get('promotion_allowed', False)).lower()}`")
    print(f"- Policy Stage: `{go_live.get('policy', {}).get('stage')}`")
    print(f"- Recommended Stage: `{go_live.get('rollout', {}).get('current_recommendation')}`")
    for item in go_live.get("next_actions", []):
        print(f"- Next Action: {item}")

if live_acceptance_file is not None:
    live_acceptance = json.loads(live_acceptance_file.read_text(encoding="utf-8"))
    print()
    print("## Live Acceptance")
    print(f"- Ready For Live: `{str(live_acceptance.get('ready_for_live', False)).lower()}`")
    print(f"- Incident Count: `{live_acceptance.get('incident_count')}`")
    print(f"- Blockers: `{len(live_acceptance.get('blockers', []))}`")

if rollout_checklist_file is not None:
    rollout_checklist = json.loads(rollout_checklist_file.read_text(encoding="utf-8"))
    print()
    print("## Rollout Checklist")
    print(f"- Stage: `{rollout_checklist.get('stage')}`")
    print(f"- Ready: `{str(rollout_checklist.get('ready', False)).lower()}`")
    print(f"- Blockers: `{len(rollout_checklist.get('blockers', []))}`")

if milestones_file is not None:
    milestones = json.loads(milestones_file.read_text(encoding="utf-8"))
    print()
    print("## Rollout Milestones")
    print(f"- Next Pending Stage: `{milestones.get('next_pending_stage')}`")
    for item in milestones.get("milestones", []):
        print(
            f"- `{item.get('stage')}` `{item.get('status')}` "
            f"({item.get('progress_weeks')}/{item.get('required_weeks')} weeks)"
        )
PY

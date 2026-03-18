#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

REPORT_DIR=""
INCLUDE_ORDER_CHECK="${TRADINGCAT_INCLUDE_ORDER_CHECK:-false}"
INCLUDE_EXECUTION_RUN="${TRADINGCAT_INCLUDE_EXECUTION_RUN:-false}"
INCLUDE_MANUAL_RECONCILE="${TRADINGCAT_INCLUDE_MANUAL_RECONCILE:-false}"
ORDER_CHECK_SYMBOL="${TRADINGCAT_ORDER_CHECK_SYMBOL:-}"
ORDER_CHECK_QUANTITY="${TRADINGCAT_ORDER_CHECK_QUANTITY:-1}"
ORDER_CHECK_AUTO_CANCEL="${TRADINGCAT_ORDER_CHECK_AUTO_CANCEL:-true}"
MANUAL_FILL_PRICE="${TRADINGCAT_MANUAL_FILL_PRICE:-5.0}"
TOTAL_STEPS=24

if [[ "$INCLUDE_ORDER_CHECK" == "true" ]]; then
  TOTAL_STEPS=24
fi
if [[ "$INCLUDE_EXECUTION_RUN" == "true" ]]; then
  TOTAL_STEPS=$((TOTAL_STEPS + 2))
fi
if [[ "$INCLUDE_MANUAL_RECONCILE" == "true" ]]; then
  TOTAL_STEPS=$((TOTAL_STEPS + 1))
fi

if [[ "${TRADINGCAT_ARCHIVE_REPORTS:-false}" == "true" ]]; then
  REPORT_DIR="$(ensure_report_dir)"
fi

ORDER_CHECK_PAYLOAD="{\"quantity\":$ORDER_CHECK_QUANTITY,\"auto_cancel\":$ORDER_CHECK_AUTO_CANCEL}"
if [[ -n "$ORDER_CHECK_SYMBOL" ]]; then
  ORDER_CHECK_PAYLOAD="{\"symbol\":\"$ORDER_CHECK_SYMBOL\",\"quantity\":$ORDER_CHECK_QUANTITY,\"auto_cancel\":$ORDER_CHECK_AUTO_CANCEL}"
fi

write_step() {
  local name content
  name="$1"
  content="$2"
  if [[ -n "$REPORT_DIR" ]]; then
    printf '%s\n' "$content" > "$REPORT_DIR/$name.json"
  fi
}

echo "[1/$TOTAL_STEPS] diagnostics summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/diagnostics/summary")"
write_step "01_diagnostics_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[2/$TOTAL_STEPS] startup preflight"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/preflight/startup")"
write_step "02_startup_preflight" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[3/$TOTAL_STEPS] broker status"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/broker/status")"
write_step "03_broker_status" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[4/$TOTAL_STEPS] broker validation"
STEP_OUTPUT="$(curl --silent --show-error -X POST "$BASE_URL/broker/validate")"
write_step "04_broker_validation" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[5/$TOTAL_STEPS] broker probe"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/broker/probe")"
write_step "05_broker_probe" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[6/$TOTAL_STEPS] market data smoke test"
STEP_OUTPUT="$(curl --silent --show-error -X POST \
  -H "Content-Type: application/json" \
  -d '{"include_bars":true,"include_option_chain":false}' \
  "$BASE_URL/market-data/smoke-test")"
write_step "06_market_data_smoke_test" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[7/$TOTAL_STEPS] execution preview"
STEP_OUTPUT="$(curl --silent --show-error -X POST \
  -H "Content-Type: application/json" \
  -d '{}' \
  "$BASE_URL/execution/preview")"
write_step "07_execution_preview" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[8/$TOTAL_STEPS] execution gate"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/execution/gate")"
write_step "08_execution_gate" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[9/$TOTAL_STEPS] alerts summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/alerts/summary")"
write_step "09_alerts_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[10/$TOTAL_STEPS] compliance summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/compliance/checklists/summary")"
write_step "10_compliance_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"
printf '\n\n'

echo "[11/$TOTAL_STEPS] operations readiness"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/readiness")"
write_step "11_operations_readiness" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[12/$TOTAL_STEPS] operations rollout"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/rollout")"
write_step "12_ops_rollout" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[13/$TOTAL_STEPS] execution quality"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/execution/quality")"
write_step "13_execution_quality" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[14/$TOTAL_STEPS] recovery summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/broker/recovery-summary")"
write_step "14_recovery_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[15/$TOTAL_STEPS] execution authorization"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/execution/authorization")"
write_step "15_execution_authorization" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[16/$TOTAL_STEPS] operations execution metrics"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/execution-metrics")"
write_step "16_ops_execution_metrics" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[17/$TOTAL_STEPS] research selection summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/research/selections/summary")"
write_step "17_selection_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[18/$TOTAL_STEPS] rollout policy"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/rollout-policy")"
write_step "18_rollout_policy" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[19/$TOTAL_STEPS] allocation summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/research/allocations/summary")"
write_step "19_allocation_summary" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[20/$TOTAL_STEPS] history sync status"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/data/history/sync-status")"
write_step "20_history_sync" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[21/$TOTAL_STEPS] go-live summary"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/go-live")"
write_step "21_ops_go_live" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[22/$TOTAL_STEPS] live acceptance"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/live-acceptance")"
write_step "22_ops_live_acceptance" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[23/$TOTAL_STEPS] rollout checklist"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/rollout/checklist?stage=10%")"
write_step "23_ops_rollout_checklist" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

printf '\n\n'
echo "[24/$TOTAL_STEPS] rollout milestones"
STEP_OUTPUT="$(curl --silent --show-error "$BASE_URL/ops/rollout/milestones")"
write_step "24_ops_rollout_milestones" "$STEP_OUTPUT"
printf '%s' "$STEP_OUTPUT"

if [[ "$INCLUDE_ORDER_CHECK" == "true" ]]; then
  printf '\n\n'
  echo "[25/$TOTAL_STEPS] broker order check"
  STEP_OUTPUT="$(curl --silent --show-error -X POST \
    -H "Content-Type: application/json" \
    -d "$ORDER_CHECK_PAYLOAD" \
    "$BASE_URL/broker/order-check")"
  write_step "08_broker_order_check" "$STEP_OUTPUT"
  printf '%s' "$STEP_OUTPUT"
fi

if [[ "$INCLUDE_EXECUTION_RUN" == "true" ]]; then
  printf '\n\n'
  CANCEL_STEP=25
  RUN_STEP=26
  if [[ "$INCLUDE_ORDER_CHECK" == "true" ]]; then
    CANCEL_STEP=26
    RUN_STEP=27
  fi

  echo "[$CANCEL_STEP/$TOTAL_STEPS] cancel open orders"
  STEP_OUTPUT="$(curl --silent --show-error -X POST "$BASE_URL/orders/cancel-open")"
  write_step "$(printf '%02d' "$CANCEL_STEP")_cancel_open_orders" "$STEP_OUTPUT"
  printf '%s' "$STEP_OUTPUT"

  printf '\n\n'
  echo "[$RUN_STEP/$TOTAL_STEPS] execution run"
  STEP_OUTPUT="$(curl --silent --show-error -X POST \
    -H "Content-Type: application/json" \
    -d '{}' \
    "$BASE_URL/execution/run")"
  write_step "$(printf '%02d' "$RUN_STEP")_execution_run" "$STEP_OUTPUT"
  printf '%s' "$STEP_OUTPUT"
fi

if [[ "$INCLUDE_MANUAL_RECONCILE" == "true" ]]; then
  printf '\n\n'
  MANUAL_STEP=$TOTAL_STEPS
  echo "[$MANUAL_STEP/$TOTAL_STEPS] manual approval reconcile"
  APPROVALS_JSON="$(curl --silent --show-error "$BASE_URL/approvals")"
  PENDING_APPROVAL_ID="$(
    APPROVALS_JSON="$APPROVALS_JSON" python3 - <<'PY'
import json
import os

items = json.loads(os.environ["APPROVALS_JSON"])
pending = [item for item in items if item.get("status") == "pending"]
print(pending[-1]["id"] if pending else "")
PY
  )"

  if [[ -z "$PENDING_APPROVAL_ID" ]]; then
    STEP_OUTPUT='{"status":"skipped","detail":"no pending approvals"}'
  else
    APPROVE_JSON="$(curl --silent --show-error -X POST \
      -H "Content-Type: application/json" \
      -d '{"reason":"manual confirmation from post_validate"}' \
      "$BASE_URL/approvals/$PENDING_APPROVAL_ID/approve")"
    RECONCILE_PAYLOAD="$(
      APPROVE_JSON="$APPROVE_JSON" MANUAL_FILL_PRICE="$MANUAL_FILL_PRICE" python3 - <<'PY'
import json
import os

payload = json.loads(os.environ["APPROVE_JSON"])
intent = payload["approval"]["order_intent"]
report = payload["execution_report"]
print(json.dumps({
    "order_intent_id": intent["id"],
    "broker_order_id": report["broker_order_id"],
    "filled_quantity": intent["quantity"],
    "average_price": float(os.environ["MANUAL_FILL_PRICE"]),
    "notes": "manual fill from post_validate",
}))
PY
    )"
    RECONCILE_JSON="$(curl --silent --show-error -X POST \
      -H "Content-Type: application/json" \
      -d "$RECONCILE_PAYLOAD" \
      "$BASE_URL/reconcile/manual-fill")"
    STEP_OUTPUT="$(
      APPROVE_JSON="$APPROVE_JSON" RECONCILE_JSON="$RECONCILE_JSON" python3 - <<'PY'
import json
import os

print(json.dumps({
    "status": "ok",
    "approval": json.loads(os.environ["APPROVE_JSON"]),
    "reconciliation": json.loads(os.environ["RECONCILE_JSON"]),
}))
PY
    )"
  fi

  write_step "$(printf '%02d' "$MANUAL_STEP")_manual_reconcile" "$STEP_OUTPUT"
  printf '%s' "$STEP_OUTPUT"
fi

if [[ -n "$REPORT_DIR" ]]; then
  printf '\n\nreport_dir: %s' "$REPORT_DIR"
fi
printf '\n'

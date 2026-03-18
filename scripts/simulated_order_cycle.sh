#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"

echo "[1/4] run execution cycle"
curl --silent --show-error -X POST \
  -H "Content-Type: application/json" \
  -d '{}' \
  "$BASE_URL/execution/run"
printf '\n\n'

echo "[2/4] list approvals"
APPROVALS_JSON="$(curl --silent --show-error "$BASE_URL/approvals")"
printf '%s\n\n' "$APPROVALS_JSON"

APPROVAL_ID="$(
  APPROVALS_JSON="$APPROVALS_JSON" python3 - <<'PY'
import json
import os

items = json.loads(os.environ["APPROVALS_JSON"])
pending_items = [item for item in items if item.get("status") == "pending"]
pending = pending_items[-1] if pending_items else None
print(pending["id"] if pending else "")
PY
)"

if [[ -n "$APPROVAL_ID" ]]; then
  echo "[3/4] approve first manual order"
  curl --silent --show-error -X POST \
    -H "Content-Type: application/json" \
    -d '{"reason":"manual confirmation from simulated order cycle"}' \
    "$BASE_URL/approvals/$APPROVAL_ID/approve"
  printf '\n\n'
else
  echo "[3/4] no approvals to process"
  printf '\n'
fi

echo "[4/4] list orders"
curl --silent --show-error "$BASE_URL/orders"
printf '\n'

#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
RAW_JSON="$(curl --silent --show-error "$BASE_URL/diagnostics/summary")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

if [[ "${TRADINGCAT_ARCHIVE_REPORTS:-false}" == "true" ]]; then
  REPORT_DIR="$(ensure_report_dir)"
  printf '%s\n' "$RAW_JSON" > "$REPORT_DIR/doctor.json"
  export TRADINGCAT_REPORT_DIR="$REPORT_DIR"
fi

DIAGNOSTICS_JSON="$RAW_JSON" python3 - <<'PY'
import json
import os
import sys

payload = json.loads(os.environ["DIAGNOSTICS_JSON"])
summary = payload["summary"]
category = summary["category"]
severity = summary.get("severity", "info")
ready = summary.get("ready", False)

print(f"category: {category}")
print(f"severity: {severity}")
print(f"ready: {str(ready).lower()}")

if summary.get("findings"):
    print("findings:")
    for item in summary["findings"]:
        print(f"- {item}")

if summary.get("next_actions"):
    print("next_actions:")
    for item in summary["next_actions"]:
        print(f"- {item}")

report_dir = os.environ.get("TRADINGCAT_REPORT_DIR")
if report_dir:
    print(f"report_dir: {report_dir}")

exit_code_map = {
    "info": 0,
    "warning": 1,
    "error": 2,
}
sys.exit(exit_code_map.get(severity, 2))
PY

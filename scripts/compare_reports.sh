#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: ./scripts/compare_reports.sh <older_report_dir|timestamp> <newer_report_dir|timestamp>"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

OLDER_DIR="$(resolve_report_dir "$1")"
NEWER_DIR="$(resolve_report_dir "$2")"

resolve_summary_file() {
  local dir
  dir="$1"
  if [[ -f "$dir/01_diagnostics_summary.json" ]]; then
    printf '%s\n' "$dir/01_diagnostics_summary.json"
    return 0
  fi
  if [[ -f "$dir/doctor.json" ]]; then
    printf '%s\n' "$dir/doctor.json"
    return 0
  fi
  return 1
}

OLDER_FILE="$(resolve_summary_file "$OLDER_DIR" || true)"
NEWER_FILE="$(resolve_summary_file "$NEWER_DIR" || true)"

if [[ -z "$OLDER_FILE" || -z "$NEWER_FILE" ]]; then
  echo "Both report directories must contain 01_diagnostics_summary.json or doctor.json"
  exit 1
fi

OLDER_FILE="$OLDER_FILE" NEWER_FILE="$NEWER_FILE" python3 - <<'PY'
import json
import os
from pathlib import Path

older = json.loads(Path(os.environ["OLDER_FILE"]).read_text(encoding="utf-8"))
newer = json.loads(Path(os.environ["NEWER_FILE"]).read_text(encoding="utf-8"))

older_summary = older["summary"]
newer_summary = newer["summary"]

print(f"older: {Path(os.environ['OLDER_FILE']).parent}")
print(f"newer: {Path(os.environ['NEWER_FILE']).parent}")
print(f"category: {older_summary.get('category')} -> {newer_summary.get('category')}")
print(f"severity: {older_summary.get('severity')} -> {newer_summary.get('severity')}")
print(f"ready: {str(older_summary.get('ready')).lower()} -> {str(newer_summary.get('ready')).lower()}")

older_findings = set(older_summary.get("findings", []))
newer_findings = set(newer_summary.get("findings", []))
added = sorted(newer_findings - older_findings)
removed = sorted(older_findings - newer_findings)

if added:
    print("added_findings:")
    for item in added:
        print(f"- {item}")

if removed:
    print("removed_findings:")
    for item in removed:
        print(f"- {item}")
PY

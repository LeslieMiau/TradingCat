#!/usr/bin/env bash
set -euo pipefail

KEEP_COUNT="${1:-10}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/reports.sh"

if ! [[ "$KEEP_COUNT" =~ ^[0-9]+$ ]]; then
  echo "Usage: ./scripts/cleanup_reports.sh [keep_count]"
  exit 1
fi

REPORTS_ROOT="$(reports_root)"
if [[ ! -d "$REPORTS_ROOT" ]]; then
  echo "No report directory found at $REPORTS_ROOT"
  exit 0
fi

REPORT_DIRS=()
while IFS= read -r line; do
  REPORT_DIRS+=("$line")
done < <(find "$REPORTS_ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
TOTAL="${#REPORT_DIRS[@]}"

if (( TOTAL <= KEEP_COUNT )); then
  echo "Nothing to clean. total=$TOTAL keep=$KEEP_COUNT"
  exit 0
fi

DELETE_COUNT=$((TOTAL - KEEP_COUNT))
for ((i = 0; i < DELETE_COUNT; i++)); do
  echo "Removing ${REPORT_DIRS[$i]}"
  rm -rf "${REPORT_DIRS[$i]}"
done

echo "Removed $DELETE_COUNT report directories. Kept $KEEP_COUNT."

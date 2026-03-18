#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
MODE="${2:-with-manual-cycle}"

echo "[post_validate] running archived validation flow"
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_all.sh "$BASE_URL" "$MODE"

echo
echo "[post_validate] latest report"
./scripts/latest_report.sh

echo
echo "[post_validate] markdown summary"
./scripts/report_markdown.sh latest

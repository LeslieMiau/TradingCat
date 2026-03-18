#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-http://127.0.0.1:8000}"
MODE="${2:-validate-only}"

echo "[validate_all] doctor"
set +e
./scripts/doctor.sh "$BASE_URL"
DOCTOR_EXIT=$?
set -e

case "$DOCTOR_EXIT" in
  0)
    echo "[validate_all] doctor status: ready"
    ;;
  1)
    echo "[validate_all] doctor status: warning, continuing with validation"
    ;;
  2)
    echo "[validate_all] doctor status: blocking error, stopping"
    exit 2
    ;;
  *)
    echo "[validate_all] doctor status: unexpected exit code $DOCTOR_EXIT"
    exit "$DOCTOR_EXIT"
    ;;
esac

echo
echo "[validate_all] validate_broker"
if [[ "$MODE" == "with-live-cycle" ]]; then
  TRADINGCAT_INCLUDE_ORDER_CHECK=true TRADINGCAT_INCLUDE_EXECUTION_RUN=true ./scripts/validate_broker.sh "$BASE_URL"
elif [[ "$MODE" == "with-manual-cycle" ]]; then
  TRADINGCAT_INCLUDE_ORDER_CHECK=true \
  TRADINGCAT_INCLUDE_EXECUTION_RUN=true \
  TRADINGCAT_INCLUDE_MANUAL_RECONCILE=true \
  ./scripts/validate_broker.sh "$BASE_URL"
elif [[ "$MODE" == "with-order-check" ]]; then
  TRADINGCAT_INCLUDE_ORDER_CHECK=true ./scripts/validate_broker.sh "$BASE_URL"
else
  ./scripts/validate_broker.sh "$BASE_URL"
fi

if [[ "$MODE" == "with-cycle" ]]; then
  echo
  echo "[validate_all] simulated_order_cycle"
  ./scripts/simulated_order_cycle.sh "$BASE_URL"
fi

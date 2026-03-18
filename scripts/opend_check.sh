#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
ENV_FILE="$ROOT_DIR/.env"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv"
  exit 2
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing .env at $ENV_FILE"
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

"$VENV_PYTHON" - <<'PY'
import importlib.util
import json
import os
import socket
import sys

host = os.environ.get("TRADINGCAT_FUTU_HOST", "127.0.0.1")
port = int(os.environ.get("TRADINGCAT_FUTU_PORT", "11111"))
enabled = os.environ.get("TRADINGCAT_FUTU_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
environment = os.environ.get("TRADINGCAT_FUTU_ENVIRONMENT", "SIMULATE").upper()

sdk_ok = importlib.util.find_spec("futu") is not None
tcp_ok = False
tcp_error = ""
try:
    with socket.create_connection((host, port), timeout=1.5):
        tcp_ok = True
except OSError as exc:
    tcp_error = str(exc)

payload = {
    "enabled": enabled,
    "environment": environment,
    "host": host,
    "port": port,
    "checks": {
        "sdk_import": {
            "ok": sdk_ok,
            "detail": "futu SDK importable" if sdk_ok else "futu SDK missing in current virtualenv",
        },
        "tcp_connect": {
            "ok": tcp_ok,
            "detail": "OpenD TCP port reachable" if tcp_ok else tcp_error,
        },
        "mode": {
            "ok": environment in {"SIMULATE", "REAL"},
            "detail": environment,
        },
    },
}

print(json.dumps(payload, ensure_ascii=True, indent=2))

if not enabled:
    sys.exit(1)
if not sdk_ok or not tcp_ok or environment not in {"SIMULATE", "REAL"}:
    sys.exit(2)
PY

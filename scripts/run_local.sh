#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTHON="$ROOT_DIR/.venv/bin/python"

if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Missing virtualenv at $ROOT_DIR/.venv"
  echo "Create it first with: python3 -m venv .venv && .venv/bin/python -m pip install -e '.[dev]'"
  exit 1
fi

if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi

echo "[preflight] startup configuration"
"$VENV_PYTHON" - <<'PY'
import json
from tradingcat.config import AppConfig
from tradingcat.services.preflight import build_startup_preflight

payload = build_startup_preflight(AppConfig.from_env())
print(json.dumps(payload, ensure_ascii=True, indent=2, default=str))
PY

ARGS=(tradingcat.main:app --host 127.0.0.1 --port 8000)
if [[ "${TRADINGCAT_RELOAD:-false}" == "true" ]]; then
  ARGS+=(--reload)
fi

exec "$ROOT_DIR/.venv/bin/uvicorn" "${ARGS[@]}"

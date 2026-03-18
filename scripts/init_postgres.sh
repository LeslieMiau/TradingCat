#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${TRADINGCAT_ROOT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
ENV_FILE="$ROOT_DIR/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ENV_FILE"
  set +a
fi

DSN="${TRADINGCAT_POSTGRES_DSN:-postgresql:///tradingcat}"
DB_NAME="${TRADINGCAT_POSTGRES_DB_NAME:-tradingcat}"

if ! command -v createdb >/dev/null 2>&1; then
  echo "createdb not found; install PostgreSQL client tools first."
  exit 1
fi

createdb "$DB_NAME" 2>/dev/null || true

"$ROOT_DIR/.venv/bin/python" - <<'PY'
from tradingcat.config import AppConfig
from tradingcat.repositories.postgres_store import PostgresStore

config = AppConfig.from_env()
if not config.postgres.enabled:
    raise SystemExit("Set TRADINGCAT_POSTGRES_ENABLED=true in .env before initializing PostgreSQL.")

store = PostgresStore(config.postgres.dsn)
store.save("bootstrap_probe", {"status": "ok"})
payload = store.load("bootstrap_probe", {})
print(payload)
PY

echo "PostgreSQL initialized for TradingCat using $DSN"

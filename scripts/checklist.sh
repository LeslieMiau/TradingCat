#!/usr/bin/env bash
set -euo pipefail

cat <<'EOF'
TradingCat local validation checklist

1. Prepare environment
   - Create `.venv` and install `.[dev]`
   - If using Futu/OpenD, also install `.[dev,futu]`
   - Create `.env` with `./scripts/bootstrap_env.sh simulate` or copy `.env.example`

2. Start services
   - Launch Futu OpenD locally and log in
   - Run `./scripts/run_local.sh`

3. Run read-only validation
   - Run `./scripts/doctor.sh`
   - Run `./scripts/validate_broker.sh`
   - Confirm diagnostics category is `ready_for_validation`

4. Run simulated execution loop
   - Run `./scripts/simulated_order_cycle.sh`
   - Verify approvals, order creation, and cancel paths as needed

5. Escalate carefully
   - Keep `TRADINGCAT_FUTU_ENVIRONMENT=SIMULATE` until all read-only and simulated checks pass
   - Only then consider `REAL`, unlock password, and final order validation
EOF

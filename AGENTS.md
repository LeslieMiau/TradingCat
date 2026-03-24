# TradingCat Agent Guide

## Canonical Docs
- Use [README.md](/Users/miau/Documents/TradingCat/README.md) for setup, local run commands, and validation entrypoints.
- Use [PLAN.md](/Users/miau/Documents/TradingCat/PLAN.md) for architecture, trading boundaries, rollout stages, and risk limits.
- Keep this file short and operational. Put durable agent rules here; keep product detail in the project docs above.

## Repo Layout
- `tradingcat/`: application code, domain models, adapters, services, and API routes.
- `tests/`: pytest coverage for trading, execution, and control-plane behavior.
- `scripts/`: local operator, diagnostics, and validation scripts.
- `data/`: local state, reports, and generated artifacts. Treat it as runtime data, not source.
- `templates/` and `static/`: dashboard UI assets.

## Standard Workflow
- Read the relevant code paths and the nearby tests before editing.
- If a request will likely require more than 100 lines of code changes or is clearly multi-step, plan first before implementation.
- If behavior changes, add or update tests in `tests/`.
- Run the smallest relevant check first. Default to `pytest` unless a narrower check is clearly enough.
- After functional changes, run the relevant tests, confirm they pass, then push the branch to the remote.
- End each task with what changed, what was verified, and any remaining risk or unverified path.

## Setup And Safe Commands
- Environment setup: `python -m venv .venv`, `source .venv/bin/activate`, `pip install -e .[dev]`
- Default local env modes: `./scripts/bootstrap_env.sh disabled` or `./scripts/bootstrap_env.sh simulate`
- Start the app locally: `./scripts/run_local.sh`
- Safe checks: `pytest`, `./scripts/checklist.sh`, `./scripts/doctor.sh`
- Safe diagnostics when explicitly relevant: `./scripts/opend_check.sh`
- Controlled validation only in default no-execution mode: `./scripts/validate_broker.sh`, `./scripts/validate_all.sh`

## Safety Boundaries
- Treat `disabled` or `simulate` as the default environment. Do not switch to real trading or assume Futu/OpenD is online unless the user explicitly asks for that workflow.
- Do not edit `.env`, add real credentials, or change broker/account settings unless the user explicitly requests it.
- AI may assist with research, debugging, reporting, and engineering. It must not invent, approve, or silently execute live trading decisions.
- Do not run side-effectful trading flows unless the user explicitly requests that exact action.

## Explicit Approval Required
- `./scripts/simulated_order_cycle.sh`
- `./scripts/validate_all.sh with-cycle`
- `./scripts/validate_all.sh with-live-cycle`
- `./scripts/validate_all.sh with-manual-cycle`
- `./scripts/post_validate.sh`
- Any flow that calls `/orders/cancel-open`, `/execution/run`, `/approvals/*/approve`, or `/reconcile/manual-fill`

## Done Means
- Relevant code and docs were read before changes were made.
- Tests or checks relevant to the change were run, or the reason they were not run is stated plainly.
- No command with trading, approval, cancel, or reconciliation side effects was executed without explicit user instruction.

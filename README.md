# TradingCat

TradingCat is a local-first trading system baseline for Hong Kong, U.S., and A-share markets. This repository now implements the V1 architecture described in [PLAN.md](/Users/miau/Documents/TradingCat/PLAN.md): a Python control plane with explicit domain models, strategy generation, risk checks, approval workflow, execution adapters, and a minimal backtesting engine.

## What Is Implemented

- A typed domain layer for `Instrument`, `Signal`, `OrderIntent`, `ExecutionReport`, `ApprovalRequest`, and `PortfolioSnapshot`
- Core interfaces from the plan: `MarketDataAdapter`, `BrokerAdapter`, `Strategy`, `RiskEngine`, and `ApprovalService`
- Three V1 strategy placeholders:
  - ETF trend / rotation
  - HK/US equity momentum
  - Option overlay baseline (research-active, execution-disabled by default)
- A FastAPI control panel exposing:
  - `GET /dashboard`
  - `GET /dashboard/summary`
  - `GET /dashboard/research`
  - `GET /dashboard/operations`
  - `GET /dashboard/strategies/{strategy_id}`
  - `GET /journal/plans`
  - `GET /journal/plans/latest`
  - `POST /journal/plans/generate`
  - `GET /journal/summaries`
  - `GET /journal/summaries/latest`
  - `POST /journal/summaries/generate`
  - `GET /signals/today`
  - `GET /portfolio`
  - `GET /audit/logs`
  - `GET /audit/summary`
  - `POST /portfolio/risk-state`
  - `POST /portfolio/reconcile`
  - `GET /orders`
  - `POST /orders/{broker_order_id}/cancel`
  - `GET /broker/status`
  - `POST /broker/validate`
  - `GET /broker/probe`
  - `POST /broker/recover`
  - `POST /market-data/smoke-test`
  - `GET /data/instruments`
  - `POST /data/instruments`
  - `POST /data/history/sync`
  - `GET /data/history/bars`
  - `GET /data/history/coverage`
  - `GET /data/history/sync-runs`
  - `GET /data/history/sync-status`
  - `GET /data/history/repair-plan`
  - `POST /data/history/repair`
  - `GET /data/quality`
  - `GET /data/history/corporate-actions`
  - `POST /data/fx/sync`
  - `GET /data/fx/rates`
  - `POST /execution/preview`
  - `GET /execution/gate`
  - `POST /execution/run`
  - `POST /execution/reconcile`
  - `GET /execution/quality`
  - `GET /execution/authorization`
  - `GET /alerts`
  - `GET /alerts/summary`
  - `POST /alerts/evaluate`
  - `GET /compliance/checklists`
  - `GET /compliance/checklists/summary`
  - `POST /compliance/checklists/{checklist_id}/items/{item_id}`
  - `GET /ops/readiness`
  - `GET /ops/execution-metrics`
  - `GET /ops/daily-report`
  - `GET /ops/weekly-report`
  - `GET /ops/postmortem`
  - `GET /ops/incidents/replay`
  - `POST /ops/journal/record`
  - `GET /ops/journal`
  - `GET /ops/journal/summary`
  - `GET /ops/acceptance`
  - `GET /ops/acceptance/timeline`
  - `GET /ops/rollout`
  - `GET /ops/rollout/milestones`
  - `GET /ops/rollout-policy`
  - `GET /ops/go-live`
  - `GET /ops/live-acceptance`
  - `GET /ops/rollout/checklist`
  - `GET /ops/rollout/promotions`
  - `GET /ops/rollout/promotions/summary`
  - `POST /ops/rollout-policy`
  - `POST /ops/rollout-policy/apply-recommendation`
  - `POST /ops/rollout-policy/promote`
  - `GET /preflight/startup`
  - `GET /diagnostics/summary`
  - `GET /reports/latest`
  - `GET /reports/{report_ref}`
  - `GET /reports/latest/dashboard`
  - `GET /reports/{report_ref}/dashboard`
  - `GET /approvals`
  - `POST /approvals/{id}/approve`
  - `POST /approvals/{id}/expire`
  - `POST /approvals/{id}/reject`
  - `POST /approvals/expire-stale`
  - `GET /kill-switch`
  - `POST /kill-switch`
  - `POST /kill-switch/verify`
  - `POST /reconcile/manual-fill`
  - `POST /reconcile/manual-fills/import`
  - `GET /market-sessions`
  - `GET /scheduler/jobs`
  - `POST /scheduler/jobs/{id}/run`
  - `POST /orders/cancel-open`
  - `POST /research/backtests/run`
  - `GET /research/backtests`
  - `GET /research/backtests/compare`
  - `POST /research/report/run`
  - `POST /research/stability/run`
  - `POST /research/scorecard/run`
  - `POST /research/candidates/scorecard`
  - `GET /research/strategies/{strategy_id}`
  - `POST /research/recommendations/run`
  - `POST /research/ideas/run`
  - `POST /research/news/summarize`
  - `POST /research/selections/review`
  - `GET /research/selections`
  - `GET /research/selections/summary`
  - `POST /research/allocations/review`
  - `GET /research/allocations`
  - `GET /research/allocations/summary`
  - `POST /portfolio/rebalance-plan`
- Simulated broker and manual execution adapters, matching the V1 split between automated HK/US execution and manual A-share confirmation
- Approval workflow now includes explicit expiry and scheduled stale-request sweeping for manual A-share orders
- Audit log service now records core control-plane mutations and supports local JSON or local PostgreSQL storage
- A minimal event-driven backtesting baseline with turnover and market-specific trading cost / slippage modelling
- Local JSON-backed persistence for approvals, orders, portfolio state, and backtest experiments under `data/`
- Market-session service plus APScheduler-backed local background jobs with startup and shutdown lifecycle management
- Optional Futu adapter factory with graceful fallback to simulated adapters when the `futu` SDK or OpenD is unavailable
- Explicit Futu validation endpoint that reports quote/trade connectivity separately before you wire real execution
- Read-only broker probe endpoint plus cancel-order API so a simulated/OpenD order management loop can be exercised
- Read-only market-data smoke test endpoint that exercises quote and short-bar retrieval through the active adapter
- Local master-data and historical-data endpoints that seed instruments, persist bars, and export DuckDB/Parquet datasets
- History coverage endpoint and scheduled recent-history sync now expose how complete local bars are for tracked instruments
- History sync runs are now persisted locally with health/staleness summary and repair plans for missing windows
- History gap repair can now be triggered explicitly and is also scheduled as a daily repair sweep
- Data-quality summary now feeds operations readiness so missing local history becomes a visible operational blocker
- Read-only execution preview endpoint that converts current signals into risk-approved order intents without placing orders
- Execution gate endpoint now summarizes whether readiness, allocation, and rollout policy would block a guarded execution cycle
- Startup preflight endpoint and launcher summary that flag missing `.env`, invalid Futu config, and missing SDK before OpenD validation
- Diagnostics summary endpoint that classifies common validation failures and suggests the next operator action
- Research report endpoint that runs walk-forward validation, computes strategy correlations, and returns a portfolio admission summary
- Research stability endpoint now summarizes walk-forward pass rate, stability bucket, and capacity score per strategy
- Research recommendation endpoint now turns validation output into keep / paper-only / drop actions with operator next steps
- Research ideas endpoint now proposes the next experiment set from validation, turnover, drawdown, and correlation outcomes
- Research news summary endpoint now turns locally supplied headlines/articles into structured themes, impacted symbols, and next research actions
- Strategy selection review endpoints now persist which strategies are active, paper-only, or rejected for the next phase
- Strategy selection review is now also scheduled and reflected in readiness/report summaries
- Strategy allocation review now turns accepted strategies into target weights and market budgets for the next rebalance review
- Portfolio rebalance-plan endpoint now compares current weights versus target weights derived from active strategy allocations
- Scheduled research selection review now refreshes both admission decisions and strategy allocations for the next cycle
- Research experiments now prefer locally persisted history from DuckDB/Parquet or JSON caches before falling back to synthetic baseline data
- Strategy C now emits minimal protective-put / covered-call research signals while live execution remains limited to stock and ETF legs
- Historical backtests now incorporate local corporate-action adjustments, lightweight FX translation, and monthly portfolio ledger accounting
- Historical backtests now prefer locally persisted FX rates when available, with sync/query endpoints for the local FX dataset
- Historical backtests now include basic option-expiry settlement handling for expiry-month exercise / worthless-expiry scenarios
- Historical backtests now price trading costs by market and asset class instead of a single flat commission/slippage assumption
- Execution state now supports duplicate-fill deduplication, broker order reconciliation, and broker-vs-snapshot portfolio checks
- Order-state transitions are now enforced through an explicit state-machine component before reconciliation merges
- Execution quality summary now tracks stock/ETF slippage and option premium deviation against paper-trading thresholds
- Execution authorization summary now audits whether every order was risk-approved, approval-backed, or externally reconciled
- Manual fills and reconciled fills now update the local portfolio snapshot instead of leaving positions stale
- Manual fill reconciliation now also supports CSV-style broker export import for batch A-share backfill
- Risk engine now enforces daily option premium and total option risk budgets in addition to weight and cash constraints
- Alert evaluation now persists actionable incidents with recovery steps for broker health, validation failures, and reconciliation mismatches
- Runtime recovery can now rebuild market-data and broker adapters in place after degraded broker health or reconnect attempts
- Kill switch state is now persisted with an audit trail and can be verified against a full execution cycle
- Compliance checklists now persist A-share programmatic-trading gates and broker capability readiness inside the control panel
- Research experiments now record replay fingerprints and expose input/metric diffs for reproducibility checks
- Validation archives now include alerts, compliance status, and an operations readiness snapshot for long-run simulation evidence
- Daily operations journal entries now accumulate readiness evidence for multi-week paper-trading acceptance checks
- Operations acceptance summary now evaluates 4-week/6-week paper-trading evidence and suggests the next rollout stage
- Operations acceptance timeline and rollout milestones now expose day-by-day evidence and stage progress for 10% / 30% / 100% gating
- Go-live summary now combines execution gate, rollout evidence, milestones, and policy state into one promotion verdict
- Live-acceptance summary now combines go-live gate, execution quality, authorization, incidents, and promotion history into one deploy verdict
- Rollout promotion history is now persisted so blocked and approved stage-raise attempts remain auditable
- Validation archives and dashboard summaries now include live-acceptance status for Phase 4 review
- Rollout checklist now turns each target stage into an explicit pass/block checklist for operator review
- Rollout policy is now persisted separately from rollout recommendation and actively scales execution cash to 10% / 30% / 100%
- Operations execution metrics now summarize recent exception rate, risk-hit rate, slippage status, and authorization status for rollout review
- Daily report, weekly report, and postmortem endpoints now summarize alerts, recoveries, execution exceptions, and operator next actions
- Incident replay endpoint now emits a chronological alert/audit/recovery timeline for operator review and scenario walkthroughs
- Pytest coverage for risk rules, approval flow, and backtest cost behavior

## Universe Maintenance

The persistent research universe now lives in `data/instruments.json` (or DuckDB when enabled) and is managed through the API instead of hard-coded strategy samples.

Typical workflow:

```bash
curl -X POST http://127.0.0.1:8000/data/instruments \
  -H 'Content-Type: application/json' \
  -d '{
    "instruments": [
      {
        "symbol": "IVV",
        "market": "US",
        "asset_class": "etf",
        "currency": "USD",
        "name": "iShares Core S&P 500 ETF",
        "enabled": true,
        "tradable": true,
        "liquidity_bucket": "high",
        "avg_daily_dollar_volume_m": 6200
      }
    ]
  }'
curl "http://127.0.0.1:8000/data/instruments?enabled_only=true&tradable_only=true&liquid_only=true"
```

Operator notes:
- Keep `enabled=true` and `tradable=true` only for symbols you really want in the research/execution candidate pool.
- Use `liquidity_bucket=low` or `enabled=false` to keep a symbol persisted but out of the default personal-trading universe.
- After a universe change, run `POST /data/history/sync` for the affected symbols and then verify `GET /data/history/coverage`.

## Absorbed Research Capabilities

A research-only capability layer absorbed from `hsliuping/TradingAgents-CN`
across rounds 01–15 ships in this repo: A-share data adapters (AKShare /
BaoStock / Tushare), Chinese news sources (East Money / 财联社 / Finnhub /
Alpha Vantage), CN hard risk rules (涨跌停 / T+1 / ST), technical features,
universe screener, and a budget-gated LLM advisory layer. **Every piece is
off by default and never produces signals/orders/approvals.** See
[`docs/ABSORB_CAPABILITIES.md`](docs/ABSORB_CAPABILITIES.md) for the
operator cookbook (env knobs, optional deps, how to verify).

Smoke run:

```bash
.venv/bin/python scripts/absorb_dogfood.py
# audits env knobs, then runs an offline end-to-end pipeline with a fake
# LLM and writes a Markdown report to data/reports/dogfood/
```

## Current Architecture Boundaries

- `tradingcat/routes/` stays thin. Route handlers should delegate to `app.py` properties, facades, or dedicated services instead of composing research/reporting logic inline.
- `tradingcat/facades.py` is for transport-facing read models. Dashboard and research facades should assemble response payloads from query/projection/reporting services, not reach directly into heavy orchestration code.
- `tradingcat/services/query_services.py` owns read-side aggregation such as readiness, data quality, and research query composition.
- `tradingcat/services/portfolio_projections.py` owns account-position/cash/nav-curve/allocation projection helpers shared by dashboard surfaces.
- `tradingcat/services/strategy_reporting.py` owns research report, stability, recommendation, scorecard, and strategy-detail assembly. `StrategyAnalysisService` remains the lower-level analysis core for experiment, correlation, benchmark, and history helpers.
- `tradingcat/strategies/simple.py` now holds production strategy implementations plus shared metadata/helpers. Research-only candidate strategies live in `tradingcat/strategies/research_candidates.py`.
- `sample_instruments()` is still available for fallback/diagnostic paths, but the persistent instrument catalog is the default source of truth for research and strategy detail flows.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
pytest
./scripts/bootstrap_env.sh disabled
./scripts/run_local.sh
```

Then open:

```bash
http://127.0.0.1:8000/dashboard
```

The GUI prototype now focuses on:
- total assets, cash, position allocation, and portfolio pnl
- strategy metrics such as annualized return, Sharpe, and max drawdown
- today's trading plan from execution preview
- daily / weekly highlights and current blockers

## Current Architecture Map

- `tradingcat/main.py` stays as the thin FastAPI entry point; router registration and error wiring still happen there.
- Runtime construction and broker/data recovery now live in `tradingcat/runtime.py`, while APScheduler job registration lives in `tradingcat/scheduler_runtime.py`.
- `tradingcat/app.py` remains the main application shell, but dashboard / research / operations / journal / alerts orchestration is now routed through facade objects in `tradingcat/facades.py`.
- Server-rendered pages use shared Jinja layout pieces from `templates/base.html` and `templates/partials/`, rather than returning raw HTML strings from route handlers.
- The dashboard frontend stays framework-free, but the page logic is now split by concern:
  - `static/dashboard_accounts.js` for account tabs, overview, and account asset helpers
  - `static/dashboard_strategy.js` for strategy / candidate / trading-plan rendering
  - `static/dashboard_operations.js` for summaries, blockers, priority actions, and live ops tables
  - `static/dashboard.js` as the orchestration shell that owns shared state and API loading

## Continue From Here

- If you are resuming refactor work, read `PLAN.json` and `PROGRESS.md` first; they are the authoritative harness state for remaining tasks and prior decisions.
- Preserve the current public HTTP surface while refactoring internals; route compatibility and dashboard response compatibility are guarded by `tests/test_api.py`.
- Prefer `.venv/bin/pytest` for local validation in this repo; using the system interpreter can produce false negatives around optional data dependencies.

To prepare Futu integration later:

```bash
source .venv/bin/activate
pip install -e .[dev,futu]
```

To move local state into PostgreSQL on the same machine:

```bash
source .venv/bin/activate
pip install -e .
./scripts/bootstrap_env.sh simulate
# edit .env:
# TRADINGCAT_POSTGRES_ENABLED=true
# TRADINGCAT_POSTGRES_DSN=postgresql:///tradingcat
./scripts/init_postgres.sh
```

To persist research experiments into local DuckDB + Parquet:

```bash
# edit .env:
# TRADINGCAT_DUCKDB_ENABLED=true
# TRADINGCAT_DUCKDB_PATH=data/research.duckdb
# TRADINGCAT_PARQUET_DIR=data/parquet
# TRADINGCAT_SCHEDULER_BACKEND=apscheduler
# TRADINGCAT_SCHEDULER_AUTOSTART=true
```

## Local Validation Flow

```bash
./scripts/bootstrap_env.sh simulate
# edit .env and set TRADINGCAT_FUTU_ENABLED=true after OpenD is running
# set TRADINGCAT_RELOAD=true only if your environment allows file watching
./scripts/run_local.sh
```

In another terminal:

```bash
./scripts/checklist.sh
./scripts/opend_check.sh
./scripts/doctor.sh
./scripts/validate_broker.sh
./scripts/validate_all.sh
./scripts/post_validate.sh
./scripts/simulated_order_cycle.sh
```

To archive validation runs under `data/reports/<timestamp>/`:

```bash
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/doctor.sh
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_broker.sh
TRADINGCAT_ARCHIVE_REPORTS=true ./scripts/validate_all.sh
```

To run the full flow in one command:

```bash
./scripts/opend_check.sh
./scripts/validate_all.sh
./scripts/validate_all.sh http://127.0.0.1:8000 with-cycle
./scripts/post_validate.sh
```

`./scripts/post_validate.sh` now runs the full local operator loop:

- validation summary
- broker order smoke check
- cancel currently open simulated/live orders
- execute one live cycle
- auto-approve the newest pending A-share request
- reconcile one manual fill
- archive the full result set under `data/reports/<timestamp>/`

To inspect archived runs:

```bash
./scripts/latest_report.sh
./scripts/compare_reports.sh 20260307-173723 20260307-173727
./scripts/report_markdown.sh latest
./scripts/cleanup_reports.sh 10
curl http://127.0.0.1:8000/reports/latest
curl http://127.0.0.1:8000/reports/latest/dashboard
```

`./scripts/validate_broker.sh` starts with `GET /diagnostics/summary`, which aggregates the likely failure category:

- `futu_disabled`: `.env` still uses simulated mode.
- `sdk_missing`: the `futu` package is not installed in `.venv`.
- `opend_unreachable`: both quote and trade validation failed, usually because OpenD is down or not logged in.
- `quote_channel_failed`: quote connectivity or market data permissions failed.
- `trade_channel_failed`: trade connectivity, unlock, or account environment failed.
- `market_data_mapping_failed`: connection exists, but quote/bar parsing still failed.
- `risk_or_preview_failed`: strategy or risk preview failed before execution.
- `ready_for_validation`: read-only checks passed and the next step is simulated order placement/cancellation.

`./scripts/doctor.sh` prints a compact summary and exits with:

- `0` for `info`
- `1` for `warning`
- `2` for `error`

## Notes

- This is a baseline implementation, not a production trading engine.
- Futu OpenD is still an external dependency; local PostgreSQL, DuckDB/Parquet, and APScheduler are now wired behind configuration.
- A-share execution remains manual by design in V1.
- Runtime state and audit logs can now move into local PostgreSQL, while research experiments can move into local DuckDB + Parquet.
- Futu integration is currently an adapter layer with fallback behavior; real trading still depends on local OpenD availability, account permissions, and final field validation against the live SDK responses.
- `AppConfig` now supports environment-driven startup, including `TRADINGCAT_FUTU_*`, local PostgreSQL, DuckDB/Parquet, and scheduler backend settings.

# TradingCat — Handoff to Codex

**Date**: 2026-03-18
**Branch**: `claude/determined-ritchie` (worktree of `main`)
**Situation**: The original commit (`263283f`) contained systematically corrupted files — large sections of code were duplicated 15–30× by an AI generation artifact, inflating files from their intended size to 25× that size.

---

## What Was Fixed (This Session)

| File | Original | Fixed | Status |
|------|----------|-------|--------|
| `tradingcat/main.py` | 24 985 L (corrupted) | 2 188 L | ✅ Syntax OK, needs runtime test |
| `tradingcat/services/operations.py` | 1 920 L (15× dup) | 248 L | ✅ Syntax OK |
| `tradingcat/services/trading_journal.py` | 1 740 L (30× dup) | 58 L | ✅ Syntax OK |
| `tests/test_api.py` | 7 621 L (corrupted) | 257 L | ✅ Syntax OK |

**Still broken** (see below): `tradingcat/domain/models.py`

---

## Critical Blocker: `tradingcat/domain/models.py`

### Current State
The file is 1 845 lines but contains **only 5 model classes** (each repeated ~30×) and **no imports**:
- `OperationsJournalEntry`
- `DailyTradingPlanNote`
- `DailyTradingSummaryNote`
- `StrategySelectionRecord`
- `StrategyAllocationRecord`

**35 models are completely missing** — referenced by all services but not defined anywhere.

### Required: Rebuild `tradingcat/domain/models.py` from scratch

The file needs:

#### 1. Imports
```python
from __future__ import annotations

from datetime import UTC, date, datetime
from enum import Enum
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field
```

#### 2. Enums

```python
class AssetClass(str, Enum):
    STOCK = "stock"
    ETF = "etf"
    OPTION = "option"
    CRYPTO = "crypto"
    BOND = "bond"
    CASH = "cash"

class Market(str, Enum):
    US = "US"
    HK = "HK"
    CN = "CN"

class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(str, Enum):
    SUBMITTED = "submitted"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"
    PENDING_APPROVAL = "pending_approval"
    EXPIRED = "expired"

class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
```

#### 3. Core Domain Models

Infer fields from service files. Key usages observed:

**`Instrument`** — used in `adapters/base.py`, `services/market_data.py`, `strategies/simple.py`:
```python
# instrument.symbol, instrument.market (Market), instrument.asset_class (AssetClass)
# instrument.currency (str), instrument.name (str), instrument.lot_size (float)
# OptionContract extends Instrument: strike, expiry, option_type ("call"/"put"), underlying_symbol
```

**`Bar`** — used in `adapters/base.py`, `services/market_data.py`:
```python
# bar.symbol, bar.date, bar.open, bar.high, bar.low, bar.close, bar.volume
```

**`FxRate`** — used in market_data:
```python
# base_currency, quote_currency, date, rate (float)
```

**`CorporateAction`** — returned by `fetch_corporate_actions`:
```python
# symbol, date, action_type (str), factor (float), notes (str | None)
```

**`Signal`** — used in `services/risk.py`, `strategies/`:
```python
# signal.id, signal.instrument (Instrument), signal.target_weight (float)
# signal.side (OrderSide), signal.reason (str | None), signal.as_of (date)
# signal.strategy_id (str | None), signal.market (Market via instrument)
```

**`OrderIntent`** — created by RiskEngine:
```python
# intent.id, intent.signal_id, intent.instrument (Instrument)
# intent.side (OrderSide), intent.quantity (float), intent.requires_approval (bool)
# intent.notes (str | None), intent.created_at (datetime)
```

**`ExecutionReport`** — created by BrokerAdapters:
```python
# report.id, report.order_intent_id, report.broker_order_id
# report.status (OrderStatus), report.message (str | None)
# report.filled_quantity (float = 0.0), report.fill_price (float | None)
# report.timestamp (datetime), report.market (Market | None)
```

**`Position`** — returned by broker:
```python
# position.symbol, position.quantity (float), position.market (Market)
# position.average_cost (float | None), position.current_price (float | None)
# position.market_value (float | None)
```

**`PortfolioSnapshot`** — used in `services/portfolio.py`:
```python
# snapshot.id, snapshot.as_of (date), snapshot.recorded_at (datetime)
# snapshot.nav (float), snapshot.cash (float), snapshot.cash_by_market (dict[str, float])
# snapshot.positions (list[Position | dict])
# snapshot.daily_pnl (float = 0.0), snapshot.weekly_pnl (float = 0.0)
# snapshot.drawdown (float = 0.0), snapshot.base_currency (str = "CNY")
```

**`ManualFill`** — used in execution reconciliation:
```python
# fill.order_intent_id, fill.broker_order_id, fill.symbol
# fill.side (OrderSide), fill.quantity (float), fill.fill_price (float)
# fill.filled_at (datetime), fill.market (Market | None), fill.notes (str | None)
```

**`ApprovalRequest`** — used in `services/approval.py`:
```python
# request.id, request.order_intent_id, request.instrument (Instrument)
# request.side (OrderSide), request.quantity (float), request.status (ApprovalStatus)
# request.reason (str | None), request.decision_reason (str | None)
# request.created_at (datetime), request.decided_at (datetime | None)
# request.expires_at (datetime | None)
```

**`KillSwitchEvent`** — used in `services/risk.py`:
```python
# event.id, event.enabled (bool), event.reason (str | None), event.changed_at (datetime)
```

**`AuditLogEntry`** — used in `services/audit.py`:
```python
# entry.id, entry.recorded_at (datetime), entry.category (str)
# entry.action (str), entry.status (str = "ok"), entry.details (dict = {})
```

**`AlertEvent`** — used in `services/alerts.py`:
```python
# alert.id, alert.category (str), alert.message (str)
# alert.severity (str = "info"), alert.triggered_at (datetime), alert.resolved (bool = False)
```

**`ComplianceChecklist`** and **`ChecklistItem`** — used in `services/compliance.py`:
```python
# checklist.id, checklist.as_of (date), checklist.created_at (datetime)
# checklist.items (list[ChecklistItem]), checklist.all_passed (bool)
# item.label (str), item.passed (bool), item.notes (str | None)
```

**`HistorySyncRun`** — used in `services/data_sync.py`:
```python
# run.id, run.started_at (datetime), run.completed_at (datetime | None)
# run.symbols (list[str]), run.status (str), run.fetched_count (int = 0)
# run.error (str | None)
```

**`RolloutPolicy`** — used in `services/rollout.py`:
```python
# policy.id, policy.stage (str), policy.enabled (bool = False)
# policy.created_at (datetime), policy.notes (str | None)
```

**`RolloutPromotionAttempt`** — used in `services/rollout.py`:
```python
# attempt.id, attempt.from_stage (str), attempt.to_stage (str)
# attempt.promoted_at (datetime), attempt.reason (str | None), attempt.success (bool)
```

**`RecoveryAttempt`** — used in `services/operations.py`:
```python
# attempt.id, attempt.triggered_at (datetime), attempt.trigger (str)
# attempt.retries (int), attempt.before_healthy (bool), attempt.after_healthy (bool)
# attempt.changed (bool), attempt.detail (str), attempt.before_backend (str), attempt.after_backend (str)
```

**`MarketSession`** — used in `services/market_calendar.py`:
```python
# session.market (Market), session.is_open (bool)
# session.open_time (str | None), session.close_time (str | None), session.notes (str | None)
```

**`SchedulerJob`** and **`SchedulerRunResult`** — used in `services/scheduler.py`:
```python
# job.id, job.name (str), job.description (str), job.timezone (str)
# job.local_time (str), job.market (Market), job.last_run (datetime | None), job.next_run (datetime | None)
# result.job_id, result.status (str), result.message (str | None), result.ran_at (datetime)
```

**`ReconciliationSummary`** and **`PortfolioReconciliationSummary`** — used in execution/portfolio services:
```python
# ReconciliationSummary: applied_fill_order_ids (list[str]), skipped_count (int), error_count (int)
# PortfolioReconciliationSummary: positions_matched (int), positions_drifted (int), drift_details (list[dict])
```

**`BacktestExperiment`**, **`BacktestLedgerEntry`**, **`BacktestMetrics`** — used in research:
```python
# BacktestExperiment: id, strategy_id, run_at, start_date, end_date, metrics (BacktestMetrics), ledger (list[BacktestLedgerEntry])
# BacktestMetrics: total_return, annualized_return, sharpe_ratio, max_drawdown, win_rate, calmar_ratio
# BacktestLedgerEntry: date, nav, daily_return, signal_count
```

#### 4. Models Already Present (Keep As-Is)
These 5 classes are in the current file and correct — include them:
- `OperationsJournalEntry`
- `DailyTradingPlanNote`
- `DailyTradingSummaryNote`
- `StrategySelectionRecord`
- `StrategyAllocationRecord`

---

## Files That Need Completion/Review

### `tradingcat/main.py` (reconstructed but incomplete)
The reconstruction was done by an AI agent — it likely covers the route structure but may have placeholder method bodies in `TradingCatApplication`. Run `pytest tests/test_api.py -x` after fixing models.py to see what's wrong.

Key routes that must exist (52 unique):
- `/signals/today`, `/portfolio`, `/orders`, `/kill-switch`
- `/approvals/{id}/approve|reject|expire`, `/approvals/expire-stale`
- `/execution/reconcile`, `/execution/preview`, `/execution/run`
- `/dashboard` (HTML), `/dashboard/summary`, `/dashboard/strategies/{id}`, etc.
- `/market-sessions`, `/scheduler/jobs`, `/scheduler/jobs/{id}/run`
- `/broker/probe`, `/broker/recover`, `/broker/recovery-attempts`, `/broker/recovery-summary`
- `/market-data/smoke-test`, `/data/instruments`, `/data/history/*`, `/data/fx/*`, `/data/quality`
- `/research/*`, `/ops/*`, `/journal/*`, `/reports/*`
- `/portfolio/risk-state`, `/portfolio/rebalance-plan`
- `/rollout/*`, `/compliance/checklist`, `/preflight`
- `/reconcile/manual-fill`, `/reconcile/manual-fills/import`

### `tradingcat/services/operations.py` (reconstructed)
Currently 248 lines with `OperationsJournalService` and `RecoveryService`. Verify against `tests/test_operations_journal.py` and `tests/test_runtime_recovery.py`.

### `tradingcat/services/trading_journal.py` (fixed to 58 lines)
Only has `TradingJournalService` skeleton. Check against `tests/test_reports_helper.py` and `tests/test_research_reporting.py` for the full required API.

### `tests/test_api.py` (reconstructed)
Was rebuilt with 10 test functions. Compare with what was originally needed by looking at the route list above.

---

## How to Run the Project

```bash
# From project root:
source .venv/bin/activate
uvicorn tradingcat.main:app --host 0.0.0.0 --port 8000 --reload
```

Or from the worktree:
```bash
cd /Users/miau/Documents/TradingCat/.claude/worktrees/determined-ritchie
/Users/miau/Documents/TradingCat/.venv/bin/uvicorn tradingcat.main:app --host 0.0.0.0 --port 8000
```

Config via `.env` file (optional):
```
TRADINGCAT_PORTFOLIO_VALUE=1000000
TRADINGCAT_BASE_CURRENCY=CNY
TRADINGCAT_SCHEDULER_AUTOSTART=false   # Disable for dev
TRADINGCAT_FUTU_ENABLED=false
TRADINGCAT_POSTGRES_ENABLED=false
TRADINGCAT_DUCKDB_ENABLED=false
```

---

## Test Suite

```bash
cd /Users/miau/Documents/TradingCat/.claude/worktrees/determined-ritchie
/Users/miau/Documents/TradingCat/.venv/bin/pytest tests/ -x -v 2>&1 | head -60
```

Most tests should pass once `domain/models.py` is rebuilt. Start with:
```bash
pytest tests/test_risk.py tests/test_backtest.py tests/test_config.py -v
```

---

## Priority Order for Codex

1. **Rebuild `tradingcat/domain/models.py`** — everything else depends on this
2. **Test** with `pytest tests/test_risk.py tests/test_backtest.py -v`
3. **Boot the server**: `uvicorn tradingcat.main:app --port 8000`
4. **Run full test suite**: `pytest tests/ -x -v`
5. **Fix `main.py`** if routes or `TradingCatApplication` methods are missing/incomplete
6. **Fix `operations.py` and `trading_journal.py`** if tests fail

---

## Project Context

- **Stack**: Python 3.12, FastAPI, Pydantic v2, APScheduler, DuckDB, PostgreSQL (optional), Futu OpenD (optional broker)
- **Purpose**: Personal automated trading system for HK/US/CN stocks and ETFs
- **Broker**: Futu/Moomoo (simulated by default, real via `TRADINGCAT_FUTU_ENABLED=true`)
- **Markets**: US, HK, CN (CN = manual execution only)
- **Risk limits**: max stock weight 8%, ETF 20%, daily stop-loss 2%, weekly 4%
- **Architecture**: `adapters/` → `services/` → `main.py` (FastAPI app + `TradingCatApplication` orchestrator)
- **Data storage**: JSON files under `data/` (default), PostgreSQL for state (optional), DuckDB for research (optional)

See `PLAN.md` for full project specification.

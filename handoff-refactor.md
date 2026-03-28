# TradingCat Refactor Handoff

## Background

TradingCat is a Python trading system built on FastAPI + Pydantic. The layered architecture (Domain → Adapters → Services → Repositories) is sound, but execution-level debt has accumulated and is getting worse with each feature addition. `main.py` has grown from 2004 to **2254 lines**, new features (Smart Order, AlphaRadar, MacroCalendar, Algo Execution, Manual Order, TCA) were added without any structural cleanup, and existing bad patterns (silent exceptions, magic numbers, sync I/O) were replicated in the new code.

**Constraint**: Preserve all existing behavior. Every existing test must continue to pass. No feature additions — pure structural improvement.

---

## Phase 0: Critical Fixes (Priority: URGENT — before any refactoring)

### Task 0.1: Remove "NUCLEAR FIX" portfolio history overwrite

**File**: `tradingcat/services/portfolio.py`

`PortfolioService.__init__()` contains a block labeled "PHASE 4 NUCLEAR FIX" that silently overwrites real portfolio history with synthetic random data if it detects the history looks "flat" (< 30 days or all same NAV). This is a **data integrity risk** — a real portfolio with 0 PnL gets its history destroyed.

**Action**:
- Remove the force-generation block entirely
- If synthetic seed data is needed for demo/dev, gate it behind an explicit config flag (e.g., `TRADINGCAT_SEED_DEMO_DATA=true`) and log a warning when it runs
- Never overwrite existing non-empty history

### Task 0.2: Fix manual order approval bypass

**File**: `tradingcat/main.py` — `POST /orders/manual` endpoint (line ~1551)

Manual orders hardcode `requires_approval=False`, bypassing the approval workflow that exists for all other order paths. This is a risk control gap.

**Action**:
- Remove the hardcoded `requires_approval=False`
- Route manual orders through the same approval logic as signal-generated orders (i.e., A-share orders require approval, others follow broker config)
- Or at minimum, make it configurable: `TRADINGCAT_MANUAL_ORDER_REQUIRES_APPROVAL=true`

### Task 0.3: Fix duplicate `RiskUpdatePayload` class

**File**: `tradingcat/main.py` — lines 207 and 1708

`RiskUpdatePayload` is defined twice in the same file. Remove the duplicate at line 1708.

---

## Phase 1: Split `main.py` (Priority: Highest)

**Problem**: `tradingcat/main.py` is **2254 lines** containing `TradingCatApplication` class, **18 Pydantic payload models**, 3 exception handlers, and **~110 route handlers**. It is the single biggest maintainability blocker and growing with every feature.

### Task 1.1: Extract `TradingCatApplication` → `tradingcat/app.py`

- Move `class TradingCatApplication` (line ~232) to `tradingcat/app.py`
- Move the `lifespan` async context manager with it
- `main.py` imports `TradingCatApplication` from `app.py`
- Keep `app_state` as a module-level variable in `main.py` (or wherever the FastAPI `app` is created)

### Task 1.2: Extract payload models → `tradingcat/api/schemas.py`

Move **all** payload classes out of `main.py`:
- `DecisionPayload` (line 138)
- `ChecklistItemPayload` (line 142)
- `RiskStatePayload` (line 147)
- `MarketDataSmokePayload` (line 153)
- `HistorySyncPayload` (line 159)
- `HistoryRepairPayload` (line 166)
- `FxSyncPayload` (line 170)
- `ResearchNewsItemPayload` (line 177)
- `ResearchNewsSummaryPayload` (line 183)
- `ManualFillImportPayload` (line 187)
- `ExecutionPreviewPayload` (line 192)
- `ManualOrderPayload` (line 196) — **NEW**
- `RiskUpdatePayload` (line 207) — **NEW** (keep only one copy, delete the duplicate at line 1708)
- `ExecutionRunPayload` (line 214)
- `RebalancePlanPayload` (line 219)
- `RolloutPolicyPayload` (line 223)
- `AssetCorrelationPayload` (line 227) — **NEW**

### Task 1.3: Split routes into `tradingcat/routes/` modules

Create `tradingcat/routes/__init__.py` and these modules, each containing an `APIRouter`:

| File | Prefix | Routes to move |
|------|--------|---------------|
| `routes/signals.py` | `/signals` | `/signals/today` |
| `routes/dashboard.py` | `/dashboard` | `/dashboard`, `/dashboard/summary`, `/dashboard/strategies/...`, `/dashboard/accounts/...`, `/dashboard/research`, `/dashboard/journal`, `/dashboard/operations` |
| `routes/portfolio.py` | `/portfolio` | `/portfolio`, `/portfolio/risk-state`, `/portfolio/reconcile`, `/portfolio/rebalance-plan` |
| `routes/orders.py` | `/orders` | `/orders`, `/orders/{id}/cancel`, `/orders/cancel-open`, **`/orders/manual`**, **`/orders/triggers` (GET/POST)** |
| `routes/execution.py` | `/execution` | `/execution/reconcile`, `/execution/quality`, `/execution/authorization`, `/execution/preview`, `/execution/run`, `/execution/gate` |
| `routes/approvals.py` | `/approvals` | `/approvals`, `/approvals/{id}/approve`, `/approvals/{id}/reject`, `/approvals/{id}/expire`, `/approvals/expire-stale` |
| `routes/kill_switch.py` | `/kill-switch` | `/kill-switch` (GET/POST), `/kill-switch/verify` |
| `routes/reconcile.py` | `/reconcile` | `/reconcile/manual-fill`, `/reconcile/manual-fills/import` |
| `routes/journal.py` | `/journal` | `/journal/plans/...`, `/journal/summaries/...` |
| `routes/broker.py` | `/broker` | `/broker/status`, `/broker/probe`, `/broker/recover`, `/broker/recovery-attempts`, `/broker/recovery-summary`, `/broker/validate` |
| `routes/market_data.py` | — | `/market-data/smoke-test`, `/data/instruments`, `/data/history/...`, `/data/fx/...`, `/data/quality`, `/market-sessions` |
| `routes/scheduler.py` | `/scheduler` | `/scheduler/jobs`, `/scheduler/jobs/{id}/run` |
| `routes/alerts.py` | `/alerts` | `/alerts`, `/alerts/summary`, `/alerts/evaluate` |
| `routes/audit.py` | `/audit` | `/audit/events`, `/audit/logs`, `/audit/summary` |
| `routes/compliance.py` | `/compliance` | `/compliance/checklist`, `/compliance/checklists/...` |
| `routes/ops.py` | `/ops` | All `/ops/...` routes (~25 endpoints), including **`/ops/evaluate-triggers`**, **`/ops/risk/config` (GET/POST)**, **`/ops/tca`** |
| `routes/research.py` | `/research` | All `/research/...` routes (~18 endpoints), including **`/research/alpha-radar`**, **`/research/macro-calendar`**, **`/research/correlation`** |
| `routes/reports.py` | `/reports` | `/reports/latest`, `/reports/latest/dashboard`, `/reports/{ref}/...` |
| `routes/preflight.py` | — | `/preflight`, `/preflight/startup`, `/diagnostics/summary` |

**Pattern for each route module:**
```python
from fastapi import APIRouter, Request
router = APIRouter()

def _get_app(request: Request):
    return request.app.state.app_state  # or however app_state is exposed

@router.get("/signals/today")
async def signals_today(request: Request):
    app = _get_app(request)
    # ... existing handler body ...
```

**In `main.py` after split:**
```python
from tradingcat.routes import signals, dashboard, portfolio, ...
app.include_router(signals.router)
app.include_router(dashboard.router)
# etc.
```

`main.py` should shrink to ~50 lines: app creation, static mount, router includes, exception handlers.

### Task 1.4: Move exception handlers → `tradingcat/api/error_handlers.py`

Move `_risk_violation_handler`, `_value_error_handler`, `_generic_error_handler` (lines ~1368–1385) to a separate module. Register them in `main.py` via a `register_error_handlers(app)` function.

---

## Phase 2: Split Bloated Services (Priority: High)

### Task 2.1: Split `ResearchService` (1201 lines)

Current file: `tradingcat/services/research.py`

Split into:
- `tradingcat/services/research.py` — keep backtest orchestration, experiment storage (core)
- `tradingcat/services/strategy_analysis.py` — extract: correlation analysis (including the new `calculate_asset_correlation()`), stability scoring, strategy recommendations, scorecard generation
- `tradingcat/services/research_ideas.py` — extract: idea generation, news summarization

Each new service receives the dependencies it needs via constructor injection (same pattern as existing services).

### Task 2.2: Split `ExecutionService` (379 lines)

Current file: `tradingcat/services/execution.py`

This one is less urgent (379 lines is manageable), but the concerns are distinct:
- Keep order submission and approval routing in `ExecutionService`
- Extract fill reconciliation + deduplication + TCA slippage calculation into `tradingcat/services/reconciliation.py`

### Task 2.3: Wire new services in `TradingCatApplication`

After splitting, update `TradingCatApplication` (now in `app.py`) to instantiate the new services and inject them where needed. Route handlers that called `app.research.some_method()` should now call the appropriate new service.

### Task 2.4: Review newly added services for consistency

The following new services were added recently. They are small and focused (good), but need cleanup:
- `tradingcat/services/alpha_radar.py` (84 lines) — has silent `except Exception` on line 22
- `tradingcat/services/macro_calendar.py` (56 lines) — purely hardcoded fixtures, mark with `# TODO: connect to real data source`
- `tradingcat/services/rule_engine.py` (128 lines) — has silent `except Exception` on lines 22 and 118; RSI/SMA always return mock values, mark with `# TODO: connect to real indicator calculations`

---

## Phase 3: Error Handling Cleanup (Priority: High)

### Task 3.1: Eliminate silent exception swallowing

There are **29 instances** of `except Exception` across the codebase. Search all files under `tradingcat/` for this pattern:

```python
except Exception:
    return <default value>
# or
except Exception:
    pass
```

Replace with:
```python
except Exception:
    logger.exception("descriptive message about what failed and context")
    return <default value>
```

Every module should have `logger = logging.getLogger(__name__)` at the top.

**Complete list of files to fix** (sorted by severity):

| File | Instances | Notes |
|------|-----------|-------|
| `main.py` | 8 | Lines 488, 496, 540, 701, 716, 724, 770, 774, 1470, 2035 |
| `services/rule_engine.py` | 2 | Lines 22, 118 — `except Exception: return {}` and `except Exception: pass` |
| `services/alpha_radar.py` | 1 | Line 22 — `except Exception: prices = {defaults}` |
| `services/research.py` | 2 | Lines 45, 682 |
| `services/execution.py` | 1 | Line 167 |
| `services/market_data.py` | 1 | Line 72 |
| `services/preflight.py` | 3 | Lines 40, 87, 144 — these log `exc`, which is acceptable |
| `adapters/factory.py` | 4 | Lines 83, 136, 174, 190 |
| `adapters/yfinance_adapter.py` | 2 | Lines 95, 121 |
| `adapters/futu.py` | 1 | Line 34 |

`services/preflight.py` already logs the exception — these are OK. Focus on the rest.

### Task 3.2: Add structured logging

Ensure every service module uses Python `logging`. Key places:
- `services/market_data.py` — log when quote fetch fails and why
- `services/execution.py` — log order submission failures with order details
- `services/rule_engine.py` — log when trigger evaluation fails
- `services/alpha_radar.py` — log when market data fetch fails
- `adapters/factory.py` — log adapter fallback decisions
- `adapters/futu.py` — log connection failures

Do NOT add logging to hot paths that run per-tick. Only log errors, warnings, and significant state transitions.

---

## Phase 4: Extract Magic Numbers to Config (Priority: Medium)

### Task 4.1: Move hardcoded values to `AppConfig`

File: `tradingcat/config.py`

Add fields to the appropriate config classes:

```python
class RiskConfig(BaseModel):
    # existing fields...
    fallback_price_us_etf: float = 600.0
    fallback_price_us_stock: float = 300.0
    fallback_price_cn_etf: float = 5.0
    fallback_price_cn_stock: float = 20.0

class FutuConfig(BaseModel):
    # existing fields...
    probe_timeout_seconds: float = 0.2
    adapter_init_timeout_seconds: float = 3.0

class AppConfig(BaseModel):
    # existing fields...
    approval_expiry_minutes: int = 60
    seed_demo_data: bool = False  # NEW: gates synthetic portfolio data generation
    manual_order_requires_approval: bool = True  # NEW: gates manual order approval bypass
```

**New magic numbers to extract** (from recently added code):
- Broker adapter: TWAP/VWAP slice count (hardcoded 5) → `AppConfig.algo_twap_slices: int = 5`
- Broker adapter: LADDER step calculation → configurable
- AlphaRadar: hardcoded symbol list `["SPY", "QQQ", ...]` → `AppConfig.alpha_radar_symbols: list[str]`
- Portfolio mock: `random.uniform(-0.02, 0.025)`, `120` days, `0.1` cash ratio → move to config (gated by `seed_demo_data`)

Then update the code that uses these hardcoded values to read from config instead.

### Task 4.2: Add Pydantic validators

In `config.py`, add basic validators:
```python
@field_validator('portfolio_value')
@classmethod
def positive_portfolio(cls, v):
    if v <= 0:
        raise ValueError('portfolio_value must be positive')
    return v
```

Add similar validators for: `futu.port` (1–65535), risk thresholds (non-negative), `algo_twap_slices` (> 0).

---

## Phase 5: Async I/O for Market Data (Priority: Medium)

### Task 5.1: Make MarketDataService async-capable

File: `tradingcat/services/market_data.py`

Convert `fetch_bars()` and `fetch_quotes()` to use `asyncio.to_thread()` wrapping the synchronous adapter calls:

```python
async def fetch_quotes_async(self, symbols: list[str]) -> dict[str, float]:
    return await asyncio.to_thread(self.fetch_quotes, symbols)
```

Add async variants alongside existing sync methods (don't break sync callers like the backtest engine).

### Task 5.2: Update I/O-bound route handlers

In the route modules created in Phase 1, update handlers that call `fetch_quotes` / `fetch_bars` to `await` the async variants. This includes the new endpoints:
- `/research/alpha-radar` (calls `fetch_quotes` via AlphaRadarService)
- `/research/correlation` (calls market data for daily returns)
- `/ops/evaluate-triggers` (calls `fetch_quotes` for trigger evaluation)

---

## Verification

After each phase:

1. Run `pytest` — all existing tests must pass
2. Run `python -c "from tradingcat.main import app; print('OK')"` — import succeeds
3. Run `uvicorn tradingcat.main:app --host 0.0.0.0 --port 8000` — server starts, hit `/preflight` and `/dashboard/summary` to verify
4. `grep -rn "except Exception" tradingcat/` — after Phase 3, every match should have a `logger` call nearby
5. After Phase 0: verify `/orders/manual` respects approval workflow; verify portfolio history is not overwritten on startup

---

## Files Reference

| File | Lines | Role |
|------|-------|------|
| `tradingcat/main.py` | 2254 | God file to split (Phase 0 + 1) |
| `tradingcat/services/research.py` | 1201 | Largest service to split (Phase 2) |
| `tradingcat/services/execution.py` | 379 | Secondary split target (Phase 2) |
| `tradingcat/services/reporting.py` | 465 | Review for split if time permits |
| `tradingcat/services/portfolio.py` | 155 | Critical fix: remove NUCLEAR FIX (Phase 0) |
| `tradingcat/services/alpha_radar.py` | 84 | Error handling cleanup (Phase 2–3) |
| `tradingcat/services/macro_calendar.py` | 56 | Mark TODOs for real data (Phase 2) |
| `tradingcat/services/rule_engine.py` | 128 | Error handling + mock indicators (Phase 2–3) |
| `tradingcat/domain/triggers.py` | 25 | SmartOrder / TriggerCondition models |
| `tradingcat/config.py` | ~150 | Config enhancement (Phase 4) |
| `tradingcat/services/market_data.py` | ~300 | Async conversion (Phase 5) |
| `tradingcat/adapters/factory.py` | ~200 | Logging + config (Phase 3–4) |
| `tradingcat/adapters/broker.py` | — | Algo execution magic numbers (Phase 4) |
| `tests/test_api.py` | — | Must pass after every phase |

## Out of Scope

- Frontend rewrite (separate effort)
- New features or strategy logic changes
- Database migration tooling (Alembic)
- Circuit breaker / retry patterns (future phase)
- Performance optimization
- Connecting mock services (AlphaRadar, MacroCalendar, RuleEngine indicators) to real data sources

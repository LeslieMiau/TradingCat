# TradingCat Refactor Handoff

## Background

TradingCat is a Python trading system built on FastAPI + Pydantic. The layered architecture (Domain → Adapters → Services → Repositories) is sound, but execution-level debt has accumulated: a 2004-line God File, bloated services, silent error swallowing, synchronous I/O on an async framework, and a fragile frontend coupling. This document defines the refactoring scope.

**Constraint**: Preserve all existing behavior. Every existing test must continue to pass. No feature additions — pure structural improvement.

---

## Phase 1: Split `main.py` (Priority: Highest)

**Problem**: `tradingcat/main.py` is 2004 lines containing `TradingCatApplication` class, 14 Pydantic payload models, 3 exception handlers, and ~100 route handlers. It is the single biggest maintainability blocker.

### Task 1.1: Extract `TradingCatApplication` → `tradingcat/app.py`

- Move `class TradingCatApplication` (line 205–~400) to `tradingcat/app.py`
- Move the `lifespan` async context manager with it
- `main.py` imports `TradingCatApplication` from `app.py`
- Keep `app_state` as a module-level variable in `main.py` (or wherever the FastAPI `app` is created)

### Task 1.2: Extract payload models → `tradingcat/api/schemas.py`

Move these classes out of `main.py`:
- `DecisionPayload` (line 133)
- `ChecklistItemPayload` (line 137)
- `RiskStatePayload` (line 142)
- `MarketDataSmokePayload` (line 148)
- `HistorySyncPayload` (line 154)
- `HistoryRepairPayload` (line 161)
- `FxSyncPayload` (line 165)
- `ResearchNewsItemPayload` (line 172)
- `ResearchNewsSummaryPayload` (line 178)
- `ManualFillImportPayload` (line 182)
- `ExecutionPreviewPayload` (line 187)
- `ExecutionRunPayload` (line 191)
- `RebalancePlanPayload` (line 196)
- `RolloutPolicyPayload` (line 200)

### Task 1.3: Split routes into `tradingcat/routes/` modules

Create `tradingcat/routes/__init__.py` and these modules, each containing an `APIRouter`:

| File | Prefix | Routes to move |
|------|--------|---------------|
| `routes/signals.py` | `/signals` | `/signals/today` |
| `routes/dashboard.py` | `/dashboard` | `/dashboard`, `/dashboard/summary`, `/dashboard/strategies/...`, `/dashboard/accounts/...`, `/dashboard/research`, `/dashboard/journal`, `/dashboard/operations` |
| `routes/portfolio.py` | `/portfolio` | `/portfolio`, `/portfolio/risk-state`, `/portfolio/reconcile`, `/portfolio/rebalance-plan` |
| `routes/orders.py` | `/orders` | `/orders`, `/orders/{id}/cancel`, `/orders/cancel-open` |
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
| `routes/ops.py` | `/ops` | All `/ops/...` routes (~20 endpoints) |
| `routes/research.py` | `/research` | All `/research/...` routes (~15 endpoints) |
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

Move `_risk_violation_handler`, `_value_error_handler`, `_generic_error_handler` (lines 1284–1300) to a separate module. Register them in `main.py` via a `register_error_handlers(app)` function.

---

## Phase 2: Split Bloated Services (Priority: High)

### Task 2.1: Split `ResearchService` (1154 lines)

Current file: `tradingcat/services/research.py`

Split into:
- `tradingcat/services/research.py` — keep backtest orchestration, experiment storage (core)
- `tradingcat/services/strategy_analysis.py` — extract: correlation analysis, stability scoring, strategy recommendations, scorecard generation
- `tradingcat/services/research_ideas.py` — extract: idea generation, news summarization

Each new service receives the dependencies it needs via constructor injection (same pattern as existing services).

### Task 2.2: Split `ExecutionService` (367 lines)

Current file: `tradingcat/services/execution.py`

This one is less urgent (367 lines is manageable), but the concerns are distinct:
- Keep order submission and approval routing in `ExecutionService`
- Extract fill reconciliation + deduplication into `tradingcat/services/reconciliation.py`

### Task 2.3: Wire new services in `TradingCatApplication`

After splitting, update `TradingCatApplication` (now in `app.py`) to instantiate the new services and inject them where needed. Route handlers that called `app.research.some_method()` should now call the appropriate new service.

---

## Phase 3: Error Handling Cleanup (Priority: High)

### Task 3.1: Eliminate silent exception swallowing

Search all files under `tradingcat/services/` for this pattern:
```python
except Exception:
    return <default value>
```

Replace with:
```python
except Exception:
    logger.exception("descriptive message about what failed and context")
    return <default value>
```

Every service file should have `logger = logging.getLogger(__name__)` at the top.

### Task 3.2: Add structured logging

Ensure every service module uses Python `logging`. Key places:
- `services/market_data.py` — log when quote fetch fails and why
- `services/execution.py` — log order submission failures with order details
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
```

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

Add similar validators for: `futu.port` (1–65535), risk thresholds (non-negative).

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

In the route modules created in Phase 1, update handlers that call `fetch_quotes` / `fetch_bars` to `await` the async variants.

---

## Verification

After each phase:

1. Run `pytest` — all existing tests must pass
2. Run `python -c "from tradingcat.main import app; print('OK')"` — import succeeds
3. Run `uvicorn tradingcat.main:app --host 0.0.0.0 --port 8000` — server starts, hit `/preflight` and `/dashboard/summary` to verify
4. `grep -rn "except Exception" tradingcat/services/` — after Phase 3, every match should have a `logger` call nearby

---

## Files Reference

| File | Lines | Role |
|------|-------|------|
| `tradingcat/main.py` | 2004 | God file to split (Phase 1) |
| `tradingcat/services/research.py` | 1154 | Largest service to split (Phase 2) |
| `tradingcat/services/execution.py` | 367 | Secondary split target (Phase 2) |
| `tradingcat/services/reporting.py` | 465 | Review for split if time permits |
| `tradingcat/config.py` | ~150 | Config enhancement (Phase 4) |
| `tradingcat/services/market_data.py` | ~300 | Async conversion (Phase 5) |
| `tradingcat/adapters/factory.py` | ~200 | Logging + config (Phase 3–4) |
| `tests/test_api.py` | — | Must pass after every phase |

## Out of Scope

- Frontend rewrite (separate effort)
- New features or strategy logic changes
- Database migration tooling (Alembic)
- Circuit breaker / retry patterns (future phase)
- Performance optimization

# TradingCat Frontend Refactor Handoff

## Background

TradingCat's frontend is a vanilla JS control panel served by FastAPI (Jinja2 templates + static JS/CSS). The backend refactoring is complete and clean. The frontend has significant code duplication (~25-30%), god functions (200-370 lines), 47 hardcoded API URLs, and zero component abstraction. This document defines the cleanup scope.

**Constraints**:
- Stay vanilla JS — no React/Vue/build tools. This is a personal trading control panel.
- Preserve all existing visual behavior and API interactions.
- Use `<script>` tag loading (common.js first, then page-specific JS). No ES modules.
- All changes in `static/` directory only. Do not modify `templates/` or Python code.

---

## Phase 1: Create Shared Component Layer (Priority: Highest)

### Task 1.1: Create `static/components.js`

Create a new file `static/components.js` that consolidates all duplicated rendering functions from across the codebase.

#### 1.1a: Unified `renderCurve()`

Currently 3 separate implementations:

| File | Line | Signature | Algorithm | Interactive |
|------|------|-----------|-----------|-------------|
| `dashboard.js` | 51 | `renderCurve(points)` | Catmull-Rom spline | Yes (hover tooltip) |
| `account.js` | 8 | `renderCurve(svgId, points)` | Linear | No |
| `strategy.js` | 8 | `renderCurve(svgId, points, stroke, fill)` | Linear, dynamic key | No |

Merge into one parameterized function:

```javascript
/**
 * Render an SVG line chart into the given element.
 * @param {string} svgId - DOM id of the <svg> element
 * @param {Array} points - Array of data points
 * @param {Object} [options]
 * @param {string} [options.valueKey="v"] - Property name for y-axis values
 * @param {string} [options.stroke="#5cc4ff"] - Line color
 * @param {string} [options.fill="rgba(92,196,255,0.12)"] - Area fill color
 * @param {boolean} [options.smooth=false] - Use Catmull-Rom spline smoothing
 * @param {boolean} [options.interactive=false] - Enable hover tooltip
 * @param {Array} [options.overlays] - Macro event overlays (dashboard only)
 */
function renderCurve(svgId, points, options = {}) {
    // ...
}
```

Also move the `catmullRomPath()` helper (currently in `dashboard.js` around line 38) into `components.js`.

**After**: Delete `renderCurve` from `dashboard.js`, `account.js`, `strategy.js`. Update callers:
- `dashboard.js`: `renderCurve("nav-curve", points, { smooth: true, interactive: true, overlays: macroEvents })`
- `account.js`: `renderCurve(svgId, points)` (uses defaults)
- `strategy.js`: `renderCurve(svgId, points, { valueKey: dynamicKey, stroke: color, fill: fillColor })`

#### 1.1b: Unified `statusTone()`

Currently 2 variants with different status vocabularies:

**account.js line 1:**
```javascript
// Recognizes: filled, approved, pending, manual, submitted, rejected, expired, not_submitted, missing
```

**strategy.js line 1:**
```javascript
// Recognizes: filled, approved, aligned, pending, warning, manual, working, rejected, expired, missing, not_submitted
```

Merge into one superset in `components.js`:

```javascript
function statusTone(value) {
    if (value === "filled" || value === "approved" || value === "aligned") return "ok";
    if (value === "pending" || value === "warning" || value === "manual" || value === "submitted" || value === "working") return "warning";
    if (value === "rejected" || value === "expired" || value === "not_submitted" || value === "missing") return "blocked";
    return "empty";
}
```

**After**: Delete `statusTone` from `account.js` (line 1) and `strategy.js` (line 1).

#### 1.1c: Unified `metricTile()`

Currently 2 implementations with different CSS classes and escaping behavior:

**common.js line 49** (safe version with escaping):
```javascript
function metricTile(label, value, subvalue, tone = "empty") {
    const safeValue = typeof value === "string" && value.includes("<span") ? value : escapeHtml(value);
    return `<article class="metric-tile metric-tile--${tone}">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value status-${tone}">${safeValue}</span>
      <div class="metric-subvalue">${escapeHtml(subvalue ?? "")}</div>
    </article>`;
}
```

**operations.js line 88** (unsafe version nested inside `renderOperations()`):
```javascript
function metricTile(label, value, sub, status) {
    return `<article class="metric-tile ${status}">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-meta">${sub}</div>
    </article>`;
}
```

**Action**: Keep the `common.js` version (it has escaping). Delete the nested version from `operations.js`. Update `operations.js` callers to use the global `metricTile()` — adjust parameter mapping where the 4th arg was a raw class like `"ok"` vs a tone.

#### 1.1d: Shared table builder

Currently every page reimplements table rendering via `rows.map(row => '<tr>...</tr>').join("")` (~20 occurrences). Create a lightweight helper:

```javascript
/**
 * Render an HTML table body from row data.
 * @param {Array} rows - Data array
 * @param {Array} columns - Column definitions [{key, label, render?, align?}]
 * @returns {string} HTML string of <tr> elements
 */
function tableRows(rows, columns) {
    return rows.map(row => `<tr>${
        columns.map(col => {
            const val = col.render ? col.render(row) : escapeHtml(row[col.key] ?? "");
            return `<td${col.align ? ` style="text-align:${col.align}"` : ""}>${val}</td>`;
        }).join("")
    }</tr>`).join("");
}
```

This is optional but recommended. Prioritize 1.1a-1.1c first.

### Task 1.2: Create `static/api.js` — API URL Registry

Currently 47 hardcoded API endpoint strings scattered across 7 files. Create a centralized registry:

```javascript
const API = {
    dashboardSummary: "/dashboard/summary",
    portfolio: "/portfolio",
    portfolioRiskState: "/portfolio/risk-state",
    portfolioRebalancePlan: "/portfolio/rebalance-plan",
    orders: "/orders",
    ordersCancelOpen: "/orders/cancel-open",
    ordersManual: "/orders/manual",
    ordersTriggers: "/orders/triggers",
    executionReconcile: "/execution/reconcile",
    executionQuality: "/execution/quality",
    executionMetrics: "/ops/execution-metrics",
    executionPreview: "/execution/preview",
    executionRun: "/execution/run",
    executionGate: "/execution/gate",
    approvals: "/approvals",
    killSwitch: "/kill-switch",
    journalPlans: "/journal/plans",
    journalPlansLatest: "/journal/plans/latest",
    journalSummaries: "/journal/summaries",
    journalSummariesLatest: "/journal/summaries/latest",
    brokerStatus: "/broker/status",
    alertsSummary: "/alerts/summary",
    auditLogs: "/audit/logs",
    opsReadiness: "/ops/readiness",
    opsIncidentsReplay: "/ops/incidents/replay",
    opsLiveAcceptance: "/ops/live-acceptance",
    opsRollout: "/ops/rollout",
    opsTca: "/ops/tca",
    opsRiskConfig: "/ops/risk/config",
    opsEvaluateTriggers: "/ops/evaluate-triggers",
    researchStrategies: (id) => `/research/strategies/${id}`,
    researchScorecard: "/research/scorecard/run",
    researchCandidatesScorecard: "/research/candidates/scorecard",
    researchCorrelation: "/research/correlation",
    researchAlphaRadar: "/research/alpha-radar",
    researchMacroCalendar: "/research/macro-calendar",
};
```

**After**: Replace all hardcoded URL strings across all JS files with `API.xxx` references.

### Task 1.3: Update HTML templates to load new files

All 6 templates in `templates/` load scripts the same way. Add the new files **between** `common.js` and page-specific JS:

```html
<script src="/static/common.js"></script>
<script src="/static/api.js"></script>
<script src="/static/components.js"></script>
<script src="/static/dashboard.js"></script>  <!-- page-specific -->
```

Update all 6 templates:
- `templates/dashboard.html`
- `templates/account.html`
- `templates/strategy.html`
- `templates/operations.html`
- `templates/journal.html`
- `templates/research.html`

---

## Phase 2: Break God Functions (Priority: High)

### Task 2.1: Split `renderOperations()` in `operations.js` (203 lines → ~8 functions)

Current structure (line 31): one function renders 8 distinct sections. Split into:

```javascript
function renderOverviewMetrics(summary, tca, riskConfig) { ... }
function renderPlanTable(plans, summaries) { ... }
function renderQualityMetrics(summary) { ... }
function renderTcaMetrics(tca) { ... }
function renderRiskPanel(riskConfig, killSwitch) { ... }
function renderFillsTable(summary) { ... }
function renderTriggersPanel(triggers) { ... }
function renderIncidentsPanel(incidents) { ... }

async function renderOperations() {
    const payloads = await loadPayloads();
    renderOverviewMetrics(payloads.summary, payloads.tca, payloads.riskConfig);
    renderPlanTable(payloads.plans, payloads.summaries);
    renderQualityMetrics(payloads.summary);
    // ...
}
```

Each sub-function should be < 40 lines. The orchestrator just loads data and dispatches.

### Task 2.2: Split `renderImpact()` in `research.js` (371 lines → ~10 functions)

This is the largest function in the entire frontend. It renders 18+ UI areas inside a strategy detail panel. Split by section:

```javascript
function renderImpactHeader(detail) { ... }
function renderImpactMetrics(detail) { ... }
function renderImpactAccounts(detail, accountSummary) { ... }
function renderSignalTable(detail) { ... }
function renderCorrelationMatrix(detail) { ... }
function renderMonthlyReturns(detail) { ... }
// etc.

function renderImpact(strategyId) {
    const detail = state.strategyDetailCache[strategyId];
    renderImpactHeader(detail);
    renderImpactMetrics(detail);
    // ...
}
```

### Task 2.3: Split `loadStrategy()` in `strategy.js` (217 lines → ~6 functions)

Currently mixes data fetching with rendering. Separate:

```javascript
async function loadStrategy() {
    const [strategyData, summaryData] = await fetchStrategyData(strategyId);
    renderStrategyOverview(strategyData, summaryData);
    renderStrategyCurves(strategyData);
    renderStrategySignals(strategyData);
    renderStrategyImplementation(strategyData, summaryData);
    renderStrategyAccounts(strategyData, summaryData);
}
```

### Task 2.4: Split `renderAssets()` in `dashboard.js` (135 lines → ~4 functions)

```javascript
function renderPositionsTable(positions) { ... }
function renderAllocationBars(positions) { ... }
function renderAccountCompare(accounts) { ... }
function renderCashUsage(accounts) { ... }

function renderAssets() {
    const data = state.summary;
    renderPositionsTable(data.positions);
    renderAllocationBars(data.positions);
    renderAccountCompare(data.accounts);
    renderCashUsage(data.accounts);
}
```

---

## Phase 3: Fix Inconsistencies (Priority: Medium)

### Task 3.1: Replace bare `fetch()` in `account.js` with `apiFetch()`

`account.js` line 37 uses `fetch()` directly instead of the shared `apiFetch()` wrapper. This means no retry logic and inconsistent error handling.

**Before** (account.js):
```javascript
const response = await fetch("/dashboard/summary", { headers: { Accept: "application/json" } });
const payload = await response.json();
```

**After**:
```javascript
const result = await apiFetch(API.dashboardSummary);
if (!result.ok) { showToast(result.error, "error"); return; }
const payload = result.data;
```

### Task 3.2: Remove `window.__researchDashboardSummary` global

`research.js` stores data on `window.__researchDashboardSummary` — a global state anti-pattern. Replace with module-level state variable (already has `const state = {...}`).

### Task 3.3: Move trading hotkeys out of `common.js`

`common.js` lines ~400-491 contain `initGlobalTradingHotkeys()` and `showQuickTradeModal()` (134 lines). These are business logic, not utilities. Move to a new `static/hotkeys.js` or into `dashboard.js` since they're only relevant on the dashboard page.

Only move if the hotkeys are dashboard-specific. If they need to work on all pages, keep in `common.js` but extract `showQuickTradeModal()` into `components.js`.

---

## Verification

After each phase:

1. Open each page in browser and visually verify:
   - `GET /dashboard` — NAV curve renders, metrics load, tabs switch
   - `GET /dashboard/strategies/{id}` — strategy curves render with correct colors
   - `GET /dashboard/accounts/{id}` — account curve renders
   - `GET /dashboard/operations` — all 8 sections render
   - `GET /dashboard/research` — strategy impact panels render, correlation matrix works
   - `GET /dashboard/journal` — plan/summary data loads
2. Verify no JS console errors on any page
3. Verify keyboard shortcuts still work (Ctrl+K overlay, Ctrl+X cancel, Shift+X kill switch)
4. Verify toast notifications still appear on API errors
5. Run: `grep -n "function renderCurve\|function statusTone" static/*.js` — should only appear in `components.js`
6. Run: `grep -c "apiFetch\|fetch(" static/*.js` — `account.js` should use `apiFetch`, not bare `fetch`

---

## Files Reference

| File | Current Lines | Action |
|------|--------------|--------|
| `static/components.js` | **NEW** | Shared UI components (renderCurve, statusTone, tableRows) |
| `static/api.js` | **NEW** | API URL registry |
| `static/common.js` | 491 | Remove metricTile if moved to components.js; remove hotkeys if extracted |
| `static/dashboard.js` | 1,156 | Remove renderCurve + catmullRomPath; split renderAssets; use API constants |
| `static/operations.js` | 352 | Remove nested metricTile; split renderOperations; use API constants |
| `static/research.js` | 638 | Split renderImpact; remove window global; use API constants |
| `static/strategy.js` | 301 | Remove renderCurve + statusTone; split loadStrategy; use API constants |
| `static/account.js` | 201 | Remove renderCurve + statusTone; replace fetch with apiFetch; use API constants |
| `static/journal.js` | 238 | Use API constants |
| `templates/*.html` | 6 files | Add `<script>` tags for api.js and components.js |

## Out of Scope

- CSS refactoring (dashboard.css is acceptable)
- Switching to a JS framework (React/Vue/Alpine)
- Adding a build system (webpack/vite)
- Adding frontend tests
- Changing HTML template structure
- Modifying Python backend code

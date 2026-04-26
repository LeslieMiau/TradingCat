# TradingCat 前端重构交接文档

## 背景

TradingCat 前端是由 FastAPI 提供的原生 JS 控制台（Jinja2 templates + static JS/CSS）。后端重构已经完成并保持清晰，但前端仍有明显重复：约 25-30% 代码重复、200-370 行级别的巨型函数、47 个硬编码 API URL，并且几乎没有组件抽象。本文定义后续清理范围。

**约束：**

- 保持原生 JS，不引入 React/Vue/构建工具；这是个人交易控制台。
- 保留现有视觉行为和 API 交互。
- 使用 `<script>` 标签加载：先 `common.js`，再页面专用 JS；不使用 ES modules。
- 除明确要求外，优先只改 `static/`。若新增共享 JS 文件，需要同步更新 `templates/` 的 `<script>` 标签。

---

## Phase 1：建立共享组件层（优先级：最高）

### Task 1.1：创建 `static/components.js`

创建 `static/components.js`，集中放置当前散落在各页面中的重复渲染函数。

#### 1.1a：统一 `renderCurve()`

当前有 3 份独立实现：

| 文件 | 位置 | 签名 | 算法 | 是否交互 |
|---|---|---|---|---|
| `dashboard.js` | line 51 | `renderCurve(points)` | Catmull-Rom spline | 是，hover tooltip |
| `account.js` | line 8 | `renderCurve(svgId, points)` | 线性 | 否 |
| `strategy.js` | line 8 | `renderCurve(svgId, points, stroke, fill)` | 线性，动态 key | 否 |

合并为一个参数化函数：

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

同时把当前在 `dashboard.js` 约 line 38 的 `catmullRomPath()` 移到 `components.js`。

完成后：

- 从 `dashboard.js`、`account.js`、`strategy.js` 删除本地 `renderCurve`。
- 更新调用方：
  - `dashboard.js`：`renderCurve("nav-curve", points, { smooth: true, interactive: true, overlays: macroEvents })`
  - `account.js`：`renderCurve(svgId, points)`，使用默认参数。
  - `strategy.js`：`renderCurve(svgId, points, { valueKey: dynamicKey, stroke: color, fill: fillColor })`

#### 1.1b：统一 `statusTone()`

当前有 2 个不同词表版本：

`account.js` line 1：

```javascript
// Recognizes: filled, approved, pending, manual, submitted, rejected, expired, not_submitted, missing
```

`strategy.js` line 1：

```javascript
// Recognizes: filled, approved, aligned, pending, warning, manual, working, rejected, expired, missing, not_submitted
```

合并成 `components.js` 中的超集：

```javascript
function statusTone(value) {
    if (value === "filled" || value === "approved" || value === "aligned") return "ok";
    if (value === "pending" || value === "warning" || value === "manual" || value === "submitted" || value === "working") return "warning";
    if (value === "rejected" || value === "expired" || value === "not_submitted" || value === "missing") return "blocked";
    return "empty";
}
```

完成后从 `account.js` 和 `strategy.js` 删除本地 `statusTone`。

#### 1.1c：统一 `metricTile()`

当前有 2 个版本，CSS class 和 escaping 行为不一致：

`common.js` line 49 是安全版本：

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

`operations.js` line 88 有一个内嵌的不安全版本：

```javascript
function metricTile(label, value, sub, status) {
    return `<article class="metric-tile ${status}">
      <div class="metric-label">${label}</div>
      <div class="metric-value">${value}</div>
      <div class="metric-meta">${sub}</div>
    </article>`;
}
```

处理方式：保留 `common.js` 的安全版本，删除 `operations.js` 中的内嵌版本。更新 `operations.js` 调用方，让第 4 个参数传入 tone（如 `"ok"`、`"warning"`、`"blocked"`、`"empty"`）。

#### 1.1d：共享 table builder

当前各页面反复使用 `rows.map(row => '<tr>...</tr>').join("")` 渲染表格，约 20 处。新增轻量 helper：

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

该项可选但推荐。优先完成 1.1a-1.1c。

### Task 1.2：创建 `static/api.js` API URL 注册表

当前 47 个 API endpoint 字符串分散在 7 个文件中。创建集中注册表：

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

完成后，把所有 JS 文件中的硬编码 URL 字符串替换为 `API.xxx` 引用。

### Task 1.3：更新 HTML 模板加载顺序

6 个模板都按同样方式加载脚本。在 `common.js` 和页面专用 JS 之间加入新文件：

```html
<script src="/static/common.js"></script>
<script src="/static/api.js"></script>
<script src="/static/components.js"></script>
<script src="/static/dashboard.js"></script>
```

需要更新：

- `templates/dashboard.html`
- `templates/account.html`
- `templates/strategy.html`
- `templates/operations.html`
- `templates/journal.html`
- `templates/research.html`

---

## Phase 2：拆分巨型函数（优先级：高）

### Task 2.1：拆分 `operations.js` 中的 `renderOperations()`

当前 `renderOperations()` 约 203 行，渲染 8 个独立区块。拆成：

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

每个子函数控制在 40 行以内；顶层 orchestrator 只负责加载数据并分发渲染。

### Task 2.2：拆分 `research.js` 中的 `renderImpact()`

这是当前前端最大函数，约 371 行，在策略详情面板内渲染 18 个以上 UI 区域。按 section 拆分：

```javascript
function renderImpactHeader(detail) { ... }
function renderImpactMetrics(detail) { ... }
function renderImpactAccounts(detail, accountSummary) { ... }
function renderSignalTable(detail) { ... }
function renderCorrelationMatrix(detail) { ... }
function renderMonthlyReturns(detail) { ... }

function renderImpact(strategyId) {
    const detail = state.strategyDetailCache[strategyId];
    renderImpactHeader(detail);
    renderImpactMetrics(detail);
    // ...
}
```

### Task 2.3：拆分 `strategy.js` 中的 `loadStrategy()`

当前 `loadStrategy()` 约 217 行，把数据加载和渲染混在一起。拆成：

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

### Task 2.4：拆分 `dashboard.js` 中的 `renderAssets()`

当前 `renderAssets()` 约 135 行。建议拆成：

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

## Phase 3：修正不一致（优先级：中）

### Task 3.1：把 `account.js` 中的裸 `fetch()` 换成 `apiFetch()`

`account.js` line 37 直接使用 `fetch()`，没有走共享 `apiFetch()` 包装，导致 retry 和错误处理不一致。

修改前：

```javascript
const response = await fetch("/dashboard/summary", { headers: { Accept: "application/json" } });
const payload = await response.json();
```

修改后：

```javascript
const result = await apiFetch(API.dashboardSummary);
if (!result.ok) { showToast(result.error, "error"); return; }
const payload = result.data;
```

### Task 3.2：移除 `window.__researchDashboardSummary` 全局变量

`research.js` 把数据放到 `window.__researchDashboardSummary`，这是全局状态反模式。改为模块级 state 变量；文件中已有 `const state = {...}` 可承接。

### Task 3.3：把交易快捷键从 `common.js` 移出

`common.js` 约 line 400-491 包含 `initGlobalTradingHotkeys()` 和 `showQuickTradeModal()`，这是业务逻辑，不是通用工具。若快捷键只在 dashboard 页面有意义，移到 `static/hotkeys.js` 或 `dashboard.js`。

如果快捷键需要在所有页面工作，则保留在 `common.js`，但把 `showQuickTradeModal()` 抽到 `components.js`。

---

## 验证

每个 phase 后做以下检查：

1. 打开各页面并目视验证：
   - `GET /dashboard`：NAV 曲线渲染，指标加载，tab 可切换。
   - `GET /dashboard/strategies/{id}`：策略曲线颜色正确。
   - `GET /dashboard/accounts/{id}`：账户曲线渲染。
   - `GET /dashboard/operations`：8 个 section 都可渲染。
   - `GET /dashboard/research`：策略 impact 面板渲染，相关性矩阵工作。
   - `GET /dashboard/journal`：plan/summary 数据加载。
2. 确认所有页面没有 JS console error。
3. 确认键盘快捷键仍工作：Ctrl+K overlay、Ctrl+X cancel、Shift+X kill switch。
4. 确认 API 错误时仍显示 toast。
5. 运行：`grep -n "function renderCurve\|function statusTone" static/*.js`，应只在 `components.js` 出现。
6. 运行：`grep -c "apiFetch\|fetch(" static/*.js`，`account.js` 应使用 `apiFetch`，不再使用裸 `fetch`。

---

## 文件参考

| 文件 | 当前行数 | 动作 |
|---|---:|---|
| `static/components.js` | 新增 | 共享 UI 组件：`renderCurve`、`statusTone`、`tableRows` |
| `static/api.js` | 新增 | API URL 注册表 |
| `static/common.js` | 491 | 如果迁移，移除 `metricTile`；如果抽离快捷键，也从这里移除 hotkeys |
| `static/dashboard.js` | 1,156 | 删除 `renderCurve` / `catmullRomPath`，拆分 `renderAssets`，使用 API constants |
| `static/operations.js` | 352 | 删除内嵌 `metricTile`，拆分 `renderOperations`，使用 API constants |
| `static/research.js` | 638 | 拆分 `renderImpact`，移除 window global，使用 API constants |
| `static/strategy.js` | 301 | 删除 `renderCurve` / `statusTone`，拆分 `loadStrategy`，使用 API constants |
| `static/account.js` | 201 | 删除 `renderCurve` / `statusTone`，把 `fetch` 换成 `apiFetch`，使用 API constants |
| `static/journal.js` | 238 | 使用 API constants |
| `templates/*.html` | 6 个文件 | 增加 `api.js` 和 `components.js` 的 `<script>` 标签 |

## 不在本轮范围

- CSS 重构；当前 `dashboard.css` 可接受。
- 切换到 JS 框架（React/Vue/Alpine）。
- 增加构建系统（webpack/vite）。
- 增加前端测试。
- 改变 HTML template 结构。
- 修改 Python 后端代码。

const state = {
  summary: null,
  incidents: null,
  rebalance: null,
  alphaRadar: null,
  macroCalendar: null,
  error: null,
  activeAccount: "total",
};

const dashboardAccounts = window.DashboardAccounts;
const dashboardStrategy = window.DashboardStrategy;
const dashboardOperations = window.DashboardOperations;

function renderSection(label, fn) {
  if (typeof fn !== "function") {
    return;
  }
  try {
    fn(state);
  } catch (err) {
    console.warn(`[Dashboard] ${label} failed:`, err.message);
  }
}

function renderError() {
  const message = state.error ?? "Unknown dashboard error";
  const errorCell = (cols) => `<tr><td colspan="${cols}" class="table-empty">${escapeHtml(message)}</td></tr>`;
  const errorMetric = (label) => metricTile(label, "Unavailable", message, "blocked");
  const el = (id) => document.getElementById(id);

  if (el("overview-cards")) el("overview-cards").innerHTML = errorMetric("Dashboard Error");
  if (el("plan-metrics")) el("plan-metrics").innerHTML = errorMetric("Trading Plan");
  if (el("plan-table")) el("plan-table").innerHTML = errorCell(8);
  if (el("priority-actions-table")) el("priority-actions-table").innerHTML = errorCell(4);
  if (el("queue-metrics")) el("queue-metrics").innerHTML = errorMetric("Execution Queue");
  if (el("daily-highlights")) setList("daily-highlights", [], message);
  if (el("weekly-highlights")) setList("weekly-highlights", [], message);
  if (el("blockers-list")) setList("blockers-list", [], message);
  if (el("global-incidents-list")) setList("global-incidents-list", [], message);
  if (el("queue-approvals-list")) setList("queue-approvals-list", [], message);
  if (el("queue-orders-list")) setList("queue-orders-list", [], message);
  if (el("filled-orders-list")) setList("filled-orders-list", [], message);
  if (el("probe-orders-list")) setList("probe-orders-list", [], message);
}

function renderDashboard() {
  const sections = [
    ["renderTabs", dashboardAccounts?.renderTabs],
    ["renderOverview", dashboardAccounts?.renderOverview],
    ["renderAssets", dashboardAccounts?.renderAssets],
    ["renderStrategies", dashboardStrategy?.renderStrategies],
    ["renderStrategyPlanBreakdown", dashboardStrategy?.renderStrategyPlanBreakdown],
    ["renderMarketPlanBreakdown", dashboardStrategy?.renderMarketPlanBreakdown],
    ["renderMarketBudget", dashboardStrategy?.renderMarketBudget],
    ["renderCandidates", dashboardStrategy?.renderCandidates],
    ["renderPlan", dashboardStrategy?.renderPlan],
    ["renderSignalFunnel", dashboardStrategy?.renderSignalFunnel],
    ["renderExecutionBlockers", dashboardOperations?.renderExecutionBlockers],
    ["renderPriorityActions", dashboardOperations?.renderPriorityActions],
    ["renderSummaries", dashboardOperations?.renderSummaries],
    ["renderAlphaRadar", dashboardOperations?.renderAlphaRadar],
    ["renderMacroCalendar", dashboardOperations?.renderMacroCalendar],
  ];
  sections.forEach(([label, fn]) => renderSection(label, fn));
}

async function loadSummary() {
  const summaryResult = await apiFetch(API.dashboardSummary);
  if (!summaryResult.ok) {
    state.error = summaryResult.error;
    state.summary = null;
    state.incidents = null;
    state.rebalance = null;
    return;
  }

  state.summary = summaryResult.data;
  state.error = null;
  renderDashboard();

  const [incidentsResult, rebalanceResult, alphaResult, macroResult] = await Promise.all([
    apiFetch(API.opsIncidentsReplay(7)),
    apiFetch(API.portfolioRebalancePlan, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }),
    apiFetch(API.researchAlphaRadar(15)),
    apiFetch(API.researchMacroCalendar(7)),
  ]);
  state.incidents = incidentsResult.ok ? incidentsResult.data : null;
  state.rebalance = rebalanceResult.ok ? rebalanceResult.data : null;
  state.alphaRadar = alphaResult.ok ? alphaResult.data : null;
  state.macroCalendar = macroResult.ok ? macroResult.data : null;

  renderDashboard();
}

let dashboardLoading = false;

async function loadDashboard() {
  if (dashboardLoading) {
    return;
  }
  dashboardLoading = true;
  const button = document.getElementById("refresh-dashboard");
  if (button) {
    button.classList.add("button--loading");
    button.disabled = true;
    button.textContent = "加载中...";
  }

  await loadSummary();
  if (state.error) {
    renderError();
    showToast(state.error, "error");
  } else {
    showToast("数据已刷新", "success", 2000);
  }

  if (button) {
    button.classList.remove("button--loading");
    button.disabled = false;
    button.textContent = "刷新数据";
  }
  dashboardLoading = false;
}

document.getElementById("refresh-dashboard")?.addEventListener("click", () => {
  loadDashboard();
});

document.querySelectorAll("#account-tabs .tab").forEach((node) => {
  node.addEventListener("click", () => {
    state.activeAccount = node.dataset.account;
    renderSection("renderTabs", dashboardAccounts?.renderTabs);
    const grid = document.querySelector(".dashboard-grid");
    if (grid) {
      grid.classList.add("panel--updating");
      requestAnimationFrame(() => {
        renderDashboard();
        requestAnimationFrame(() => grid.classList.remove("panel--updating"));
      });
    } else {
      renderDashboard();
    }
  });
});

function enableTableSort() {
  document.querySelectorAll(".data-table th").forEach((th) => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const table = th.closest("table");
      const tbody = table?.querySelector("tbody");
      if (!tbody) {
        return;
      }
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const rows = Array.from(tbody.querySelectorAll("tr")).filter((row) => !row.querySelector(".table-empty"));
      if (!rows.length) {
        return;
      }
      const dir = th.dataset.sortDir === "asc" ? "desc" : "asc";
      th.parentNode.querySelectorAll("th").forEach((header) => {
        delete header.dataset.sortDir;
        header.classList.remove("sort-asc", "sort-desc");
      });
      th.dataset.sortDir = dir;
      th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
      rows.sort((left, right) => {
        const leftText = (left.children[idx]?.textContent ?? "").trim();
        const rightText = (right.children[idx]?.textContent ?? "").trim();
        const leftNumber = parseFloat(leftText.replace(/[,%¥$]/g, ""));
        const rightNumber = parseFloat(rightText.replace(/[,%¥$]/g, ""));
        if (!Number.isNaN(leftNumber) && !Number.isNaN(rightNumber)) {
          return dir === "asc" ? leftNumber - rightNumber : rightNumber - leftNumber;
        }
        return dir === "asc" ? leftText.localeCompare(rightText, "zh") : rightText.localeCompare(leftText, "zh");
      });
      rows.forEach((row) => tbody.appendChild(row));
    });
  });
}

registerShortcut("r", "刷新数据", () => loadDashboard());
registerShortcut("1", "切换到总账户", () => { state.activeAccount = "total"; renderDashboard(); });
registerShortcut("2", "切换到A股", () => { state.activeAccount = "CN"; renderDashboard(); });
registerShortcut("3", "切换到港股", () => { state.activeAccount = "HK"; renderDashboard(); });
registerShortcut("4", "切换到美股", () => { state.activeAccount = "US"; renderDashboard(); });
registerShortcut("/", "聚焦搜索框", () => {
  const search = document.querySelector(".table-search");
  if (search) {
    search.focus();
    search.scrollIntoView({ behavior: "smooth", block: "center" });
  }
});
initKeyboardShortcuts();

loadDashboard().then(() => {
  enableTableSort();
  if (document.getElementById("search-assets") && document.getElementById("assets-table")) {
    enableTableSearch("search-assets", "assets-table");
  }
  if (document.getElementById("search-candidates") && document.getElementById("candidates-table")) {
    enableTableSearch("search-candidates", "candidates-table");
  }
});

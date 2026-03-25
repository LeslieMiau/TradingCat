
// --- TradingCat UX Redesign Patch ---
// Gracefully absorb null elements for components removed from the dashboard layout.
const _originalGetElementById = document.getElementById.bind(document);
document.getElementById = function(id) {
    const el = _originalGetElementById(id);
    if (!el) {
        return {
            innerHTML: '',
            textContent: '',
            value: '',
            appendChild: () => {},
            addEventListener: () => {},
            classList: { add: ()=>{}, remove: ()=>{}, toggle: ()=>{} },
            style: {}
        };
    }
    return el;
};
// ------------------------------------
const state = {
  summary: null,
  incidents: null,
  rebalance: null,
  error: null,
  activeAccount: "total",
};


function accountData() {
  return state.summary?.accounts?.[state.activeAccount] ?? null;
}

function planNote() {
  return state.summary?.journal?.latest_plan ?? {};
}

function summaryNote() {
  return state.summary?.journal?.latest_summary ?? {};
}

function renderTabs() {
  document.querySelectorAll("#account-tabs .tab").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.account === state.activeAccount);
  });
  const detailLink = document.getElementById("account-detail-link");
  if (detailLink) {
    detailLink.href = `/dashboard/accounts/${encodeURIComponent(state.activeAccount)}`;
  }
}

function renderCurve(points) {
  const svg = document.getElementById("nav-curve");
  if (!svg) return;
  if (!points || !points.length) {
    svg.innerHTML = "";
    return;
  }
  const width = 640;
  const height = 240;
  const padding = 18;
  const values = points.map((item) => Number(item.v));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const step = (width - padding * 2) / Math.max(points.length - 1, 1);
  const coords = points.map((item, index) => {
    const x = padding + step * index;
    const y = height - padding - ((Number(item.v) - min) / spread) * (height - padding * 2);
    return [x, y];
  });
  const line = coords.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  const area = `${line} L ${coords.at(-1)[0].toFixed(2)} ${(height - padding).toFixed(2)} L ${coords[0][0].toFixed(2)} ${(height - padding).toFixed(2)} Z`;
  svg.innerHTML = `
    <defs><linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(92,196,255,0.18)"/><stop offset="100%" stop-color="rgba(92,196,255,0.02)"/></linearGradient></defs>
    <path d="${area}" fill="url(#cg)"></path>
    <path d="${line}" fill="none" stroke="#5cc4ff" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"></path>
    <circle cx="${coords.at(-1)[0].toFixed(2)}" cy="${coords.at(-1)[1].toFixed(2)}" r="4" fill="#34d399" stroke="#0b0e13" stroke-width="2"></circle>
    ${coords.map(([x,y],i) => `<circle cx="${x.toFixed(2)}" cy="${y.toFixed(2)}" r="8" fill="transparent"><title>${escapeHtml(points[i].t??"")} ${money(points[i].v)}</title></circle>`).join("")}
  `;
}

function renderOverview() {
  const overview = state.summary?.overview ?? {};
  const details = state.summary?.details ?? {};
  const gate = details.execution_gate ?? {};
  const live = details.live_acceptance ?? {};
  const account = accountData() ?? {};
  const tone = gate.should_block ? "blocked" : gate.ready ? "ok" : "warning";
  const cards = [
    metricTile("当前账户 NAV", money(account.nav), `${account.label ?? ""} / 现金 ${money(account.cash)}`, "ok"),
    metricTile("持仓市值", money(account.position_value), `持仓数 ${fmt(account.position_count)}`, "ok"),
    metricTile("现金占比", fmtPct(account.cash_weight), `现金 ${money(account.cash)}`, "warning"),
    metricTile("总收益", `${fmtPct(account.total_return ?? overview.total_return)} ${trendIcon(account.total_return ?? overview.total_return)}`, `回撤 ${fmtPct(account.drawdown ?? overview.drawdown)}`, (account.total_return ?? overview.total_return) >= 0 ? "ok" : "blocked"),
    metricTile("日 / 周盈亏", `${money(account.daily_pnl ?? overview.daily_pnl)} ${trendIcon(account.daily_pnl ?? overview.daily_pnl)} / ${money(account.weekly_pnl ?? overview.weekly_pnl)}`, "PnL", (account.daily_pnl ?? overview.daily_pnl) >= 0 ? "ok" : "blocked"),
    metricTile("运行状态", live.ready_for_live ? "Live Ready" : gate.should_block ? "Blocked" : "Warning", `Gate ${gate.policy_stage ?? "N/A"} / Live ${fmt(live.ready_for_live)}`, tone),
  ];
  document.getElementById("overview-cards").innerHTML = cards.join("");
  const now = new Date();
  document.getElementById("topline-updated").innerHTML = `Updated ${now.toLocaleString()} ${freshnessIndicator(now)}`;
  document.getElementById("curve-title").textContent = `${account.label ?? "总账户"}净值曲线`;
  renderCurve(account.nav_curve ?? []);
}

function renderAssets() {
  const account = accountData() ?? {};
  const rows = account.positions ?? [];
  const totalPositions = state.summary?.assets?.positions ?? [];
  const totalNav = Number(state.summary?.accounts?.total?.nav || 0);
  const tbody = document.getElementById("assets-table");
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="9" class="table-empty">当前账户没有持仓。</td></tr>';
  } else {
    tbody.innerHTML = rows
      .map(
        (row) => `
          <tr>
            <td data-label="资产"><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(row.name ?? "")}</span></td>
            <td data-label="市场">${escapeHtml(row.market)}</td>
            <td data-label="类别">${escapeHtml(row.asset_class)}</td>
            <td data-label="数量">${escapeHtml(fmt(row.quantity, 4))}</td>
            <td data-label="均价">${escapeHtml(money(row.average_cost))}</td>
            <td data-label="市值">${escapeHtml(money(row.market_value))}</td>
            <td data-label="配置">${escapeHtml(fmtPct(row.weight))}</td>
            <td data-label="浮盈亏" class="${row.unrealized_pnl >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(money(row.unrealized_pnl))} ${trendIcon(row.unrealized_pnl)}</td>
            <td data-label="收益" class="${(row.unrealized_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.unrealized_return))}</td>
          </tr>
        `,
      )
      .join("");
  }
  const allocation = account.allocation_mix ?? {};
  document.getElementById("allocation-bars").innerHTML = `
    <div class="stack-row">
      <label>Cash / Equity / Option</label>
      <div class="stack-track">
        <span class="stack-segment cash" style="width:${(allocation.cash ?? 0) * 100}%"></span>
        <span class="stack-segment equity" style="width:${(allocation.equity ?? 0) * 100}%"></span>
        <span class="stack-segment option" style="width:${(allocation.option ?? 0) * 100}%"></span>
      </div>
    </div>
  `;
  setList(
    "account-bullets",
    [
      `账户: ${account.label ?? "N/A"}`,
      `NAV: ${money(account.nav)}`,
      `现金: ${money(account.cash)}`,
      `持仓市值: ${money(account.position_value)}`,
      `现金占比: ${fmtPct(account.cash_weight)}`,
    ],
    "暂无账户说明。",
  );

  const compareTable = document.getElementById("account-compare-table");
  const allAccounts = state.summary?.accounts ?? {};
  const gate = state.summary?.details?.execution_gate ?? {};
  const live = state.summary?.details?.live_acceptance ?? {};
  const compareRows = ["total", "CN", "HK", "US"]
    .map((key) => {
      const item = allAccounts[key];
      if (!item) return null;
      const status = key === "total"
        ? (live.ready_for_live ? "live_ready" : gate.should_block ? "blocked" : "warning")
        : ((item.plan_items?.length ?? 0) > 0 ? "planned" : "idle");
      return { key, item, status };
    })
    .filter(Boolean);
  compareTable.innerHTML = compareRows.length
    ? compareRows.map(({ key, item, status }) => `
        <tr>
          <td><strong><a href="/dashboard/accounts/${encodeURIComponent(key)}">${escapeHtml(item.label)}</a></strong></td>
          <td>${escapeHtml(money(item.nav))}</td>
          <td>${escapeHtml(fmtPct(item.cash_weight))}</td>
          <td class="${(item.total_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(item.total_return))}</td>
          <td>${escapeHtml(fmt((item.plan_items || []).length))}</td>
          <td>${escapeHtml(fmt(item.position_count))}</td>
          <td><span class="badge status-${badgeTone(status === "blocked" ? "blocked" : status === "live_ready" ? "ok" : status === "planned" ? "warning" : "empty")}">${escapeHtml(status)}</span></td>
        </tr>
      `).join("")
    : '<tr><td colspan="7" class="table-empty">当前没有账户对照数据。</td></tr>';

  const planItems = state.summary?.trading_plan?.items ?? [];
  const notionalByAccount = new Map([
    ["CN", 0],
    ["HK", 0],
    ["US", 0],
  ]);
  const planCountByAccount = new Map([
    ["CN", 0],
    ["HK", 0],
    ["US", 0],
  ]);
  planItems.forEach((item) => {
    const market = item.market || "unknown";
    const notional = Number(item.reference_price || 0) * Number(item.quantity || 0);
    notionalByAccount.set(market, (notionalByAccount.get(market) || 0) + notional);
    planCountByAccount.set(market, (planCountByAccount.get(market) || 0) + 1);
  });
  const usageRows = ["total", "CN", "HK", "US"]
    .map((key) => {
      const item = allAccounts[key];
      if (!item) return null;
      const planNotional = key === "total"
        ? [...notionalByAccount.values()].reduce((sum, value) => sum + value, 0)
        : Number(notionalByAccount.get(key) || 0);
      const planCount = key === "total"
        ? planItems.length
        : Number(planCountByAccount.get(key) || 0);
      const cashUsage = Number(item.cash || 0) > 0 ? planNotional / Number(item.cash) : null;
      return {
        key,
        label: item.label,
        cash: Number(item.cash || 0),
        planNotional,
        planCount,
        cashUsage,
      };
    })
    .filter(Boolean);
  document.getElementById("cash-usage-metrics").innerHTML = [
    metricTile("总计划金额", money(usageRows.find((row) => row.key === "total")?.planNotional ?? 0), "gross notional today", usageRows.length ? "ok" : "warning"),
    metricTile("最高使用率", fmtPct(Math.max(...usageRows.map((row) => Number(row.cashUsage || 0)))), "max cash draw by account", usageRows.length ? "warning" : "empty"),
    metricTile("触达账户", fmt(usageRows.filter((row) => row.planCount > 0 && row.key !== "total").length), "accounts with plan today", usageRows.length ? "ok" : "warning"),
    metricTile("总计划单", fmt(planItems.length), "planned intents", planItems.length ? "ok" : "warning"),
  ].join("");
  document.getElementById("cash-usage-table").innerHTML = usageRows.length
    ? usageRows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.label)}</strong></td>
          <td>${escapeHtml(money(row.cash))}</td>
          <td>${escapeHtml(money(row.planNotional))}</td>
          <td>${escapeHtml(row.cashUsage != null ? fmtPct(row.cashUsage) : "N/A")}</td>
          <td>${escapeHtml(fmt(row.planCount))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有现金使用数据。</td></tr>';
}

function labelSide(value) {
  if (value === "buy") return "买入";
  if (value === "sell") return "卖出";
  return value == null ? "N/A" : String(value);
}

function labelPlanStatus(value) {
  if (value === "planned") return "有计划";
  if (value === "no_trade") return "无交易";
  if (value === "blocked") return "已阻塞";
  return value == null ? "N/A" : String(value);
}

function renderStrategies() {
  const strategies = state.summary?.strategies ?? {};
  const metrics = strategies.portfolio_metrics ?? {};
  document.getElementById("strategy-metrics").innerHTML = [
    metricTile("组合年化", fmtPct(metrics.annualized_return), `通过 ${fmt(strategies.portfolio_passed)}`, strategies.portfolio_passed ? "ok" : "warning"),
    metricTile("组合夏普", fmt(metrics.sharpe), `策略数 ${fmt(metrics.strategy_count)}`, "ok"),
    metricTile("组合最大回撤", fmtPct(metrics.max_drawdown), `Calmar ${fmt(metrics.calmar)}`, "warning"),
    metricTile("通过策略", fmt((strategies.accepted_strategy_ids ?? []).length), `Accepted ${(strategies.accepted_strategy_ids ?? []).join(", ") || "None"}`, (strategies.accepted_strategy_ids ?? []).length ? "ok" : "warning"),
  ].join("");

  const rows = strategies.rows ?? [];
  const cards = document.getElementById("strategy-cards");
  cards.innerHTML = rows.length
    ? rows
        .map(
          (row) => `
            <article class="detail-card">
              <h3><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.name)}</a></h3>
              <p class="detail-paragraph">${escapeHtml(row.thesis)}</p>
              <div class="tag-row">
                <span class="badge status-${badgeTone(row.action)}">${escapeHtml(row.action)}</span>
                <span class="tag">${escapeHtml(row.cadence)}</span>
                <span class="tag">${escapeHtml(row.capacity_tier)}</span>
              </div>
              <div class="tag-row">
                ${(row.focus_instruments ?? []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}
              </div>
              <div class="tag-row">
                ${(row.indicators ?? []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")}
              </div>
            </article>
          `,
        )
        .join("")
    : '<article class="detail-card"><span class="detail-empty">当前没有策略数据。</span></article>';

  const tbody = document.getElementById("strategies-table");
  tbody.innerHTML = rows.length
    ? rows
        .map(
          (row) => `
            <tr>
              <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.name)}</a></strong><br /><span class="meta-text">${escapeHtml(row.strategy_id)}</span></td>
              <td><span class="badge status-${badgeTone(row.action)}">${escapeHtml(row.action)}</span></td>
              <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
              <td>${escapeHtml(fmt(row.sharpe))}</td>
              <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
              <td>${escapeHtml(fmt(row.calmar))}</td>
              <td>${escapeHtml(`${row.stability_bucket} / pass ${fmtPct(row.validation_pass_rate)}`)}</td>
            </tr>
          `,
        )
        .join("")
    : '<tr><td colspan="7" class="table-empty">当前没有策略指标。</td></tr>';

  const perfTop = rows.slice().sort((a, b) => (b.annualized_return ?? 0) - (a.annualized_return ?? 0)).slice(0, 5);
  setList("strategy-perf-top-list", perfTop.map((r) => `${r.name}: 年化 ${fmtPct(r.annualized_return)} / 夏普 ${fmt(r.sharpe)}`), "暂无策略表现排名。");
  const execTop = rows.filter((r) => r.action === "active" || r.action === "deploy").slice(0, 5);
  setList("strategy-exec-top-list", execTop.map((r) => `${r.name}: ${r.action} / 年化 ${fmtPct(r.annualized_return)}`), "暂无执行中策略。");
  setList("account-strategy-matrix-list", ["total", "CN", "HK", "US"].map((key) => {
    const count = rows.filter((r) => (r.markets ?? []).includes(key) || key === "total").length;
    return `${key}: ${fmt(count)} 条策略`;
  }), "暂无账户-策略矩阵。");
  const nextActions = state.summary?.strategies?.next_actions ?? [];
  setList("research-group-summary-list", nextActions.length ? nextActions : ["暂无研究分组总览。"], "暂无研究分组总览。");

  const planItems = state.summary?.trading_plan?.items ?? [];
  const strategyFundMap = new Map();
  planItems.forEach((item) => {
    const sid = item.strategy_id || "unknown";
    const notional = Number(item.reference_price || 0) * Number(item.quantity || 0);
    strategyFundMap.set(sid, (strategyFundMap.get(sid) || 0) + notional);
  });
  const fundRows = [...strategyFundMap.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
  const totalFund = fundRows.reduce((s, r) => s + r[1], 0);
  const fundTable = document.getElementById("strategy-fund-top-table");
  if (fundTable) {
    fundTable.innerHTML = fundRows.length
      ? fundRows.map(([sid, notional]) => `
          <tr>
            <td>${escapeHtml(sid)}</td>
            <td>${escapeHtml(money(notional))}</td>
            <td>${escapeHtml(totalFund ? fmtPct(notional / totalFund) : "N/A")}</td>
            <td>${escapeHtml(fmt(planItems.filter((i) => i.strategy_id === sid).length))}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="4" class="table-empty">当前没有策略资金占用数据。</td></tr>';
  }
}

function renderStrategyPlanBreakdown() {
  const items = state.summary?.trading_plan?.items ?? [];
  const rawApprovals = state.summary?.trading_plan?.pending_approvals;
  const approvals = Array.isArray(rawApprovals) ? rawApprovals : [];
  const grouped = new Map();

  const ensureRow = (strategyId) => {
    if (!grouped.has(strategyId)) {
      grouped.set(strategyId, {
        market: strategyId,
        itemCount: 0,
        approvalCount: 0,
        notional: 0,
        strategies: new Set(),
      });
    }
    return grouped.get(strategyId);
  };

  items.forEach((item) => {
    const row = ensureRow(item.strategy_id || "unknown");
    row.itemCount += 1;
    row.notional += Number(item.reference_price || 0) * Number(item.quantity || 0);
    row.strategies.add(item.market || "unknown");
  });

  approvals.forEach((item) => {
    const row = ensureRow(item.strategy_id || "unknown");
    row.approvalCount += 1;
    row.strategies.add(item.market || "unknown");
  });

  const rows = [...grouped.values()].sort((left, right) => right.notional - left.notional);
  document.getElementById("strategy-plan-metrics").innerHTML = [
    metricTile("涉及策略", fmt(rows.length), "strategies in today's plan", rows.length ? "ok" : "warning"),
    metricTile("总计划单", fmt(items.length), "planned intents", items.length ? "ok" : "warning"),
    metricTile("预估总金额", money(rows.reduce((sum, row) => sum + row.notional, 0)), "estimated gross notional", rows.length ? "ok" : "empty"),
    metricTile("待审批策略", fmt(rows.filter((row) => row.approvalCount > 0).length), "strategies needing manual step", approvals.length ? "warning" : "ok"),
  ].join("");

  document.getElementById("strategy-plan-table").innerHTML = rows.length
    ? rows.map((row) => `
        <tr>
          <td><span class="badge status-${badgeTone(row.approvalCount ? "warning" : "ok")}">${escapeHtml(row.market)}</span></td>
          <td>${escapeHtml(fmt(row.itemCount))}</td>
          <td>${escapeHtml(money(row.notional))}</td>
          <td>${escapeHtml(fmt(row.approvalCount))}</td>
          <td>${escapeHtml([...row.strategies].slice(0, 3).join(", ") || "N/A")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">今天还没有按策略拆分的计划。</td></tr>';
}

function renderMarketPlanBreakdown() {
  const items = state.summary?.trading_plan?.items ?? [];
  const rawApprovals = state.summary?.trading_plan?.pending_approvals;
  const approvals = Array.isArray(rawApprovals) ? rawApprovals : [];
  const grouped = new Map();

  const ensureRow = (market) => {
    if (!grouped.has(market)) {
      grouped.set(market, {
        market,
        itemCount: 0,
        approvalCount: 0,
        notional: 0,
        strategies: new Set(),
      });
    }
    return grouped.get(market);
  };

  items.forEach((item) => {
    const row = ensureRow(item.market || "unknown");
    row.itemCount += 1;
    row.notional += Number(item.reference_price || 0) * Number(item.quantity || 0);
    row.strategies.add(item.strategy_id || "unknown");
  });

  approvals.forEach((item) => {
    const row = ensureRow(item.market || "unknown");
    row.approvalCount += 1;
    row.strategies.add(item.strategy_id || "unknown");
  });

  const rows = [...grouped.values()].sort((left, right) => right.notional - left.notional);
  document.getElementById("market-plan-table").innerHTML = rows.length
    ? rows.map((row) => `
        <tr>
          <td><span class="badge status-${badgeTone(row.approvalCount ? "warning" : "ok")}">${escapeHtml(row.market)}</span></td>
          <td>${escapeHtml(fmt(row.itemCount))}</td>
          <td>${escapeHtml(money(row.notional))}</td>
          <td>${escapeHtml(fmt(row.approvalCount))}</td>
          <td>${escapeHtml([...row.strategies].slice(0, 3).join(", ") || "N/A")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">今天还没有按市场拆分的计划。</td></tr>';
}

function renderMarketBudget() {
  const budgetRows = state.summary?.market_budget ?? [];
  document.getElementById("market-budget-table").innerHTML = budgetRows.length
    ? budgetRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(row.actualWeight == null ? "N/A" : fmtPct(row.actualWeight))}</td>
          <td>${escapeHtml(fmtPct(row.targetWeight))}</td>
          <td class="${Math.abs(Number(row.delta || 0)) <= 0.02 ? "status-ok" : Number(row.delta || 0) > 0 ? "status-warning" : "status-blocked"}">
            ${escapeHtml(row.delta == null ? "N/A" : fmtPct(row.delta))}
            <span class="badge status-${badgeTone(row.action === "aligned" ? "ok" : row.action === "overweight" ? "warning" : row.action === "underweight" ? "blocked" : "empty")}">${escapeHtml(row.action)}</span>
          </td>
        </tr>
      `).join("")
    : '<tr><td colspan="4" class="table-empty">当前没有市场预算数据。</td></tr>';
}

function renderCandidates() {
  const candidates = state.summary?.candidates ?? {};
  document.getElementById("candidate-metrics").innerHTML = [
    metricTile("可继续研究", fmt(candidates.deploy_candidate_count), "deploy_candidate", candidates.deploy_candidate_count ? "ok" : "warning"),
    metricTile("仅纸面跟踪", fmt(candidates.paper_only_count), "paper_only", candidates.paper_only_count ? "warning" : "ok"),
    metricTile("应淘汰", fmt(candidates.rejected_count), "reject", candidates.rejected_count ? "blocked" : "ok"),
    metricTile("下一步", fmt((candidates.next_actions ?? []).length), (candidates.next_actions ?? [])[0] ?? "No action", "warning"),
  ].join("");

  const rows = candidates.rows ?? [];
  const tops = candidates.top_candidates ?? [];
  setList(
    "candidate-top-list",
    tops.map((row) => `${row.strategy_id}: ${row.verdict} / score ${fmt(row.profitability_score)}`),
    "当前没有候选策略。",
  );
  setList("candidate-actions-list", candidates.next_actions ?? [], "当前没有额外研究动作。");
  const tbody = document.getElementById("candidates-table");
  tbody.innerHTML = rows.length
    ? rows.map((row) => `
        <tr>
          <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></strong></td>
          <td><span class="badge status-${badgeTone(row.verdict === "deploy_candidate" ? "ok" : row.verdict === "paper_only" ? "warning" : "blocked")}">${escapeHtml(row.verdict)}</span></td>
          <td>${escapeHtml(fmt(row.profitability_score))}</td>
          <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
          <td>${escapeHtml(fmt(row.sharpe))}</td>
          <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
          <td>${escapeHtml(fmt(row.max_selected_correlation))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="7" class="table-empty">当前没有候选策略评分。</td></tr>';

  const verdictBuckets = new Map([
    ["deploy_candidate", { label: "deploy", rows: [] }],
    ["paper_only", { label: "paper", rows: [] }],
    ["reject", { label: "reject", rows: [] }],
  ]);
  rows.forEach((row) => {
    const verdict = row.verdict || "reject";
    if (!verdictBuckets.has(verdict)) {
      verdictBuckets.set(verdict, { label: verdict, rows: [] });
    }
    verdictBuckets.get(verdict).rows.push(row);
  });
  const groupRows = [...verdictBuckets.values()].map((group) => {
    const count = group.rows.length;
    const average = (key) => {
      if (!count) return null;
      const total = group.rows.reduce((sum, row) => sum + Number(row[key] || 0), 0);
      return total / count;
    };
    return {
      label: group.label,
      count,
      avgProfitability: average("profitability_score"),
      avgAnnualizedReturn: average("annualized_return"),
      avgSharpe: average("sharpe"),
      avgMaxDrawdown: average("max_drawdown"),
    };
  });
  document.getElementById("candidate-group-metrics").innerHTML = [
    metricTile("Deploy 组", fmt(groupRows.find((row) => row.label === "deploy")?.count ?? 0), "worth funding research", (groupRows.find((row) => row.label === "deploy")?.count ?? 0) ? "ok" : "warning"),
    metricTile("Paper 组", fmt(groupRows.find((row) => row.label === "paper")?.count ?? 0), "monitor before funding", (groupRows.find((row) => row.label === "paper")?.count ?? 0) ? "warning" : "ok"),
    metricTile("Reject 组", fmt(groupRows.find((row) => row.label === "reject")?.count ?? 0), "drop quickly", (groupRows.find((row) => row.label === "reject")?.count ?? 0) ? "blocked" : "ok"),
    metricTile("总候选", fmt(rows.length), "candidate universe", rows.length ? "ok" : "warning"),
  ].join("");
  document.getElementById("candidate-groups-table").innerHTML = groupRows.length
    ? groupRows.map((row) => `
        <tr>
          <td><span class="badge status-${badgeTone(row.label === "deploy" ? "ok" : row.label === "paper" ? "warning" : row.label === "reject" ? "blocked" : "empty")}">${escapeHtml(row.label)}</span></td>
          <td>${escapeHtml(fmt(row.count))}</td>
          <td>${escapeHtml(row.avgProfitability == null ? "N/A" : fmt(row.avgProfitability))}</td>
          <td>${escapeHtml(row.avgAnnualizedReturn == null ? "N/A" : fmtPct(row.avgAnnualizedReturn))}</td>
          <td>${escapeHtml(row.avgSharpe == null ? "N/A" : fmt(row.avgSharpe))}</td>
          <td>${escapeHtml(row.avgMaxDrawdown == null ? "N/A" : fmtPct(row.avgMaxDrawdown))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有研究分组数据。</td></tr>';
}

function renderPlan() {
  const tradingPlan = state.summary?.trading_plan ?? {};
  const plan = planNote();
  const planHistory = state.summary?.journal?.recent_plans ?? [];
  const account = accountData() ?? {};
  const gate = tradingPlan.gate ?? {};
  const rows = account.plan_items ?? [];
  const allPlanItems = tradingPlan.items ?? [];
  const allPositions = state.summary?.assets?.positions ?? [];
  document.getElementById("plan-metrics").innerHTML = [
    metricTile("Signals", fmt(tradingPlan.signal_count), `Intents ${fmt(tradingPlan.intent_count)}`, "ok"),
    metricTile("自动 / 手工", `${fmt(tradingPlan.automated_count)} / ${fmt(tradingPlan.manual_count)}`, "Auto / Manual", tradingPlan.manual_count ? "warning" : "ok"),
    metricTile("计划状态", labelPlanStatus(plan.status), plan.headline ?? "暂无标题", badgeTone(plan.status)),
    metricTile("执行闸门", gate.should_block ? "已阻塞" : gate.ready ? "已就绪" : "预警", `Policy ${fmt(gate.policy_stage)}`, gate.should_block ? "blocked" : gate.ready ? "ok" : "warning"),
  ].join("");
  document.getElementById("journal-plan-headline").textContent = plan.headline ?? "暂无计划说明。";
  setList("journal-plan-reasons", plan.reasons ?? [], "今日没有额外说明。");
  setList(
    "plan-side-notes",
    [
      `当前账户: ${account.label ?? "N/A"}`,
      `今日计划数: ${fmt(rows.length)}`,
      `待审批: ${fmt(Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals.length : tradingPlan.pending_approvals ?? 0)}`,
      `Gate ready: ${fmt(gate.ready)}`,
      `信号数: ${fmt(plan.counts?.signal_count)}`,
      `自动 / 手工: ${fmt(plan.counts?.automated_count)} / ${fmt(plan.counts?.manual_count)}`,
    ],
    "暂无计划侧说明。",
  );
  const planBody = [];
  (plan.reasons ?? []).forEach((item) => planBody.push(`原因：${item}`));
  (plan.items ?? []).slice(0, 5).forEach((item) => {
    const side = item.side === "buy" ? "买入" : item.side === "sell" ? "卖出" : "未知";
    const target = item.target_weight == null ? "N/A" : fmtPct(item.target_weight);
    const qty = item.quantity == null ? "N/A" : fmt(item.quantity, 4);
    const reason = item.reason ?? "暂无原因说明";
    planBody.push(`${item.symbol}，${side} ${qty}，目标权重 ${target}，原因：${reason}`);
  });
  if (!planBody.length) {
    if (plan.status === "no_trade") {
      planBody.push("今日无交易计划：当前 active 策略没有生成可执行计划单。");
    } else if (plan.status === "blocked") {
      planBody.push("今日计划被 gate 或运行条件阻塞。");
    }
  }
  setList("plan-body-list", planBody, "今天的计划正文暂无内容。");
  const heroPlanHeadline = document.getElementById("hero-plan-headline");
  if (heroPlanHeadline) heroPlanHeadline.textContent = plan.headline ?? "暂无计划说明。";
  setList("hero-plan-body-list", planBody, "今天的计划正文暂无内容。");
  const buyItems = (plan.items ?? [])
    .filter((item) => item.side === "buy")
    .slice(0, 4)
    .map((item) => `${item.symbol} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.requires_approval ? "人工审批" : "自动执行"}`);
  const sellItems = (plan.items ?? [])
    .filter((item) => item.side === "sell")
    .slice(0, 4)
    .map((item) => `${item.symbol} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.requires_approval ? "人工审批" : "自动执行"}`);
  const manualItems = (plan.items ?? [])
    .filter((item) => item.requires_approval)
    .slice(0, 4)
    .map((item) => `${item.symbol} / ${item.side === "buy" ? "买入" : item.side === "sell" ? "卖出" : "未知"} / ${item.reason ?? "暂无原因说明"}`);
  setList("hero-plan-buy-list", buyItems, "今天没有买入计划。");
  setList("hero-plan-sell-list", sellItems, "今天没有卖出计划。");
  setList("hero-plan-manual-list", manualItems, "今天没有需要人工审批的计划。");

  const tbody = document.getElementById("plan-table");
  if (tradingPlan.error) {
    tbody.innerHTML = `<tr><td colspan="8" class="table-empty">${escapeHtml(tradingPlan.error)}</td></tr>`;
  } else if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="table-empty">当前账户今日没有交易计划。</td></tr>';
  } else {
    tbody.innerHTML = rows
      .map(
        (row) => `
          <tr>
            <td>${escapeHtml(row.strategy_id)}</td>
            <td><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(row.market)}</span></td>
            <td>${escapeHtml(labelSide(row.side))}</td>
            <td>${escapeHtml(fmt(row.quantity, 4))}</td>
            <td>${escapeHtml(row.target_weight == null ? "N/A" : fmtPct(row.target_weight))}</td>
            <td>${escapeHtml(row.reference_price == null ? "N/A" : money(row.reference_price))}</td>
            <td><span class="badge status-${row.requires_approval ? "warning" : "ok"}">${row.requires_approval ? "manual" : "auto"}</span></td>
            <td>${escapeHtml(row.reason ?? "")}</td>
          </tr>
        `,
      )
      .join("");
  }

  const buyCount = allPlanItems.filter((item) => item.side === "buy").length;
  const sellCount = allPlanItems.filter((item) => item.side === "sell").length;
  const automatedCount = allPlanItems.filter((item) => !item.requires_approval).length;
  const manualCount = allPlanItems.filter((item) => item.requires_approval).length;
  const netTargetWeight = allPlanItems.reduce((sum, item) => sum + Number(item.target_weight || 0), 0);
  const marketCounts = ["CN", "HK", "US"].map((market) => ({
    market,
    count: allPlanItems.filter((item) => item.market === market).length,
  }));
  const primaryMarket = marketCounts.sort((left, right) => right.count - left.count)[0]?.market ?? "N/A";
  const directionalBias = buyCount > sellCount ? "risk_on" : sellCount > buyCount ? "risk_off" : "balanced";
  document.getElementById("plan-direction-metrics").innerHTML = [
    metricTile("买 / 卖", `${fmt(buyCount)} / ${fmt(sellCount)}`, directionalBias, buyCount >= sellCount ? "ok" : "warning"),
    metricTile("自动 / 手工", `${fmt(automatedCount)} / ${fmt(manualCount)}`, "execution mix", manualCount ? "warning" : "ok"),
    metricTile("净目标权重", fmtPct(netTargetWeight), "gross target bias", Math.abs(netTargetWeight) > 0.2 ? "warning" : "ok"),
    metricTile("主市场", primaryMarket, `CN ${fmt(marketCounts.find((item) => item.market === "CN")?.count ?? 0)} / HK ${fmt(marketCounts.find((item) => item.market === "HK")?.count ?? 0)} / US ${fmt(marketCounts.find((item) => item.market === "US")?.count ?? 0)}`, "ok"),
  ].join("");
  document.getElementById("plan-direction-table").innerHTML = [
    { label: "方向倾向", value: directionalBias, note: buyCount === sellCount ? "买卖数量相当" : buyCount > sellCount ? "买入计划多于卖出计划" : "卖出计划多于买入计划" },
    { label: "执行模式", value: manualCount ? "mixed" : "automated", note: `${fmt(manualCount)} 笔需要人工审批` },
    { label: "净暴露", value: fmtPct(netTargetWeight), note: "计划单 target_weight 汇总结果" },
    { label: "主市场", value: primaryMarket, note: "今天计划单最集中的市场" },
  ].map((row) => `
      <tr>
        <td>${escapeHtml(row.label)}</td>
        <td>${escapeHtml(row.value)}</td>
        <td>${escapeHtml(row.note)}</td>
      </tr>
    `).join("");

  const notionalRows = allPlanItems
    .map((item) => ({
      symbol: item.symbol,
      market: item.market,
      side: labelSide(item.side),
      requiresApproval: item.requires_approval,
      targetWeight: Number(item.target_weight || 0),
      notional: Number(item.reference_price || 0) * Number(item.quantity || 0),
    }))
    .sort((left, right) => right.notional - left.notional)
    .slice(0, 8);
  document.getElementById("plan-notional-top-table").innerHTML = notionalRows.length
    ? notionalRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(row.side)}</td>
          <td>${escapeHtml(money(row.notional))}</td>
          <td>${escapeHtml(fmtPct(row.targetWeight))}</td>
          <td><span class="badge status-${row.requiresApproval ? "warning" : "ok"}">${row.requiresApproval ? "manual" : "auto"}</span></td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有计划金额排序数据。</td></tr>';

  const currentWeightBySymbol = new Map(
    allPositions.map((position) => [`${position.market}:${position.symbol}`, Number(position.weight || 0)]),
  );
  const gapRows = allPlanItems
    .map((item) => {
      const key = `${item.market}:${item.symbol}`;
      const currentWeight = currentWeightBySymbol.get(key) ?? 0;
      const targetWeight = Number(item.target_weight || 0);
      const gap = targetWeight - currentWeight;
      return { symbol: item.symbol, market: item.market, currentWeight, targetWeight, gap, side: labelSide(item.side) };
    })
    .filter((row) => Math.abs(row.gap) > 0.0001)
    .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap))
    .slice(0, 10);
  document.getElementById("plan-vs-holdings-table").innerHTML = gapRows.length
    ? gapRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.symbol)}</td>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(fmtPct(row.currentWeight))}</td>
          <td>${escapeHtml(fmtPct(row.targetWeight))}</td>
          <td class="${row.gap >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.gap))}</td>
          <td>${escapeHtml(row.side)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有计划与持仓偏差数据。</td></tr>';
}

function renderSignalFunnel() {
  const tradingPlan = state.summary?.trading_plan ?? {};
  const recentOrders = state.summary?.details?.recent_orders ?? [];
  const signals = Number(tradingPlan.signal_count || 0);
  const intents = Number(tradingPlan.intent_count || 0);
  const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals.length : Number(tradingPlan.pending_approvals || 0);
  const orders = recentOrders.length;
  const fills = recentOrders.filter((item) => item.status === "filled").length;

  const ratio = (value, base) => {
    if (!base) return "N/A";
    return fmtPct(value / base);
  };

  document.getElementById("signal-funnel-metrics").innerHTML = [
    metricTile("信号", fmt(signals), "research signals", signals ? "ok" : "warning"),
    metricTile("计划", fmt(intents), `from signals ${ratio(intents, signals)}`, intents ? "ok" : "warning"),
    metricTile("待审批", fmt(approvals), `from plans ${ratio(approvals, intents)}`, approvals ? "warning" : "ok"),
    metricTile("出单", fmt(orders), `from plans ${ratio(orders, intents)}`, orders ? "ok" : "warning"),
    metricTile("成交", fmt(fills), `from orders ${ratio(fills, orders)}`, fills ? "ok" : "warning"),
  ].join("");

  const rows = [
    { stage: "研究信号", count: signals, rate: "100.00%", note: "策略生成的原始候选信号" },
    { stage: "进入计划", count: intents, rate: ratio(intents, signals), note: "通过风控与 gate 后形成计划单" },
    { stage: "待审批", count: approvals, rate: ratio(approvals, intents), note: "需要人工确认的计划单" },
    { stage: "已出订单", count: orders, rate: ratio(orders, intents), note: "已经推送到 broker 的订单" },
    { stage: "已成交", count: fills, rate: ratio(fills, orders), note: "最近订单里状态为 filled 的数量" },
  ];
  document.getElementById("signal-funnel-table").innerHTML = rows.map((row) => `
      <tr>
        <td>${escapeHtml(row.stage)}</td>
        <td>${escapeHtml(fmt(row.count))}</td>
        <td>${escapeHtml(row.rate)}</td>
        <td>${escapeHtml(row.note)}</td>
      </tr>
    `).join("");
}

function renderExecutionBlockers() {
  const tradingPlan = state.summary?.trading_plan ?? {};
  const details = state.summary?.details ?? {};
  const gateReasons = details.execution_gate?.reasons ?? [];
  const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals : [];
  const recentOrders = details.recent_orders ?? [];
  const workingOrders = recentOrders.filter((item) => item.status && item.status !== "filled" && item.status !== "cancelled");
  const rejectedOrders = recentOrders.filter((item) => item.status === "rejected");

  const rows = [
    {
      type: "gate",
      count: gateReasons.length,
      tone: gateReasons.length ? "blocked" : "ok",
      note: gateReasons.length ? gateReasons.join(" | ") : "当前没有 execution gate 阻塞。",
    },
    {
      type: "approval",
      count: approvals.length,
      tone: approvals.length ? "warning" : "ok",
      note: approvals.length ? approvals.slice(0, 3).map((item) => `${item.symbol}/${item.market}`).join(", ") : "当前没有待审批单。",
    },
    {
      type: "working_order",
      count: workingOrders.length,
      tone: workingOrders.length ? "warning" : "ok",
      note: workingOrders.length ? workingOrders.slice(0, 3).map((item) => `${item.broker_order_id}/${item.status}`).join(", ") : "当前没有处理中订单。",
    },
    {
      type: "rejected_order",
      count: rejectedOrders.length,
      tone: rejectedOrders.length ? "blocked" : "ok",
      note: rejectedOrders.length ? rejectedOrders.slice(0, 3).map((item) => `${item.broker_order_id}/${item.symbol}`).join(", ") : "当前没有被拒订单。",
    },
  ];

  document.getElementById("execution-blocker-metrics").innerHTML = [
    metricTile("Gate 卡点", fmt(rows[0].count), "execution gate reasons", rows[0].tone),
    metricTile("审批卡点", fmt(rows[1].count), "pending approvals", rows[1].tone),
    metricTile("订单处理中", fmt(rows[2].count), "working broker orders", rows[2].tone),
    metricTile("拒单", fmt(rows[3].count), "rejected broker orders", rows[3].tone),
  ].join("");
  document.getElementById("execution-blocker-table").innerHTML = rows.map((row) => `
      <tr>
        <td>${escapeHtml(row.type)}</td>
        <td>${escapeHtml(fmt(row.count))}</td>
        <td><span class="badge status-${badgeTone(row.tone)}">${escapeHtml(row.tone)}</span></td>
        <td>${escapeHtml(row.note)}</td>
      </tr>
    `).join("");
}

function renderPriorityActions() {
  const details = state.summary?.details ?? {};
  const tradingPlan = state.summary?.trading_plan ?? {};
  const strategyActions = state.summary?.strategies?.next_actions ?? [];
  const candidateActions = state.summary?.candidates?.next_actions ?? [];
  const rebalanceRows = (state.rebalance?.rebalance_actions ?? []).filter((row) => row.action !== "hold");
  const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals : [];
  const gateReasons = details.execution_gate?.reasons ?? [];

  const actions = [];
  gateReasons.forEach((item, index) => {
    actions.push({
      priority: index + 1,
      type: "gate",
      action: item.type,
      reason: item.detail,
    });
  });
  approvals.slice(0, 3).forEach((item) => {
    actions.push({
      priority: actions.length + 1,
      type: "approval",
      action: `Approve ${item.symbol}`,
      reason: item.reason || `${item.market} / ${item.side}`,
    });
  });
  rebalanceRows.slice(0, 3).forEach((item) => {
    actions.push({
      priority: actions.length + 1,
      type: "rebalance",
      action: `${item.action} ${item.symbol}`,
      reason: `delta ${fmtPct(item.delta)}`,
    });
  });
  [...strategyActions, ...candidateActions].slice(0, 4).forEach((item) => {
    actions.push({
      priority: actions.length + 1,
      type: "research",
      action: "Review strategy",
      reason: item,
    });
  });

  document.getElementById("priority-actions-table").innerHTML = actions.length
    ? actions.slice(0, 10).map((row) => `
        <tr>
          <td>${escapeHtml(String(row.priority))}</td>
          <td><span class="badge status-${badgeTone(row.type === "gate" ? "blocked" : row.type === "approval" ? "warning" : row.type === "rebalance" ? "warning" : "ok")}">${escapeHtml(row.type)}</span></td>
          <td>${escapeHtml(row.action)}</td>
          <td>${escapeHtml(row.reason)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="4" class="table-empty">当前没有需要优先处理的动作。</td></tr>';
}

function renderSummaries() {
  const daily = state.summary?.summaries?.daily ?? {};
  const weekly = state.summary?.summaries?.weekly ?? {};
  const details = state.summary?.details ?? {};
  const note = summaryNote();
  const blockers = [
    ...(details.execution_gate?.reasons ?? []).map((item) => typeof item === "string" ? item : `${item.type}: ${item.detail}`),
    ...(details.live_acceptance?.blockers ?? []),
    ...(note.blockers ?? []),
  ];
  const actions = [
    ...(state.summary?.strategies?.next_actions ?? []),
    ...(daily.next_actions ?? []),
    ...(weekly.next_actions ?? []),
    ...(note.next_actions ?? []),
  ];
  document.getElementById("journal-summary-headline").textContent = note.headline ?? "暂无总结。";
  setList("daily-highlights", note.highlights?.length ? note.highlights : daily.highlights ?? [], "今日暂无摘要。");
  setList("weekly-highlights", weekly.highlights ?? [], "本周暂无摘要。");
  setList("blockers-list", blockers, "当前没有硬阻塞项。");
  setList("actions-list", actions, "当前没有待处理动作。");
  const heroSummaryEl = document.getElementById("hero-summary-headline");
  if (heroSummaryEl) heroSummaryEl.textContent = note.headline ?? "暂无总结。";
  setList("hero-summary-body-list", [...(note.highlights ?? []), ...(note.blockers ?? []).map((b) => `阻塞：${b}`), ...(note.next_actions ?? []).map((a) => `下一步：${a}`)], "今天还没有总结正文。");
  setList("hero-summary-metrics-list", [
    `亮点 ${fmt((note.highlights ?? []).length)}`,
    `阻塞 ${fmt((note.blockers ?? []).length)}`,
    `下一步 ${fmt((note.next_actions ?? []).length)}`,
    `执行 gate: ${details.execution_gate?.ready ? "就绪" : "未就绪"}`,
  ], "暂无总结指标。");
  setList("global-blockers-list", blockers, "当前没有全局阻塞项。");
  setList(
    "global-incidents-list",
    (state.incidents?.events ?? []).slice(0, 6).map((item) => `${item.occurred_at} / ${item.category} / ${item.label}`),
    "最近没有关键事件。",
  );
  const report = state.summary?.details?.latest_report ?? {};
  const reportCards = report.cards ?? {};
  document.getElementById("report-snapshot-metrics").innerHTML = [
    metricTile("报告状态", fmt(report.ready), `category ${fmt(report.category)}`, report.ready ? "ok" : "warning"),
    metricTile("Execution Gate", fmt(reportCards.execution_gate?.ready), `blocked ${fmt(reportCards.execution_gate?.should_block)}`, reportCards.execution_gate?.ready ? "ok" : "warning"),
    metricTile("Live Acceptance", fmt(reportCards.live_acceptance?.ready_for_live), `incidents ${fmt(reportCards.live_acceptance?.incident_count)}`, reportCards.live_acceptance?.ready_for_live ? "ok" : "warning"),
    metricTile("Execution Run", fmt(reportCards.execution_run?.submitted_count), `failed ${fmt(reportCards.execution_run?.failed_count)}`, Number(reportCards.execution_run?.failed_count || 0) === 0 ? "ok" : "warning"),
  ].join("");
  setList(
    "report-snapshot-list",
    [
      `report_dir: ${fmt(report.report_dir)}`,
      `severity: ${fmt(report.severity)}`,
      `findings: ${fmt((report.findings ?? []).length)}`,
      `rollout recommendation: ${fmt(reportCards.rollout?.current_recommendation)}`,
    ],
    "当前没有最近报告。",
  );
  setList(
    "report-snapshot-cards",
    [
      `broker order check: ${fmt(reportCards.broker_order_check?.submission_status)} / ${fmt(reportCards.broker_order_check?.cancellation_status)}`,
      `cancel open orders: cancelled ${fmt(reportCards.cancel_open_orders?.cancelled_count)}, failed ${fmt(reportCards.cancel_open_orders?.failed_count)}`,
      `execution quality: within_limits ${fmt(reportCards.execution_quality?.within_limits)}`,
      `authorization: all_authorized ${fmt(reportCards.execution_authorization?.all_authorized)}`,
    ],
    "当前没有最近报告卡片。",
  );
  setList("data-health-list", [
    `data feeds: ${fmt(report.data_feed_status ?? "unknown")}`,
    `last sync: ${fmt(report.last_sync_at ?? "N/A")}`,
    `coverage: ${fmt(report.data_coverage ?? "N/A")}`,
  ], "暂无数据健康信息。");
  setList("launch-progress-list", [
    `recommendation: ${fmt(reportCards.rollout?.current_recommendation ?? "N/A")}`,
    `gate ready: ${fmt(reportCards.execution_gate?.ready ?? false)}`,
    `live ready: ${fmt(reportCards.live_acceptance?.ready_for_live ?? false)}`,
  ], "暂无上线推进信息。");
  const summaryBodyEl = document.getElementById("summary-body-text");
  if (summaryBodyEl) {
    const bodyParts = [...(note.highlights ?? []), ...(note.blockers ?? []).map((b) => `阻塞: ${b}`), ...(note.next_actions ?? []).map((a) => `下一步: ${a}`)];
    summaryBodyEl.textContent = bodyParts.length ? bodyParts.join(" | ") : "暂无总结正文。";
  }
  const rawApprovals = state.summary?.trading_plan?.pending_approvals;
  const approvals = Array.isArray(rawApprovals) ? rawApprovals : [];
  const recentOrders = state.summary?.details?.recent_orders ?? [];
  const filledOrders = recentOrders.filter((item) => item.status === "filled").length;
  const workingOrders = recentOrders.filter((item) => item.status && item.status !== "filled" && item.status !== "cancelled").length;
  document.getElementById("queue-metrics").innerHTML = [
    metricTile("待审批", fmt(approvals.length), "pending approval queue", approvals.length ? "warning" : "ok"),
    metricTile("最近订单", fmt(recentOrders.length), "recent broker orders", recentOrders.length ? "ok" : "warning"),
    metricTile("已成交", fmt(filledOrders), "filled recently", filledOrders ? "ok" : "warning"),
    metricTile("处理中", fmt(workingOrders), "submitted / pending", workingOrders ? "warning" : "ok"),
  ].join("");
  setList(
    "queue-approvals-list",
    approvals.slice(0, 6).map((item) => `${item.symbol} / ${item.market} / ${item.side} / ${item.status}`),
    "当前没有待审批单。",
  );
  setList(
    "queue-orders-list",
    recentOrders.slice(0, 6).map((item) => `${item.broker_order_id} / ${item.status} / filled ${fmt(item.filled_quantity, 4)}`),
    "当前没有最近订单。",
  );
  setList(
    "filled-orders-list",
    recentOrders
      .filter((item) => item.status === "filled")
      .slice(0, 6)
      .map((item) => `${item.broker_order_id} / filled ${fmt(item.filled_quantity, 4)} / avg ${item.average_price == null ? "N/A" : money(item.average_price)}`),
    "当前没有最近成交单。",
  );
  const probe = reportCards.broker_order_check ?? {};
  const probeItems = [];
  if (probe.symbol || probe.broker_order_id || probe.submission_status || probe.cancellation_status) {
    probeItems.push(
      `${fmt(probe.symbol)} / ${fmt(probe.submission_status)} / ${fmt(probe.cancellation_status)} / order ${fmt(probe.broker_order_id)}`,
    );
  }
  setList("probe-orders-list", probeItems, "当前没有最近验证单。");

  const now = Date.now();
  const ageMinutes = (value) => {
    if (!value) return null;
    const parsed = new Date(value).getTime();
    if (Number.isNaN(parsed)) return null;
    return Math.max(0, Math.round((now - parsed) / 60000));
  };
  const pendingApprovalAges = approvals.map((item) => ageMinutes(item.created_at)).filter((value) => value != null);
  const workingOrderAges = recentOrders
    .filter((item) => item.status && item.status !== "filled" && item.status !== "cancelled")
    .map((item) => ageMinutes(item.timestamp))
    .filter((value) => value != null);
  const filledOrderAges = recentOrders
    .filter((item) => item.status === "filled")
    .map((item) => ageMinutes(item.timestamp))
    .filter((value) => value != null);
  const latencyRows = [
    {
      label: "待审批",
      count: approvals.length,
      oldest: pendingApprovalAges.length ? `${fmt(Math.max(...pendingApprovalAges))} min` : "N/A",
      note: approvals.length ? "最老 pending approval 的创建时间" : "当前没有待审批单。",
      tone: approvals.length ? "warning" : "ok",
    },
    {
      label: "处理中订单",
      count: workingOrders,
      oldest: workingOrderAges.length ? `${fmt(Math.max(...workingOrderAges))} min` : "N/A",
      note: workingOrders ? "submitted / pending 订单里最老的一笔" : "当前没有处理中订单。",
      tone: workingOrders ? "warning" : "ok",
    },
    {
      label: "最近成交",
      count: filledOrders,
      oldest: filledOrderAges.length ? `${fmt(Math.max(...filledOrderAges))} min` : "N/A",
      note: filledOrders ? "最近 filled 订单距离现在的时间" : "当前没有最近成交。",
      tone: filledOrders ? "ok" : "empty",
    },
  ];
  document.getElementById("latency-metrics").innerHTML = [
    metricTile("待审批年龄", latencyRows[0].oldest, `count ${fmt(latencyRows[0].count)}`, latencyRows[0].tone),
    metricTile("订单年龄", latencyRows[1].oldest, `count ${fmt(latencyRows[1].count)}`, latencyRows[1].tone),
    metricTile("最近成交年龄", latencyRows[2].oldest, `count ${fmt(latencyRows[2].count)}`, latencyRows[2].tone),
    metricTile("执行新鲜度", workingOrders || approvals.length ? "stalled" : "fresh", "approval/order latency snapshot", workingOrders || approvals.length ? "warning" : "ok"),
  ].join("");
  document.getElementById("latency-table").innerHTML = latencyRows.map((row) => `
      <tr>
        <td>${escapeHtml(row.label)}</td>
        <td>${escapeHtml(fmt(row.count))}</td>
        <td>${escapeHtml(row.oldest)}</td>
        <td>${escapeHtml(row.note)}</td>
      </tr>
    `).join("");
}

async function loadSummary() {
  /* Phase 1: fetch critical summary first for fast first-paint */
  const summaryResult = await apiFetch("/dashboard/summary");
  if (!summaryResult.ok) {
    state.error = summaryResult.error;
    state.summary = null;
    state.incidents = null;
    state.rebalance = null;
    return;
  }
  state.summary = summaryResult.data;
  state.error = null;

  /* Render immediately with primary data */
  renderDashboard();

  /* Phase 2: fetch secondary data in parallel, update affected sections */
  const [incidentsResult, rebalanceResult] = await Promise.all([
    apiFetch("/ops/incidents/replay?window_days=7"),
    apiFetch("/portfolio/rebalance-plan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }),
  ]);
  state.incidents = incidentsResult.ok ? incidentsResult.data : null;
  state.rebalance = rebalanceResult.ok ? rebalanceResult.data : null;
  /* Re-render sections that depend on secondary data */
  try { renderSummaries(); } catch (e) { console.warn("[Dashboard] renderSummaries re-render:", e.message); }
  try { renderPriorityActions(); } catch (e) { console.warn("[Dashboard] renderPriorityActions re-render:", e.message); }
}

function renderError() {
  const message = state.error ?? "Unknown dashboard error";
  const errorCell = (cols) => `<tr><td colspan="${cols}" class="table-empty">${escapeHtml(message)}</td></tr>`;
  const errorMetric = (label) => metricTile(label, "Unavailable", message, "blocked");
  const el = (id) => document.getElementById(id);

  if (el("overview-cards")) el("overview-cards").innerHTML = errorMetric("Dashboard Error");
  if (el("assets-table")) el("assets-table").innerHTML = errorCell(9);
  if (el("account-compare-table")) el("account-compare-table").innerHTML = errorCell(7);
  if (el("cash-usage-metrics")) el("cash-usage-metrics").innerHTML = errorMetric("Cash Usage");
  if (el("cash-usage-table")) el("cash-usage-table").innerHTML = errorCell(5);
  if (el("account-risk-table")) el("account-risk-table").innerHTML = errorCell(6);
  if (el("concentration-table")) el("concentration-table").innerHTML = errorCell(5);
  if (el("pnl-market-table")) el("pnl-market-table").innerHTML = errorCell(4);
  if (el("pnl-asset-table")) el("pnl-asset-table").innerHTML = errorCell(4);
  if (el("rebalance-metrics")) el("rebalance-metrics").innerHTML = errorMetric("Rebalance");
  if (el("rebalance-table")) el("rebalance-table").innerHTML = errorCell(5);
  if (el("market-budget-table")) el("market-budget-table").innerHTML = errorCell(4);
  if (el("strategies-table")) el("strategies-table").innerHTML = errorCell(7);
  if (el("strategy-plan-metrics")) el("strategy-plan-metrics").innerHTML = errorMetric("Strategy Plan");
  if (el("strategy-plan-table")) el("strategy-plan-table").innerHTML = errorCell(5);
  if (el("candidate-metrics")) el("candidate-metrics").innerHTML = errorMetric("Candidates");
  if (el("candidates-table")) el("candidates-table").innerHTML = errorCell(7);
  if (el("candidate-group-metrics")) el("candidate-group-metrics").innerHTML = errorMetric("Research Groups");
  if (el("candidate-groups-table")) el("candidate-groups-table").innerHTML = errorCell(6);
  if (el("market-plan-table")) el("market-plan-table").innerHTML = errorCell(5);
  if (el("plan-table")) el("plan-table").innerHTML = errorCell(8);
  if (el("plan-direction-metrics")) el("plan-direction-metrics").innerHTML = errorMetric("Plan Direction");
  if (el("plan-direction-table")) el("plan-direction-table").innerHTML = errorCell(3);
  if (el("plan-notional-top-table")) el("plan-notional-top-table").innerHTML = errorCell(6);
  if (el("plan-vs-holdings-table")) el("plan-vs-holdings-table").innerHTML = errorCell(6);
  if (el("signal-funnel-metrics")) el("signal-funnel-metrics").innerHTML = errorMetric("Signal Funnel");
  if (el("signal-funnel-table")) el("signal-funnel-table").innerHTML = errorCell(4);
  if (el("execution-blocker-metrics")) el("execution-blocker-metrics").innerHTML = errorMetric("Execution Blockers");
  if (el("execution-blocker-table")) el("execution-blocker-table").innerHTML = errorCell(4);
  if (el("priority-actions-table")) el("priority-actions-table").innerHTML = errorCell(4);
  setList("daily-highlights", [], message);
  setList("weekly-highlights", [], message);
  setList("blockers-list", [], message);
  setList("actions-list", [], message);
  setList("global-blockers-list", [], message);
  setList("global-incidents-list", [], message);
  if (el("report-snapshot-metrics")) el("report-snapshot-metrics").innerHTML = errorMetric("Report Snapshot");
  setList("report-snapshot-list", [], message);
  setList("report-snapshot-cards", [], message);
  if (el("queue-metrics")) el("queue-metrics").innerHTML = errorMetric("Execution Queue");
  setList("queue-approvals-list", [], message);
  setList("queue-orders-list", [], message);
  setList("filled-orders-list", [], message);
  setList("probe-orders-list", [], message);
  if (el("latency-metrics")) el("latency-metrics").innerHTML = errorMetric("Latency");
  if (el("latency-table")) el("latency-table").innerHTML = errorCell(4);
}

function renderDashboard() {
  const sections = [
    renderTabs,
    renderOverview,
    renderAssets,
    renderStrategies,
    renderStrategyPlanBreakdown,
    renderMarketPlanBreakdown,
    renderMarketBudget,
    renderCandidates,
    renderPlan,
    renderSignalFunnel,
    renderExecutionBlockers,
    renderPriorityActions,
    renderSummaries,
  ];
  for (const fn of sections) {
    try { fn(); } catch (err) { console.warn(`[Dashboard] ${fn.name} failed:`, err.message); }
  }
}

let _dashboardLoading = false;

async function loadDashboard() {
  if (_dashboardLoading) return;
  _dashboardLoading = true;
  const btn = document.getElementById("refresh-dashboard");
  if (btn) { btn.classList.add("button--loading"); btn.disabled = true; btn.textContent = "加载中..."; }

  await loadSummary();
  if (state.error) {
    renderError();
    showToast(state.error, "error");
  } else {
    /* renderDashboard already called inside loadSummary for fast first-paint */
    showToast("数据已刷新", "success", 2000);
  }

  if (btn) { btn.classList.remove("button--loading"); btn.disabled = false; btn.textContent = "刷新数据"; }
  _dashboardLoading = false;
}

document.getElementById("refresh-dashboard")?.addEventListener("click", () => {
  loadDashboard();
});

document.querySelectorAll("#account-tabs .tab").forEach((node) => {
  node.addEventListener("click", () => {
    state.activeAccount = node.dataset.account;
    renderTabs();
    /* Smooth transition on tab switch */
    const grid = document.querySelector(".dashboard-grid");
    if (grid) { grid.classList.add("panel--updating"); requestAnimationFrame(() => { renderDashboard(); requestAnimationFrame(() => grid.classList.remove("panel--updating")); }); }
    else { renderDashboard(); }
  });
});

/* Table sorting — click any th to sort */
function enableTableSort() {
  document.querySelectorAll(".data-table th").forEach((th) => {
    th.style.cursor = "pointer";
    th.addEventListener("click", () => {
      const table = th.closest("table");
      const tbody = table.querySelector("tbody");
      const idx = Array.from(th.parentNode.children).indexOf(th);
      const rows = Array.from(tbody.querySelectorAll("tr")).filter((r) => !r.querySelector(".table-empty"));
      if (!rows.length) return;
      const dir = th.dataset.sortDir === "asc" ? "desc" : "asc";
      th.parentNode.querySelectorAll("th").forEach((h) => { delete h.dataset.sortDir; h.classList.remove("sort-asc", "sort-desc"); });
      th.dataset.sortDir = dir;
      th.classList.add(dir === "asc" ? "sort-asc" : "sort-desc");
      rows.sort((a, b) => {
        const at = (a.children[idx]?.textContent ?? "").trim();
        const bt = (b.children[idx]?.textContent ?? "").trim();
        const an = parseFloat(at.replace(/[,%¥$]/g, ""));
        const bn = parseFloat(bt.replace(/[,%¥$]/g, ""));
        if (!isNaN(an) && !isNaN(bn)) return dir === "asc" ? an - bn : bn - an;
        return dir === "asc" ? at.localeCompare(bt, "zh") : bt.localeCompare(at, "zh");
      });
      rows.forEach((r) => tbody.appendChild(r));
    });
  });
}

/* Keyboard shortcuts */
registerShortcut("r", "刷新数据", () => loadDashboard());
registerShortcut("1", "切换到总账户", () => { state.activeAccount = "total"; renderTabs(); renderDashboard(); });
registerShortcut("2", "切换到A股", () => { state.activeAccount = "CN"; renderTabs(); renderDashboard(); });
registerShortcut("3", "切换到港股", () => { state.activeAccount = "HK"; renderTabs(); renderDashboard(); });
registerShortcut("4", "切换到美股", () => { state.activeAccount = "US"; renderTabs(); renderDashboard(); });
registerShortcut("/", "聚焦搜索框", () => { const s = document.querySelector(".table-search"); if (s) { s.focus(); s.scrollIntoView({ behavior: "smooth", block: "center" }); } });
initKeyboardShortcuts();

loadDashboard().then(() => {
  enableTableSort();
  enableTableSearch("search-assets", "assets-table");
  enableTableSearch("search-candidates", "candidates-table");
});

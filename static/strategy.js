function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function fmt(value, digits = 2) {
  if (value == null) return "N/A";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }
  return String(value);
}

function fmtPct(value) {
  if (value == null) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function statusTone(value) {
  if (value === "filled" || value === "approved" || value === "aligned") return "ok";
  if (value === "pending" || value === "warning" || value === "manual" || value === "working") return "warning";
  if (value === "rejected" || value === "expired" || value === "missing" || value === "not_submitted") return "blocked";
  return "empty";
}

function metricTile(label, value, subvalue, tone = "empty") {
  return `
    <article class="metric-tile">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value status-${tone}">${escapeHtml(value)}</span>
      <div class="metric-subvalue">${escapeHtml(subvalue ?? "")}</div>
    </article>
  `;
}

function renderCurve(svgId, points, stroke = "#5cc4ff", fill = "rgba(92, 196, 255, 0.12)") {
  const svg = document.getElementById(svgId);
  if (!svg || !points || !points.length) return;
  const width = 640;
  const height = 240;
  const padding = 18;
  const valueKey = Object.keys(points[0]).find((key) => key !== "index") || "nav";
  const values = points.map((item) => Number(item[valueKey]));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const step = (width - padding * 2) / Math.max(points.length - 1, 1);
  const coords = points.map((item, index) => {
    const x = padding + step * index;
    const y = height - padding - ((Number(item[valueKey]) - min) / spread) * (height - padding * 2);
    return [x, y];
  });
  const line = coords.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  const area = `${line} L ${coords.at(-1)[0].toFixed(2)} ${(height - padding).toFixed(2)} L ${coords[0][0].toFixed(2)} ${(height - padding).toFixed(2)} Z`;
  svg.innerHTML = `
    <path d="${area}" fill="${fill}"></path>
    <path d="${line}" fill="none" stroke="${stroke}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round"></path>
  `;
}

function heatTone(value) {
  if (value == null) return "rgba(22, 32, 43, 0.05)";
  if (value >= 0.03) return "rgba(14, 138, 97, 0.34)";
  if (value >= 0.01) return "rgba(14, 138, 97, 0.22)";
  if (value > 0) return "rgba(14, 138, 97, 0.12)";
  if (value <= -0.03) return "rgba(180, 35, 24, 0.34)";
  if (value <= -0.01) return "rgba(180, 35, 24, 0.22)";
  return "rgba(180, 35, 24, 0.12)";
}

function renderMonthlyHeatmap(rows) {
  const root = document.getElementById("monthly-heatmap");
  if (!root) return;
  const monthLabels = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  if (!rows || !rows.length) {
    root.innerHTML = '<div class="detail-empty">当前没有月度收益数据。</div>';
    return;
  }
  const header = `
    <div class="heatmap-row">
      <div class="heatmap-label">Year</div>
      ${monthLabels.map((label) => `<div class="heatmap-label">${label}</div>`).join("")}
    </div>
  `;
  const body = rows.map((row) => `
    <div class="heatmap-row">
      <div class="heatmap-label">${escapeHtml(row.year)}</div>
      ${monthLabels.map((label) => {
        const value = row.months?.[label];
        return `<div class="heatmap-cell" style="background:${heatTone(value)}">${value == null ? "-" : escapeHtml(fmtPct(value))}</div>`;
      }).join("")}
    </div>
  `).join("");
  root.innerHTML = header + body;
}

function renderYearlyPerformance(rows) {
  const root = document.getElementById("yearly-performance-table");
  if (!root) return;
  if (!rows || !rows.length) {
    root.innerHTML = '<tr><td colspan="4" class="table-empty">当前没有年度对比数据。</td></tr>';
    return;
  }
  root.innerHTML = rows.map((row) => `
    <tr>
      <td>${escapeHtml(row.year)}</td>
      <td class="${(row.strategy_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.strategy_return))}</td>
      <td class="${(row.benchmark_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.benchmark_return))}</td>
      <td class="${(row.excess_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(row.excess_return == null ? "N/A" : fmtPct(row.excess_return))}</td>
    </tr>
  `).join("");
}

function accountLabel(market) {
  return {
    CN: "A股账户",
    HK: "港股账户",
    US: "美股账户",
    total: "总账户",
  }[market] || market;
}

async function loadStrategy() {
  const strategyId = window.location.pathname.split("/").pop();
  const [response, summaryResponse] = await Promise.all([
    fetch(`/research/strategies/${strategyId}`, { headers: { Accept: "application/json" } }),
    fetch("/dashboard/summary", { headers: { Accept: "application/json" } }),
  ]);
  if (!response.ok) {
    document.getElementById("strategy-title").textContent = "策略加载失败";
    document.getElementById("strategy-subtitle").textContent = `${response.status}`;
    return;
  }
  const payload = await response.json();
  const summary = summaryResponse.ok ? await summaryResponse.json() : {};
  const recommendation = payload.recommendation || {};
  const metadata = payload.metadata || {};
  document.getElementById("strategy-title").textContent = payload.strategy_id;
  document.getElementById("strategy-subtitle").textContent = `Verdict: ${recommendation.verdict || "N/A"} / Action: ${recommendation.action || "N/A"}`;
  document.getElementById("detail-updated").textContent = `As of ${payload.as_of}`;
  document.getElementById("strategy-detail-metrics").innerHTML = [
    metricTile("年化收益", fmtPct(payload.metrics.annualized_return), `Profit score ${fmt(recommendation.profitability_score)}`, "ok"),
    metricTile("夏普", fmt(payload.metrics.sharpe), `Calmar ${fmt(payload.metrics.calmar)}`, "ok"),
    metricTile("最大回撤", fmtPct(payload.metrics.max_drawdown), `波动 ${fmtPct(payload.metrics.volatility)}`, "warning"),
    metricTile("验证通过率", fmtPct(recommendation.validation_pass_rate), `稳定性 ${fmt(recommendation.stability_score)}`, "warning"),
    metricTile("容量", fmt(recommendation.capacity_tier), `相关性 ${fmt(recommendation.max_selected_correlation)}`, "warning"),
    metricTile("数据源", fmt(payload.assumptions.data_source), `完整历史 ${fmt(payload.assumptions.history_complete)}`, payload.assumptions.history_complete ? "ok" : "warning"),
  ].join("");
  renderCurve("strategy-nav-curve", payload.nav_curve || []);
  renderCurve("strategy-drawdown-curve", payload.drawdown_curve || [], "#b42318", "rgba(180, 35, 24, 0.12)");
  const benchmark = payload.benchmark || {};
  document.getElementById("benchmark-curve-title").textContent = benchmark.symbol ? `基准净值曲线 (${benchmark.symbol})` : "基准净值曲线";
  renderCurve("strategy-benchmark-curve", benchmark.nav_curve || [], "#6941c6", "rgba(105, 65, 198, 0.12)");
  renderCurve("relative-performance-curve", benchmark.relative_curve || [], "#34d399", "rgba(52, 211, 153, 0.12)");
  renderCurve("rolling-excess-curve", benchmark.rolling_excess_curve || [], "#f79009", "rgba(247, 144, 9, 0.12)");
  document.getElementById("strategy-thesis").textContent = metadata.thesis || "No strategy thesis available.";
  document.getElementById("strategy-meta-list").innerHTML = [
    `名称: ${metadata.name || payload.strategy_id}`,
    `节奏: ${metadata.cadence || "N/A"}`,
    `关注市场: ${(metadata.focus_markets || []).join(", ") || "N/A"}`,
    `当前信号数: ${fmt(payload.signal_count)}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.getElementById("strategy-focus-tags").innerHTML = (metadata.focus_instruments || []).length
    ? (metadata.focus_instruments || []).map((item) => `<span class="tag">${escapeHtml(item)}</span>`).join("")
    : '<span class="detail-empty">当前没有关注标的。</span>';
  document.getElementById("strategy-indicator-list").innerHTML = (metadata.indicators || []).length
    ? (metadata.indicators || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : '<li class="detail-empty">当前没有指标描述。</li>';

  const signalBody = document.getElementById("strategy-signals-table");
  signalBody.innerHTML = (payload.signals || []).length
    ? payload.signals.map((item) => `
        <tr>
          <td>${escapeHtml(item.symbol)}</td>
          <td>${escapeHtml(item.market)}</td>
          <td>${escapeHtml(item.asset_class)}</td>
          <td>${escapeHtml(item.side)}</td>
          <td>${escapeHtml(fmtPct(item.target_weight))}</td>
          <td>${escapeHtml(item.reason)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有信号。</td></tr>';

  const positions = summary.assets?.positions || [];
  const planItems = summary.trading_plan?.items || [];
  const recentOrders = summary.details?.recent_orders || [];
  const recentApprovals = summary.trading_plan?.recent_approvals || [];
  const accounts = summary.accounts || {};
  const strategyPlans = planItems.filter((item) => item.strategy_id === strategyId);
  const implRows = (payload.signals || []).map((item) => {
    const plan = strategyPlans.find((planItem) => planItem.symbol === item.symbol);
    const position = positions.find((holding) => holding.symbol === item.symbol);
    const order = plan ? recentOrders.find((entry) => entry.order_intent_id === plan.intent_id) : null;
    const approval = plan ? recentApprovals.find((entry) => entry.intent_id === plan.intent_id) : null;
    const planState = plan ? fmtPct(plan.target_weight) : "N/A";
    const holdingState = position ? fmtPct(position.weight) : "N/A";
    const orderState = order?.status || (plan ? "not_submitted" : "missing");
    const approvalState = approval?.status || (plan?.requires_approval ? "pending" : "auto");
    return { item, planState, holdingState, orderState, approvalState };
  });
  const submittedCount = implRows.filter((row) => row.orderState !== "missing" && row.orderState !== "not_submitted").length;
  const filledCount = implRows.filter((row) => row.orderState === "filled").length;
  const pendingApprovalCount = implRows.filter((row) => row.approvalState === "pending").length;
  document.getElementById("strategy-implementation-metrics").innerHTML = [
    metricTile("信号", fmt((payload.signals || []).length), "research targets today", (payload.signals || []).length ? "ok" : "warning"),
    metricTile("进计划", fmt(strategyPlans.length), "linked plan rows", strategyPlans.length ? "ok" : "warning"),
    metricTile("已出单", fmt(submittedCount), "recent orders", submittedCount ? "ok" : "warning"),
    metricTile("待审批", fmt(pendingApprovalCount), "manual chain", pendingApprovalCount ? "warning" : "ok"),
  ].join("");
  document.getElementById("strategy-implementation-table").innerHTML = implRows.length
    ? implRows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.item.symbol)}</strong></td>
          <td>${escapeHtml(fmtPct(row.item.target_weight))}</td>
          <td>${escapeHtml(row.planState)}</td>
          <td>${escapeHtml(row.holdingState)}</td>
          <td class="status-${statusTone(row.orderState)}">${escapeHtml(row.orderState)}</td>
          <td class="status-${statusTone(row.approvalState)}">${escapeHtml(row.approvalState)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有今日落地数据。</td></tr>';
  const implSummary = [
    `今日研究信号: ${fmt((payload.signals || []).length)}`,
    `今日已进计划: ${fmt(strategyPlans.length)}`,
    `最近已出单: ${fmt(submittedCount)}`,
    `最近已成交: ${fmt(filledCount)}`,
  ];
  document.getElementById("strategy-implementation-list").innerHTML = implSummary.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const implActions = [];
  if ((payload.signals || []).length > strategyPlans.length) implActions.push("有研究信号尚未进入今日计划。");
  if (pendingApprovalCount > 0) implActions.push("存在待审批计划，需确认人工链路。");
  if (strategyPlans.length > submittedCount) implActions.push("计划单还没完全转成订单状态。");
  if (!implActions.length) implActions.push("今日研究、计划与执行链路基本一致。");
  document.getElementById("strategy-implementation-actions").innerHTML = implActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const accountImpactMetricsNode = document.getElementById("strategy-account-impact-metrics");
  const accountImpactTableNode = document.getElementById("strategy-account-impact-table");
  const accountImpactListNode = document.getElementById("strategy-account-impact-list");
  const accountImpactLinksNode = document.getElementById("strategy-account-impact-links");
  const signalsByMarket = (payload.signals || []).reduce((mapping, item) => {
    mapping[item.market] = (mapping[item.market] || 0) + 1;
    return mapping;
  }, {});
  const exposureByMarket = (payload.signals || []).reduce((mapping, item) => {
    mapping[item.market] = (mapping[item.market] || 0) + Math.abs(Number(item.target_weight || 0));
    return mapping;
  }, {});
  const impactedMarkets = Object.keys(exposureByMarket);
  const totalNav = Number(accounts.total?.nav || 0);
  const accountImpactRows = impactedMarkets.map((market) => {
    const currentWeight = totalNav > 0 ? Number(accounts[market]?.nav || 0) / totalNav : 0;
    const targetWeight = Number(exposureByMarket[market] || 0);
    const delta = targetWeight - currentWeight;
    return {
      market,
      currentWeight,
      targetWeight,
      delta,
      signalCount: Number(signalsByMarket[market] || 0),
    };
  });
  const dominantImpact = [...accountImpactRows].sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta))[0];
  accountImpactMetricsNode.innerHTML = [
    metricTile("影响账户", fmt(accountImpactRows.length), "markets touched", accountImpactRows.length ? "ok" : "warning"),
    metricTile("主账户", accountLabel(dominantImpact?.market || "N/A"), dominantImpact ? `delta ${fmtPct(dominantImpact.delta)}` : "no impact", dominantImpact ? "warning" : "empty"),
    metricTile("目标总暴露", fmtPct(Object.values(exposureByMarket).reduce((sum, value) => sum + Number(value), 0)), "sum of target weights", "ok"),
    metricTile("计划单", fmt(strategyPlans.length), "linked plan rows", strategyPlans.length ? "ok" : "warning"),
  ].join("");
  accountImpactTableNode.innerHTML = accountImpactRows.length
    ? accountImpactRows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(accountLabel(row.market))}</strong></td>
          <td>${escapeHtml(fmtPct(row.currentWeight))}</td>
          <td>${escapeHtml(fmtPct(row.targetWeight))}</td>
          <td class="${Math.abs(row.delta) <= 0.03 ? "status-ok" : row.delta > 0 ? "status-warning" : "status-blocked"}">${escapeHtml(fmtPct(row.delta))}</td>
          <td>${escapeHtml(fmt(row.signalCount))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前策略没有账户影响。</td></tr>';
  accountImpactListNode.innerHTML = accountImpactRows.length
    ? accountImpactRows.map((row) => `<li>${escapeHtml(`${accountLabel(row.market)}: 当前 ${fmtPct(row.currentWeight)} -> 目标 ${fmtPct(row.targetWeight)}，偏离 ${fmtPct(row.delta)}`)}</li>`).join("")
    : '<li class="detail-empty">当前没有账户影响摘要。</li>';
  accountImpactLinksNode.innerHTML = accountImpactRows.length
    ? accountImpactRows.map((row) => `<a class="button" href="/dashboard/accounts/${encodeURIComponent(row.market)}">${escapeHtml(accountLabel(row.market))}</a>`).join("")
    : '<span class="detail-empty">当前没有账户跳转。</span>';

  const windows = document.getElementById("walk-forward-list");
  windows.innerHTML = (payload.walk_forward_windows || []).length
    ? payload.walk_forward_windows.map((item) => `<li>Window ${escapeHtml(item.window_index)}: Sharpe ${escapeHtml(fmt(item.metrics.sharpe))}, MaxDD ${escapeHtml(fmtPct(item.metrics.max_drawdown))}, passed=${escapeHtml(String(item.passed))}</li>`).join("")
    : '<li class="detail-empty">当前没有 walk-forward 明细。</li>';

  const assumptions = document.getElementById("assumption-list");
  assumptions.innerHTML = [
    `data_source: ${payload.assumptions.data_source}`,
    `history_complete: ${payload.assumptions.history_complete}`,
    `history_symbols: ${payload.assumptions.history_symbols}`,
    `missing_history_symbols: ${payload.assumptions.missing_history_symbols}`,
    `commission_bps: ${payload.assumptions.commission_bps}`,
    `slippage_bps: ${payload.assumptions.slippage_bps}`,
    `total_cost_bps: ${payload.assumptions.total_cost_bps}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const split = payload.sample_split || {};
  document.getElementById("sample-split-list").innerHTML = [
    `样本内年化: ${fmtPct(split.in_sample?.annualized_return)}`,
    `样本内夏普: ${fmt(split.in_sample?.sharpe)}`,
    `样本内最大回撤: ${fmtPct(split.in_sample?.max_drawdown)}`,
    `样本外年化: ${fmtPct(split.out_of_sample?.annualized_return)}`,
    `样本外夏普: ${fmt(split.out_of_sample?.sharpe)}`,
    `样本外最大回撤: ${fmtPct(split.out_of_sample?.max_drawdown)}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const coverage = payload.history_coverage || {};
  const reports = coverage.reports || [];
  document.getElementById("coverage-list").innerHTML = [
    `coverage ready: ${coverage.ready}`,
    `minimum ratio: ${fmtPct(coverage.minimum_coverage_ratio)}`,
    ...reports.slice(0, 5).map((item) => `${item.symbol}: ${fmtPct(item.coverage_ratio)} (${item.bar_count}/${item.expected_count})`),
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  renderMonthlyHeatmap(payload.monthly_table || []);
  renderYearlyPerformance(payload.yearly_performance || []);
  document.getElementById("benchmark-list").innerHTML = benchmark.ready
    ? [
        `benchmark: ${benchmark.symbol}`,
        `年化收益: ${fmtPct(benchmark.metrics?.annualized_return)}`,
        `夏普: ${fmt(benchmark.metrics?.sharpe)}`,
        `最大回撤: ${fmtPct(benchmark.metrics?.max_drawdown)}`,
        `是否跑赢: ${fmt(benchmark.comparison?.outperformed)}`,
        `相对超额终值: ${fmtPct((benchmark.relative_curve || []).at(-1)?.excess)}`,
      ].map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : '<li class="detail-empty">当前没有可用基准数据。</li>';
  const reasons = recommendation.reasons || [];
  document.getElementById("verdict-reasons").innerHTML = reasons.length
    ? reasons.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : '<li class="detail-empty">当前没有额外 verdict 理由。</li>';
}

loadStrategy();

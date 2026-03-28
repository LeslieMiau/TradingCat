const state = {
  activeVerdict: "all",
  selectedStrategyId: null,
  strategyDetailCache: {},
};

function renderCorrelationMatrix(matrix) {
  const head = document.getElementById("research-correlation-head");
  const body = document.getElementById("research-correlation-table");
  if (!head || !body) return;
  const ids = matrix?.strategy_ids ?? [];
  const rows = matrix?.rows ?? [];
  if (!ids.length || !rows.length) {
    head.innerHTML = "<tr><th>策略</th></tr>";
    body.innerHTML = '<tr><td class="table-empty">当前没有相关性矩阵。</td></tr>';
    return;
  }
  head.innerHTML = `<tr><th>策略</th>${ids.map((id) => `<th>${escapeHtml(id)}</th>`).join("")}</tr>`;
  body.innerHTML = rows.map((row) => `
    <tr>
      <td><strong>${escapeHtml(row.strategy_id)}</strong></td>
      ${(row.values || []).map((cell) => `<td style="background:${heatTone(Math.abs(Number(cell.value)))}">${escapeHtml(fmt(cell.value))}</td>`).join("")}
    </tr>
  `).join("");
}

function renderAssetCorrelationMatrix(matrixMap) {
  const head = document.getElementById("asset-correlation-head");
  const body = document.getElementById("asset-correlation-table");
  if (!head || !body) return;
  if (!matrixMap || Object.keys(matrixMap).length === 0) {
    head.innerHTML = "<tr><th>资产</th></tr>";
    body.innerHTML = '<tr><td class="table-empty">当前没有大类资产相关性矩阵。</td></tr>';
    return;
  }
  const symbols = Object.keys(matrixMap).sort();
  head.innerHTML = `<tr><th>资产</th>${symbols.map((sym) => `<th>${escapeHtml(sym)}</th>`).join("")}</tr>`;
  body.innerHTML = symbols.map((rowSym) => `
    <tr>
      <td><strong>${escapeHtml(rowSym)}</strong></td>
      ${symbols.map((colSym) => {
        const val = matrixMap[rowSym][colSym] ?? 0;
        return `<td style="background:${heatTone(Math.abs(Number(val)))}">${escapeHtml(fmt(val))}</td>`;
      }).join("")}
    </tr>
  `).join("");
}


function renderRejectSummary(rows) {
  const table = document.getElementById("research-reject-table");
  if (!table) return;
  if (!rows || !rows.length) {
    table.innerHTML = '<tr><td colspan="6" class="table-empty">当前没有需要优先淘汰的策略。</td></tr>';
    return;
  }
  table.innerHTML = rows.map((row) => `
    <tr>
      <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></strong></td>
      <td>${escapeHtml(row.primary_reason)}</td>
      <td>${escapeHtml(fmt(row.reason_count))}</td>
      <td>${escapeHtml(fmt(row.profitability_score))}</td>
      <td>${escapeHtml(fmt(row.max_selected_correlation))}</td>
      <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
    </tr>
  `).join("");
}

function filteredRows(rows) {
  if (state.activeVerdict === "all") return rows || [];
  return (rows || []).filter((row) => row.verdict === state.activeVerdict);
}

function filteredRejectRows(rows) {
  if (state.activeVerdict === "all" || state.activeVerdict === "reject") return rows || [];
  return [];
}

function renderFilterTabs() {
  document.querySelectorAll("#research-filter-tabs .tab").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.verdict === state.activeVerdict);
  });
  const note = document.getElementById("research-filter-note");
  if (note) {
    note.textContent = state.activeVerdict === "all"
      ? "当前显示全部候选"
      : `当前只看 ${state.activeVerdict}`;
  }
}

function renderVerdictGroups(groups) {
  const root = document.getElementById("research-verdict-groups");
  if (!root) return;
  if (!groups || !groups.length) {
    root.innerHTML = '<article class="detail-card"><span class="detail-empty">当前没有分组对照。</span></article>';
    return;
  }
  root.innerHTML = groups.map((group) => `
    <article class="detail-card">
      <h3>${escapeHtml(group.verdict)}</h3>
      <div class="tag-row">
        <span class="badge status-${badgeTone(group.verdict)}">${escapeHtml(group.verdict)}</span>
        <span class="tag">count ${escapeHtml(fmt(group.count))}</span>
      </div>
      <ul class="detail-list">
        <li>平均 Profit Score: ${escapeHtml(fmt(group.average_profitability_score))}</li>
        <li>平均年化: ${escapeHtml(fmtPct(group.average_annualized_return))}</li>
        <li>平均夏普: ${escapeHtml(fmt(group.average_sharpe))}</li>
        <li>平均最大回撤: ${escapeHtml(fmtPct(group.average_max_drawdown))}</li>
      </ul>
      <p class="detail-paragraph">${escapeHtml(group.summary)}</p>
    </article>
  `).join("");
}

function selectStrategy(strategyId) {
  state.selectedStrategyId = strategyId;
  refreshResearch();
}

async function loadStrategyImpact(strategyId) {
  if (!strategyId) return null;
  if (state.strategyDetailCache[strategyId]) {
    return state.strategyDetailCache[strategyId];
  }
  const result = await apiFetch(`/research/strategies/${encodeURIComponent(strategyId)}`);
  if (!result.ok) throw new Error(`strategy detail unavailable: ${strategyId}`);
  state.strategyDetailCache[strategyId] = result.data;
  return result.data;
}

function renderImpact(detail) {
  const title = document.getElementById("impact-title");
  const note = document.getElementById("research-impact-note");
  const accountsList = document.getElementById("impact-accounts-list");
  const summaryList = document.getElementById("impact-summary-list");
  const links = document.getElementById("impact-account-links");
  const accountDeltaTable = document.getElementById("impact-account-delta-table");
  const table = document.getElementById("impact-signals-table");
  const gapTable = document.getElementById("impact-gap-table");
  const gapMetrics = document.getElementById("impact-gap-metrics");
  const offTargetList = document.getElementById("impact-offtarget-list");
  const actionsList = document.getElementById("impact-actions-list");
  const executionMetrics = document.getElementById("impact-execution-metrics");
  const executionTable = document.getElementById("impact-execution-table");
  const blockersList = document.getElementById("impact-blockers-list");
  const progressList = document.getElementById("impact-progress-list");
  const approvalMetrics = document.getElementById("impact-approval-metrics");
  const approvalTable = document.getElementById("impact-approval-table");
  const approvalPendingList = document.getElementById("impact-approval-pending-list");
  const approvalActionsList = document.getElementById("impact-approval-actions-list");
  const timelineSummaryList = document.getElementById("impact-timeline-summary-list");
  const timelineList = document.getElementById("impact-timeline-list");
  const readinessMetrics = document.getElementById("impact-readiness-metrics");
  const readinessList = document.getElementById("impact-readiness-list");
  const readinessActions = document.getElementById("impact-readiness-actions");
  if (!title || !note || !accountsList || !summaryList || !links || !accountDeltaTable || !table || !gapTable || !gapMetrics || !offTargetList || !actionsList || !executionMetrics || !executionTable || !blockersList || !progressList || !approvalMetrics || !approvalTable || !approvalPendingList || !approvalActionsList || !timelineSummaryList || !timelineList || !readinessMetrics || !readinessList || !readinessActions) return;
  if (!detail) {
    title.textContent = "未选择策略";
    note.textContent = "选择一个候选策略，查看会影响哪些账户和信号";
    accountsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    summaryList.innerHTML = '<li class="detail-empty">暂无影响摘要。</li>';
    links.innerHTML = '<span class="detail-empty">暂无账户跳转。</span>';
    accountDeltaTable.innerHTML = '<tr><td colspan="5" class="table-empty">请选择策略。</td></tr>';
    table.innerHTML = '<tr><td colspan="5" class="table-empty">请选择策略。</td></tr>';
    gapTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
    gapMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">差异摘要</span><span class="metric-value">N/A</span></article>';
    offTargetList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    actionsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    executionMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">执行状态</span><span class="metric-value">N/A</span></article>';
    executionTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
    blockersList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    progressList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    approvalMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">人工审批</span><span class="metric-value">N/A</span></article>';
    approvalTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
    approvalPendingList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    approvalActionsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    timelineSummaryList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    timelineList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    readinessMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">推进状态</span><span class="metric-value">N/A</span></article>';
    readinessList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    readinessActions.innerHTML = '<li class="detail-empty">请选择策略。</li>';
    return;
  }
  const accountMap = { CN: "A股账户", HK: "港股账户", US: "美股账户" };
  const signals = detail.signals || [];
  const markets = [...new Set(signals.map((item) => item.market))];
  const grossTarget = signals.reduce((sum, item) => sum + Math.abs(Number(item.target_weight || 0)), 0);
  const approvalCount = signals.filter((item) => item.market === "CN").length;
  const marketExposure = signals.reduce((mapping, item) => {
    const market = item.market || "UNKNOWN";
    mapping[market] = (mapping[market] || 0) + Math.abs(Number(item.target_weight || 0));
    return mapping;
  }, {});
  const dominantMarket = Object.entries(marketExposure).sort((left, right) => Number(right[1]) - Number(left[1]))[0]?.[0] || "N/A";
  const accountSummary = window.__researchDashboardSummary?.accounts || {};
  const totalPositions = window.__researchDashboardSummary?.assets?.positions || [];
  const planItems = window.__researchDashboardSummary?.trading_plan?.items || [];
  const pendingApprovals = window.__researchDashboardSummary?.trading_plan?.pending_approvals || [];
  const recentApprovals = window.__researchDashboardSummary?.trading_plan?.recent_approvals || [];
  const recentOrders = window.__researchDashboardSummary?.details?.recent_orders || [];
  const marketWeightDeltas = markets.map((market) => {
    const account = accountSummary[market];
    const currentWeight = account?.nav && accountSummary.total?.nav
      ? Number(account.nav) / Number(accountSummary.total.nav)
      : 0;
    const targetWeight = Number(marketExposure[market] || 0);
    return {
      market,
      delta: targetWeight - currentWeight,
    };
  });
  title.textContent = detail.strategy_id;
  note.textContent = `当前聚焦 ${detail.strategy_id}，按今日信号预览账户影响`;
  accountsList.innerHTML = markets.length
    ? markets.map((market) => `<li>${escapeHtml(accountMap[market] || market)}</li>`).join("")
    : '<li class="detail-empty">当前没有账户影响。</li>';
  summaryList.innerHTML = [
    `信号数: ${fmt(detail.signal_count)}`,
    `预估计划单数: ${fmt(signals.length)}`,
    `预估审批数: ${fmt(approvalCount)}`,
    `影响账户数: ${fmt(markets.length)}`,
    `目标总暴露: ${fmtPct(grossTarget)}`,
    `主影响账户: ${dominantMarket}`,
    `当前 verdict: ${detail.recommendation?.verdict || "N/A"}`,
    ...marketWeightDeltas.map((item) => `${item.market} 配置偏离: ${fmtPct(item.delta)}`),
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  links.innerHTML = markets.length
    ? markets.map((market) => `<a class="button" href="/dashboard/accounts/${encodeURIComponent(market)}">${escapeHtml(accountMap[market] || market)}</a>`).join("")
    : '<span class="detail-empty">暂无账户跳转。</span>';
  accountDeltaTable.innerHTML = markets.length
    ? markets.map((market) => {
        const account = accountSummary[market];
        const currentWeight = account?.nav && accountSummary.total?.nav
          ? Number(account.nav) / Number(accountSummary.total.nav)
          : 0;
        const targetWeight = Number(marketExposure[market] || 0);
        const delta = targetWeight - currentWeight;
        const marketSignals = signals.filter((item) => item.market === market).length;
        const tone = Math.abs(delta) <= 0.03 ? "status-ok" : delta > 0 ? "status-warning" : "status-blocked";
        return `
          <tr>
            <td><strong>${escapeHtml(accountMap[market] || market)}</strong></td>
            <td>${escapeHtml(fmtPct(currentWeight))}</td>
            <td>${escapeHtml(fmtPct(targetWeight))}</td>
            <td class="${tone}">${escapeHtml(fmtPct(delta))}</td>
            <td>${escapeHtml(fmt(marketSignals))}</td>
          </tr>
        `;
      }).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有账户配置影响。</td></tr>';
  table.innerHTML = signals.length
    ? signals.map((item) => `
        <tr>
          <td><strong>${escapeHtml(item.symbol)}</strong></td>
          <td>${escapeHtml(item.market)}</td>
          <td>${escapeHtml(item.side)}</td>
          <td>${escapeHtml(fmtPct(item.target_weight))}</td>
          <td>${escapeHtml(item.reason)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有信号。</td></tr>';

  const gapRows = signals.length
    ? signals.map((item) => {
        const plan = planItems.find((planItem) => planItem.strategy_id === detail.strategy_id && planItem.symbol === item.symbol);
        const holding = totalPositions.find((position) => position.symbol === item.symbol);
        const planWeight = plan?.target_weight ?? null;
        const holdingWeight = holding?.weight ?? null;
        const gapStatus = planWeight == null
          ? "未进计划"
          : holdingWeight == null
            ? "已进计划，未建仓"
            : Math.abs(Number(item.target_weight || 0) - Number(holdingWeight || 0)) <= 0.02
              ? "接近目标"
              : "持仓未到位";
        const gapClass = gapStatus === "接近目标" ? "status-ok" : gapStatus === "已进计划，未建仓" ? "status-warning" : "status-blocked";
        return `
          <tr>
            <td><strong>${escapeHtml(item.symbol)}</strong></td>
            <td>${escapeHtml(item.market)}</td>
            <td>${escapeHtml(fmtPct(item.target_weight))}</td>
            <td>${escapeHtml(planWeight == null ? "N/A" : fmtPct(planWeight))}</td>
            <td>${escapeHtml(holdingWeight == null ? "N/A" : fmtPct(holdingWeight))}</td>
            <td class="${gapClass}">${escapeHtml(gapStatus)}</td>
          </tr>
        `;
      })
    : [];
  gapTable.innerHTML = gapRows.length
    ? gapRows.join("")
    : '<tr><td colspan="6" class="table-empty">当前没有可对比的信号。</td></tr>';

  const mappedSignals = signals.map((item) => {
    const plan = planItems.find((planItem) => planItem.strategy_id === detail.strategy_id && planItem.symbol === item.symbol);
    const holding = totalPositions.find((position) => position.symbol === item.symbol);
    const planWeight = plan?.target_weight ?? null;
    const holdingWeight = holding?.weight ?? null;
    const gapStatus = planWeight == null
      ? "missing_plan"
      : holdingWeight == null
        ? "plan_no_position"
        : Math.abs(Number(item.target_weight || 0) - Number(holdingWeight || 0)) <= 0.02
          ? "aligned"
          : "under_positioned";
    return { item, plan, holding, planWeight, holdingWeight, gapStatus };
  });
  const missingPlanCount = mappedSignals.filter((row) => row.gapStatus === "missing_plan").length;
  const noPositionCount = mappedSignals.filter((row) => row.gapStatus === "plan_no_position").length;
  const misalignedCount = mappedSignals.filter((row) => row.gapStatus === "under_positioned").length;
  const alignedCount = mappedSignals.filter((row) => row.gapStatus === "aligned").length;
  gapMetrics.innerHTML = [
    metricTile("已对齐", fmt(alignedCount), "signals aligned", alignedCount ? "ok" : "warning"),
    metricTile("未进计划", fmt(missingPlanCount), "research not in plan", missingPlanCount ? "blocked" : "ok"),
    metricTile("未建仓", fmt(noPositionCount), "planned but no position", noPositionCount ? "warning" : "ok"),
    metricTile("未到位", fmt(misalignedCount), "holding gap remains", misalignedCount ? "warning" : "ok"),
  ].join("");

  const offTargetHoldings = totalPositions.filter((position) => markets.includes(position.market) && !signals.some((item) => item.symbol === position.symbol));
  offTargetList.innerHTML = offTargetHoldings.length
    ? offTargetHoldings.slice(0, 6).map((position) => `<li>${escapeHtml(position.symbol)}: 当前权重 ${escapeHtml(fmtPct(position.weight))}</li>`).join("")
    : '<li class="detail-empty">当前没有多余持仓。</li>';

  const actions = [];
  if (missingPlanCount > 0) actions.push(`有 ${missingPlanCount} 个研究信号尚未进入今日计划。`);
  if (noPositionCount > 0) actions.push(`有 ${noPositionCount} 个计划单尚未形成持仓。`);
  if (misalignedCount > 0) actions.push(`有 ${misalignedCount} 个标的当前持仓仍未到目标权重。`);
  if (!actions.length) actions.push("研究信号、计划和当前持仓基本一致。");
  actionsList.innerHTML = actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const strategyPlans = planItems.filter((planItem) => planItem.strategy_id === detail.strategy_id);
  const strategyExecutions = strategyPlans.map((planItem) => {
    const order = recentOrders.find((item) => item.order_intent_id === planItem.intent_id);
    return { planItem, order };
  });
  const submittedCount = strategyExecutions.filter((item) => item.order).length;
  const filledCount = strategyExecutions.filter((item) => item.order?.status === "filled").length;
  const pendingCount = strategyExecutions.filter((item) => item.planItem.requires_approval).length;
  const notSubmittedCount = strategyExecutions.filter((item) => !item.order).length;
  const workingCount = strategyExecutions.filter((item) => item.order && item.order.status !== "filled").length;
  executionMetrics.innerHTML = [
    metricTile("计划单", fmt(strategyPlans.length), "today plan items", strategyPlans.length ? "ok" : "warning"),
    metricTile("已出单", fmt(submittedCount), "recent order linked", submittedCount ? "ok" : "warning"),
    metricTile("已成交", fmt(filledCount), "filled orders", filledCount ? "ok" : "warning"),
    metricTile("待审批", fmt(pendingCount), "requires approval", pendingCount ? "warning" : "ok"),
  ].join("");
  executionTable.innerHTML = strategyExecutions.length
    ? strategyExecutions.map(({ planItem, order }) => `
        <tr>
          <td><strong>${escapeHtml(planItem.symbol)}</strong><br /><span class="meta-text">${escapeHtml(planItem.market)}</span></td>
          <td>${escapeHtml(planItem.side)}</td>
          <td>${escapeHtml(fmt(planItem.quantity, 4))}</td>
          <td>${escapeHtml(planItem.requires_approval ? "manual" : "auto")}</td>
          <td class="${order?.status === "filled" ? "status-ok" : order ? "status-warning" : "status-blocked"}">${escapeHtml(order?.status || "not_submitted")}</td>
          <td>${escapeHtml(order?.filled_quantity == null ? "N/A" : fmt(order.filled_quantity, 4))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前策略今天没有计划单。</td></tr>';

  const blockers = [];
  if (missingPlanCount > 0) blockers.push(`${missingPlanCount} 个研究信号还没进今日计划。`);
  if (pendingCount > 0) blockers.push(`${pendingCount} 笔计划单需要人工审批。`);
  if (notSubmittedCount > 0) blockers.push(`${notSubmittedCount} 笔计划单还没生成订单状态。`);
  if (workingCount > 0) blockers.push(`${workingCount} 笔订单仍在提交/排队中。`);
  if (!blockers.length) blockers.push("当前没有明显执行卡点。");
  blockersList.innerHTML = blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const progress = [
    `研究信号: ${fmt(signals.length)}`,
    `进入计划: ${fmt(strategyPlans.length)}`,
    `生成订单: ${fmt(submittedCount)}`,
    `完成成交: ${fmt(filledCount)}`,
  ];
  progressList.innerHTML = progress.map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const strategyPendingApprovals = pendingApprovals.filter((item) => item.strategy_id === detail.strategy_id);
  const strategyRecentApprovals = recentApprovals.filter((item) => item.strategy_id === detail.strategy_id);
  const approvedCount = strategyRecentApprovals.filter((item) => item.status === "approved").length;
  const rejectedCount = strategyRecentApprovals.filter((item) => item.status === "rejected" || item.status === "expired").length;
  approvalMetrics.innerHTML = [
    metricTile("待审批", fmt(strategyPendingApprovals.length), "pending manual decisions", strategyPendingApprovals.length ? "warning" : "ok"),
    metricTile("最近审批", fmt(strategyRecentApprovals.length), "latest approval records", strategyRecentApprovals.length ? "ok" : "empty"),
    metricTile("已批准", fmt(approvedCount), "approved recently", approvedCount ? "ok" : "empty"),
    metricTile("拒绝/过期", fmt(rejectedCount), "rejected or expired", rejectedCount ? "blocked" : "ok"),
  ].join("");
  approvalTable.innerHTML = strategyRecentApprovals.length
    ? strategyRecentApprovals.map((item) => `
        <tr>
          <td><strong>${escapeHtml(item.symbol)}</strong></td>
          <td>${escapeHtml(item.market)}</td>
          <td>${escapeHtml(item.side)}</td>
          <td>${escapeHtml(fmt(item.quantity, 4))}</td>
          <td class="${item.status === "approved" ? "status-ok" : item.status === "pending" ? "status-warning" : "status-blocked"}">${escapeHtml(item.status)}</td>
          <td>${escapeHtml(item.decision_reason || item.reason || "N/A")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前策略最近没有人工审批记录。</td></tr>';
  approvalPendingList.innerHTML = strategyPendingApprovals.length
    ? strategyPendingApprovals.map((item) => `<li>${escapeHtml(`${item.symbol} ${item.side} ${fmt(item.quantity, 4)}，待审批，理由：${item.reason || "N/A"}`)}</li>`).join("")
    : '<li class="detail-empty">当前策略没有待审批单。</li>';
  const recentApprovalActions = strategyRecentApprovals.slice(0, 5).map((item) => {
    const timestamp = item.decided_at || item.created_at || "";
    return `${item.symbol}: ${item.status}${timestamp ? ` @ ${timestamp}` : ""}`;
  });
  approvalActionsList.innerHTML = recentApprovalActions.length
    ? recentApprovalActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("")
    : '<li class="detail-empty">当前没有最近动作。</li>';

  const timelineEvents = [];
  signals.forEach((item) => {
    timelineEvents.push({
      at: null,
      stage: "signal",
      label: `${item.symbol} 生成研究信号`,
      detail: `${item.side} / 目标 ${fmtPct(item.target_weight)} / ${item.reason}`,
    });
  });
  strategyPlans.forEach((planItem) => {
    timelineEvents.push({
      at: null,
      stage: "plan",
      label: `${planItem.symbol} 进入今日计划`,
      detail: `${planItem.side} ${fmt(planItem.quantity, 4)} / ${planItem.requires_approval ? "manual" : "auto"}`,
    });
  });
  strategyRecentApprovals.forEach((item) => {
    timelineEvents.push({
      at: item.decided_at || item.created_at,
      stage: item.status === "pending" ? "approval_pending" : "approval",
      label: `${item.symbol} 审批 ${item.status}`,
      detail: item.decision_reason || item.reason || "manual approval flow",
    });
  });
  strategyExecutions.forEach(({ planItem, order }) => {
    if (!order) return;
    timelineEvents.push({
      at: order.timestamp,
      stage: order.status === "filled" ? "fill" : "order",
      label: `${planItem.symbol} 订单 ${order.status}`,
      detail: `${planItem.side} / filled ${fmt(order.filled_quantity, 4)} / avg ${order.average_price == null ? "N/A" : fmt(order.average_price, 4)}`,
    });
  });
  const stageWeight = {
    signal: 1,
    plan: 2,
    approval_pending: 3,
    approval: 4,
    order: 5,
    fill: 6,
  };
  const sortedTimeline = timelineEvents.sort((left, right) => {
    const leftHasTime = Boolean(left.at);
    const rightHasTime = Boolean(right.at);
    if (leftHasTime && rightHasTime) return new Date(right.at).getTime() - new Date(left.at).getTime();
    if (leftHasTime) return -1;
    if (rightHasTime) return 1;
    return (stageWeight[right.stage] || 0) - (stageWeight[left.stage] || 0);
  });
  const timelineSummary = [
    `链路事件: ${fmt(sortedTimeline.length)}`,
    `已进入计划: ${fmt(strategyPlans.length)}/${fmt(signals.length)}`,
    `审批事件: ${fmt(strategyRecentApprovals.length)}`,
    `订单事件: ${fmt(strategyExecutions.filter((item) => item.order).length)}`,
  ];
  timelineSummaryList.innerHTML = timelineSummary.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  timelineList.innerHTML = sortedTimeline.length
    ? sortedTimeline.slice(0, 10).map((item) => `<li><strong>${escapeHtml(item.label)}</strong><br /><span class="meta-text">${escapeHtml(fmtTime(item.at))}</span><br />${escapeHtml(item.detail)}</li>`).join("")
    : '<li class="detail-empty">当前策略还没有链路事件。</li>';

  const recommendation = detail.recommendation || {};
  const historyCoverage = detail.history_coverage || {};
  const historyReady = Boolean(historyCoverage.ready);
  const validationReady = Number(recommendation.validation_pass_rate || 0) >= 0.6 && (recommendation.stability_bucket || "") === "stable";
  const correlationReady = Number(recommendation.max_selected_correlation || 0) < 0.7;
  const capacityReady = (recommendation.capacity_tier || "inactive") !== "inactive";
  const executableToday = strategyPlans.length > 0 || signals.length > 0;
  const deployReady = (recommendation.verdict || "") === "deploy_candidate" && historyReady && validationReady && correlationReady;
  readinessMetrics.innerHTML = [
    metricTile("历史覆盖", historyReady ? "ready" : "blocked", `min ${fmtPct(historyCoverage.minimum_coverage_ratio)}`, historyReady ? "ok" : "blocked"),
    metricTile("验证稳定性", validationReady ? "ready" : "warning", `${recommendation.stability_bucket || "N/A"} / pass ${fmtPct(recommendation.validation_pass_rate)}`, validationReady ? "ok" : "warning"),
    metricTile("相关性门槛", correlationReady ? "ready" : "blocked", `max corr ${fmt(recommendation.max_selected_correlation)}`, correlationReady ? "ok" : "blocked"),
    metricTile("推进状态", deployReady ? "deploy" : (recommendation.verdict || "review"), recommendation.action || "N/A", deployReady ? "ok" : "warning"),
  ].join("");
  const readinessItems = [
    `当前 verdict: ${recommendation.verdict || "N/A"}`,
    `研究动作: ${recommendation.action || "N/A"}`,
    `容量层级: ${recommendation.capacity_tier || "N/A"}`,
    `今日可执行: ${executableToday ? "yes" : "no"}`,
    `历史覆盖最小值: ${fmtPct(historyCoverage.minimum_coverage_ratio)}`,
  ];
  readinessList.innerHTML = readinessItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const readinessActionItems = [];
  if (!historyReady) readinessActionItems.push("先补历史数据覆盖，再决定是否推进。");
  if (!validationReady) readinessActionItems.push("先提升样本外验证和稳定性，再考虑 active。");
  if (!correlationReady) readinessActionItems.push("先解决和已选策略的相关性，再谈推进。");
  if (!capacityReady) readinessActionItems.push("当前容量不足，保持 research only。");
  if (!strategyPlans.length && signals.length) readinessActionItems.push("今天有研究信号，但还没形成计划。");
  if (deployReady) readinessActionItems.push("当前已接近 deploy candidate，可继续跟踪计划与执行偏差。");
  if (!readinessActionItems.length) readinessActionItems.push("当前没有新增推进动作。");
  readinessActions.innerHTML = readinessActionItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

async function loadPayloads() {
  const [dashboardRes, activeRes, candidateRes, assetCorrRes] = await Promise.all([
    apiFetch("/dashboard/summary"),
    apiFetch("/research/scorecard/run", { method: "POST" }),
    apiFetch("/research/candidates/scorecard", { method: "POST" }),
    apiFetch("/research/correlation", { 
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: ["SPY", "QQQ", "IWM", "EEM", "GLD", "TLT", "USO"] })
    }),
  ]);
  if (!dashboardRes.ok) throw new Error(dashboardRes.error);
  return {
    dashboard: dashboardRes.data,
    active: activeRes.data ?? {},
    candidates: candidateRes.data ?? {},
    assetCorrelations: assetCorrRes.data ?? {},
  };
}

function bindStrategyPickers() {
  document.querySelectorAll("[data-strategy-pick]").forEach((node) => {
    node.addEventListener("click", (event) => {
      event.preventDefault();
      selectStrategy(node.dataset.strategyPick || null);
    });
  });
}

function renderResearch(payload) {
  const activeRows = payload.dashboard?.strategies?.rows ?? [];
  const candidateRows = filteredRows(payload.candidates?.rows ?? []);
  const topRows = filteredRows(payload.dashboard?.candidates?.top_candidates ?? []);
  const rejectRows = filteredRejectRows(payload.candidates?.reject_summary ?? []);

  renderFilterTabs();

  document.getElementById("research-updated").textContent = `Updated ${new Date().toLocaleString()}`;
  document.getElementById("research-overview-metrics").innerHTML = [
    metricTile("执行策略", fmt(activeRows.length), `accepted ${(payload.dashboard?.strategies?.accepted_strategy_ids ?? []).length}`, activeRows.length ? "ok" : "warning"),
    metricTile("候选 deploy", fmt(payload.candidates?.deploy_candidate_count), "worth deeper study", payload.candidates?.deploy_candidate_count ? "ok" : "warning"),
    metricTile("候选 paper", fmt(payload.candidates?.paper_only_count), "needs more evidence", payload.candidates?.paper_only_count ? "warning" : "ok"),
    metricTile("候选 reject", fmt(payload.candidates?.rejected_count), "cut losers faster", payload.candidates?.rejected_count ? "blocked" : "ok"),
  ].join("");

  const topCards = document.getElementById("research-top-cards");
  topCards.innerHTML = topRows.length
    ? topRows.map((row) => `
        <article class="detail-card">
          <h3><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></h3>
          <p class="detail-paragraph">Verdict ${escapeHtml(row.verdict)} / Profit score ${escapeHtml(fmt(row.profitability_score))}</p>
          <div class="tag-row">
            <span class="badge status-${badgeTone(row.verdict)}">${escapeHtml(row.verdict)}</span>
            <span class="tag">Sharpe ${escapeHtml(fmt(row.sharpe))}</span>
            <span class="tag">CAGR ${escapeHtml(fmtPct(row.annualized_return))}</span>
            <button class="button" data-strategy-pick="${escapeHtml(row.strategy_id)}" type="button">查看影响</button>
          </div>
        </article>
      `).join("")
    : '<article class="detail-card"><span class="detail-empty">当前没有 top picks。</span></article>';

  renderVerdictGroups(payload.candidates?.verdict_groups);

  const activeTable = document.getElementById("research-active-table");
  activeTable.innerHTML = activeRows.length
    ? activeRows.map((row) => `
        <tr>
          <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.name)}</a></strong><br /><span class="meta-text">${escapeHtml(row.strategy_id)}</span></td>
          <td><span class="badge status-${badgeTone(row.action)}">${escapeHtml(row.action)}</span></td>
          <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
          <td>${escapeHtml(fmt(row.sharpe))}</td>
          <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
          <td>${escapeHtml(`${row.stability_bucket} / pass ${fmtPct(row.validation_pass_rate)}`)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前没有 active 研究策略。</td></tr>';

  setList("research-actions", payload.candidates?.next_actions ?? [], "当前没有新的研究动作。");
  setList(
    "research-buckets",
    [
      `deploy_candidate: ${fmt(payload.candidates?.deploy_candidate_count)}`,
      `paper_only: ${fmt(payload.candidates?.paper_only_count)}`,
      `reject: ${fmt(payload.candidates?.rejected_count)}`,
    ],
    "当前没有候选池分布。",
  );

  const candidateTable = document.getElementById("research-candidate-table");
  candidateTable.innerHTML = candidateRows.length
    ? candidateRows.map((row) => `
        <tr>
          <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></strong><br /><button class="button" data-strategy-pick="${escapeHtml(row.strategy_id)}" type="button">查看影响</button></td>
          <td><span class="badge status-${badgeTone(row.verdict)}">${escapeHtml(row.verdict)}</span></td>
          <td>${escapeHtml(fmt(row.profitability_score))}</td>
          <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
          <td>${escapeHtml(fmt(row.sharpe))}</td>
          <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
          <td>${escapeHtml(row.capacity_tier)}</td>
          <td>${escapeHtml(fmt(row.max_selected_correlation))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="8" class="table-empty">当前没有候选池评分。</td></tr>';

  renderCorrelationMatrix(payload.candidates?.correlation_matrix);
  renderAssetCorrelationMatrix(payload.assetCorrelations);
  renderRejectSummary(rejectRows);
  bindStrategyPickers();
}

async function refreshResearch() {
  try {
    const payload = await loadPayloads();
    window.__researchDashboardSummary = payload.dashboard;
    renderResearch(payload);
    if (!state.selectedStrategyId) {
      const defaultStrategyId = filteredRows(payload.candidates?.rows ?? [])[0]?.strategy_id || null;
      state.selectedStrategyId = defaultStrategyId;
    }
    const detail = await loadStrategyImpact(state.selectedStrategyId);
    renderImpact(detail);
  } catch (error) {
    document.getElementById("research-overview-metrics").innerHTML = metricTile("Research Error", "Unavailable", error.message, "blocked");
    renderImpact(null);
  }
}

document.getElementById("refresh-research")?.addEventListener("click", refreshResearch);
document.querySelectorAll("#research-filter-tabs .tab").forEach((node) => {
  node.addEventListener("click", () => {
    state.activeVerdict = node.dataset.verdict || "all";
    refreshResearch();
  });
});

refreshResearch();

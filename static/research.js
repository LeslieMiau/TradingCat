const state = {
  activeVerdict: "all",
  selectedStrategyId: null,
  strategyDetailCache: {},
};

function marketAwarenessTone(value) {
  if (["bullish", "build_risk", "supportive", "high", "complete"].includes(value)) return "ok";
  if (["neutral", "caution", "hold_pace", "mixed", "medium", "degraded", "hedged"].includes(value)) return "warning";
  if (["risk_off", "pause_new_adds", "reduce_risk", "blocked", "low", "fallback", "defensive"].includes(value)) return "blocked";
  return "empty";
}

function marketAwarenessSnapshot(payload) {
  return payload.marketAwareness || payload.dashboard?.details?.market_awareness || null;
}

function renderMarketAwareness(payload, errorMessage = null) {
  const noteEl = document.getElementById("research-market-awareness-note");
  const metricsEl = document.getElementById("research-market-awareness-metrics");
  const badgesEl = document.getElementById("research-market-awareness-badges");
  const actionsEl = document.getElementById("research-market-awareness-actions");
  const guidanceEl = document.getElementById("research-market-awareness-guidance");
  const blockersEl = document.getElementById("research-market-awareness-blockers");
  const cardsEl = document.getElementById("research-market-awareness-market-cards");
  const evidenceEl = document.getElementById("research-market-awareness-evidence-table");
  if (!noteEl || !metricsEl || !badgesEl || !actionsEl || !guidanceEl || !blockersEl || !cardsEl || !evidenceEl) {
    return;
  }

  const snapshot = marketAwarenessSnapshot(payload);
  const dataQuality = snapshot?.data_quality ?? {};
  const marketViews = Array.isArray(snapshot?.market_views) ? snapshot.market_views : [];
  const actions = Array.isArray(snapshot?.actions) ? snapshot.actions : [];
  const guidanceRows = Array.isArray(snapshot?.strategy_guidance) ? snapshot.strategy_guidance : [];
  const blockers = [
    `数据状态: ${dataQuality.status || (snapshot ? "unknown" : "missing")}`,
    ...(dataQuality.degraded ? ["当前结果为降级输出，先把它当作节奏参考。"] : []),
    ...(dataQuality.fallback_driven ? ["部分证据来自 fallback 路径，置信度需要保守看待。"] : []),
    ...((dataQuality.blockers || []).map((item) => `阻塞: ${item}`)),
    ...((dataQuality.missing_symbols || []).slice(0, 5).map((item) => `缺失标的: ${item}`)),
    ...((dataQuality.adapter_limitations || []).slice(0, 5).map((item) => `适配器限制: ${item}`)),
  ];

  if (!snapshot || errorMessage) {
    noteEl.textContent = errorMessage || "市场感知暂不可用";
    metricsEl.innerHTML = [
      metricTile("Regime", "Unavailable", "market awareness missing", "blocked"),
      metricTile("Confidence", "N/A", "waiting for snapshot", "empty"),
      metricTile("Posture", "N/A", "no operator guidance", "empty"),
      metricTile("Data", errorMessage ? "error" : "missing", errorMessage || "snapshot unavailable", "blocked"),
    ].join("");
    badgesEl.innerHTML = '<span class="detail-empty">当前没有可用的市场感知摘要。</span>';
    setList("research-market-awareness-actions", [], errorMessage || "当前没有可用动作建议。");
    setList("research-market-awareness-guidance", [], errorMessage || "当前没有可用策略建议。");
    setList("research-market-awareness-blockers", blockers, errorMessage || "当前没有可用数据状态。");
    cardsEl.innerHTML = '<article class="detail-card"><span class="detail-empty">当前没有市场视角卡片。</span></article>';
    evidenceEl.innerHTML = '<tr><td colspan="5" class="table-empty">当前没有市场感知证据。</td></tr>';
    return;
  }

  noteEl.textContent = `截至 ${snapshot.as_of}，仅作仓位与节奏建议，不会自动下单`;
  metricsEl.innerHTML = [
    metricTile("Regime", snapshot.overall_regime || "N/A", `score ${fmt(snapshot.overall_score)}`, marketAwarenessTone(snapshot.overall_regime)),
    metricTile("Confidence", snapshot.confidence || "N/A", `markets ${fmt(marketViews.length)}`, marketAwarenessTone(snapshot.confidence)),
    metricTile("Posture", snapshot.risk_posture || "N/A", "operator pace", marketAwarenessTone(snapshot.risk_posture)),
    metricTile("Data", dataQuality.status || "unknown", dataQuality.degraded ? "degraded snapshot" : "snapshot ready", marketAwarenessTone(dataQuality.status)),
  ].join("");
  badgesEl.innerHTML = [
    `<span class="badge status-${marketAwarenessTone(snapshot.overall_regime)}">${escapeHtml(snapshot.overall_regime || "N/A")}</span>`,
    `<span class="badge status-${marketAwarenessTone(snapshot.confidence)}">${escapeHtml(snapshot.confidence || "N/A")} confidence</span>`,
    `<span class="badge status-${marketAwarenessTone(snapshot.risk_posture)}">${escapeHtml(snapshot.risk_posture || "N/A")}</span>`,
  ].join("");
  setList(
    "research-market-awareness-actions",
    actions.map((item) => `${item.text} (${item.rationale})`),
    "当前没有新增操作建议。",
  );
  setList(
    "research-market-awareness-guidance",
    guidanceRows.map((item) => `${item.strategy_id}: ${item.stance} - ${item.summary}`),
    "当前没有策略级建议。",
  );
  setList(
    "research-market-awareness-blockers",
    blockers.length ? blockers : ["市场感知数据完整，可直接作为计划参考。"],
    "市场感知数据完整，可直接作为计划参考。",
  );

  cardsEl.innerHTML = marketViews.length
    ? marketViews.map((view) => `
        <article class="detail-card">
          <h3>${escapeHtml(view.market)} / ${escapeHtml(view.benchmark_symbol)}</h3>
          <div class="tag-row">
            <span class="badge status-${marketAwarenessTone(view.regime)}">${escapeHtml(view.regime)}</span>
            <span class="badge status-${marketAwarenessTone(view.confidence)}">${escapeHtml(view.confidence)}</span>
            <span class="badge status-${marketAwarenessTone(view.risk_posture)}">${escapeHtml(view.risk_posture)}</span>
          </div>
          <ul class="detail-list">
            <li>breadth: ${escapeHtml(fmtPct(view.breadth_ratio))}</li>
            <li>momentum 21d: ${escapeHtml(fmtPct(view.momentum_21d))}</li>
            <li>drawdown 20d: ${escapeHtml(fmtPct(view.drawdown_20d))}</li>
            <li>vol 20d: ${escapeHtml(fmtPct(view.realized_volatility_20d))}</li>
          </ul>
        </article>
      `).join("")
    : '<article class="detail-card"><span class="detail-empty">当前没有逐市场视角。</span></article>';

  const evidenceRows = marketViews.flatMap((view) => (view.evidence || []).map((row) => ({
    market: row.market || view.market,
    label: row.label,
    status: row.status,
    value: row.value,
    unit: row.unit,
    explanation: row.explanation,
  })));
  evidenceEl.innerHTML = evidenceRows.length
    ? evidenceRows.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.market)}</strong></td>
          <td>${escapeHtml(row.label)}</td>
          <td><span class="badge status-${marketAwarenessTone(row.status)}">${escapeHtml(row.status)}</span></td>
          <td>${escapeHtml(row.unit === "ratio" ? fmtPct(row.value) : fmt(row.value))}</td>
          <td>${escapeHtml(row.explanation)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有市场感知证据。</td></tr>';
}

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
  const result = await apiFetch(API.researchStrategies(strategyId));
  if (!result.ok) throw new Error(`strategy detail unavailable: ${strategyId}`);
  state.strategyDetailCache[strategyId] = result.data;
  return result.data;
}

function impactElements() {
  const ids = {
    title: "impact-title",
    note: "research-impact-note",
    accountsList: "impact-accounts-list",
    summaryList: "impact-summary-list",
    links: "impact-account-links",
    accountDeltaTable: "impact-account-delta-table",
    signalsTable: "impact-signals-table",
    gapTable: "impact-gap-table",
    gapMetrics: "impact-gap-metrics",
    offTargetList: "impact-offtarget-list",
    actionsList: "impact-actions-list",
    executionMetrics: "impact-execution-metrics",
    executionTable: "impact-execution-table",
    blockersList: "impact-blockers-list",
    progressList: "impact-progress-list",
    approvalMetrics: "impact-approval-metrics",
    approvalTable: "impact-approval-table",
    approvalPendingList: "impact-approval-pending-list",
    approvalActionsList: "impact-approval-actions-list",
    timelineSummaryList: "impact-timeline-summary-list",
    timelineList: "impact-timeline-list",
    readinessMetrics: "impact-readiness-metrics",
    readinessList: "impact-readiness-list",
    readinessActions: "impact-readiness-actions",
  };
  const elements = Object.fromEntries(Object.entries(ids).map(([key, id]) => [key, document.getElementById(id)]));
  return Object.values(elements).every(Boolean) ? elements : null;
}

function renderImpactEmpty(elements) {
  elements.title.textContent = "未选择策略";
  elements.note.textContent = "选择一个候选策略，查看会影响哪些账户和信号";
  elements.accountsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.summaryList.innerHTML = '<li class="detail-empty">暂无影响摘要。</li>';
  elements.links.innerHTML = '<span class="detail-empty">暂无账户跳转。</span>';
  elements.accountDeltaTable.innerHTML = '<tr><td colspan="5" class="table-empty">请选择策略。</td></tr>';
  elements.signalsTable.innerHTML = '<tr><td colspan="5" class="table-empty">请选择策略。</td></tr>';
  elements.gapTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
  elements.gapMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">差异摘要</span><span class="metric-value">N/A</span></article>';
  elements.offTargetList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.actionsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.executionMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">执行状态</span><span class="metric-value">N/A</span></article>';
  elements.executionTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
  elements.blockersList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.progressList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.approvalMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">人工审批</span><span class="metric-value">N/A</span></article>';
  elements.approvalTable.innerHTML = '<tr><td colspan="6" class="table-empty">请选择策略。</td></tr>';
  elements.approvalPendingList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.approvalActionsList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.timelineSummaryList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.timelineList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.readinessMetrics.innerHTML = '<article class="metric-tile"><span class="metric-label">推进状态</span><span class="metric-value">N/A</span></article>';
  elements.readinessList.innerHTML = '<li class="detail-empty">请选择策略。</li>';
  elements.readinessActions.innerHTML = '<li class="detail-empty">请选择策略。</li>';
}

function buildImpactContext(detail) {
  const dashboardSummary = state.dashboardSummary || {};
  const signals = detail.signals || [];
  const planItems = dashboardSummary.trading_plan?.items || [];
  const pendingApprovals = dashboardSummary.trading_plan?.pending_approvals || [];
  const recentApprovals = dashboardSummary.trading_plan?.recent_approvals || [];
  const recentOrders = dashboardSummary.details?.recent_orders || [];
  const marketExposure = signals.reduce((mapping, item) => {
    const market = item.market || "UNKNOWN";
    mapping[market] = (mapping[market] || 0) + Math.abs(Number(item.target_weight || 0));
    return mapping;
  }, {});
  const strategyPlans = planItems.filter((item) => item.strategy_id === detail.strategy_id);
  return {
    detail,
    signals,
    markets: [...new Set(signals.map((item) => item.market))],
    accountMap: { CN: "A股账户", HK: "港股账户", US: "美股账户" },
    accountSummary: dashboardSummary.accounts || {},
    totalPositions: dashboardSummary.assets?.positions || [],
    planItems,
    pendingApprovals,
    recentApprovals,
    recentOrders,
    marketExposure,
    strategyPlans,
    strategyExecutions: strategyPlans.map((planItem) => ({
      planItem,
      order: recentOrders.find((item) => item.order_intent_id === planItem.intent_id),
    })),
    strategyPendingApprovals: pendingApprovals.filter((item) => item.strategy_id === detail.strategy_id),
    strategyRecentApprovals: recentApprovals.filter((item) => item.strategy_id === detail.strategy_id),
  };
}

function buildGapSummary(context) {
  const mappedSignals = context.signals.map((item) => {
    const plan = context.planItems.find((planItem) => planItem.strategy_id === context.detail.strategy_id && planItem.symbol === item.symbol);
    const holding = context.totalPositions.find((position) => position.symbol === item.symbol);
    const holdingWeight = holding?.weight ?? null;
    const gapStatus = plan?.target_weight == null
      ? "missing_plan"
      : holdingWeight == null
        ? "plan_no_position"
        : Math.abs(Number(item.target_weight || 0) - Number(holdingWeight || 0)) <= 0.02
          ? "aligned"
          : "under_positioned";
    return { item, planWeight: plan?.target_weight ?? null, holdingWeight, gapStatus };
  });
  return {
    mappedSignals,
    missingPlanCount: mappedSignals.filter((row) => row.gapStatus === "missing_plan").length,
    noPositionCount: mappedSignals.filter((row) => row.gapStatus === "plan_no_position").length,
    misalignedCount: mappedSignals.filter((row) => row.gapStatus === "under_positioned").length,
    alignedCount: mappedSignals.filter((row) => row.gapStatus === "aligned").length,
  };
}

function buildExecutionSummary(context) {
  const submittedCount = context.strategyExecutions.filter((item) => item.order).length;
  const filledCount = context.strategyExecutions.filter((item) => item.order?.status === "filled").length;
  const pendingCount = context.strategyExecutions.filter((item) => item.planItem.requires_approval).length;
  const notSubmittedCount = context.strategyExecutions.filter((item) => !item.order).length;
  const workingCount = context.strategyExecutions.filter((item) => item.order && item.order.status !== "filled").length;
  return { submittedCount, filledCount, pendingCount, notSubmittedCount, workingCount };
}

function buildApprovalSummary(context) {
  const approvedCount = context.strategyRecentApprovals.filter((item) => item.status === "approved").length;
  const rejectedCount = context.strategyRecentApprovals.filter((item) => item.status === "rejected" || item.status === "expired").length;
  const recentApprovalActions = context.strategyRecentApprovals.slice(0, 5).map((item) => {
    const timestamp = item.decided_at || item.created_at || "";
    return `${item.symbol}: ${item.status}${timestamp ? ` @ ${timestamp}` : ""}`;
  });
  return { approvedCount, rejectedCount, recentApprovalActions };
}

function renderImpactHeader(elements, context) {
  const grossTarget = context.signals.reduce((sum, item) => sum + Math.abs(Number(item.target_weight || 0)), 0);
  const approvalCount = context.signals.filter((item) => item.market === "CN").length;
  const dominantMarket = Object.entries(context.marketExposure).sort((left, right) => Number(right[1]) - Number(left[1]))[0]?.[0] || "N/A";
  const marketWeightDeltas = context.markets.map((market) => {
    const currentWeight = context.accountSummary[market]?.nav && context.accountSummary.total?.nav
      ? Number(context.accountSummary[market].nav) / Number(context.accountSummary.total.nav)
      : 0;
    return { market, currentWeight, targetWeight: Number(context.marketExposure[market] || 0) };
  });
  elements.title.textContent = context.detail.strategy_id;
  elements.note.textContent = `当前聚焦 ${context.detail.strategy_id}，按今日信号预览账户影响`;
  elements.accountsList.innerHTML = context.markets.length ? context.markets.map((market) => `<li>${escapeHtml(context.accountMap[market] || market)}</li>`).join("") : '<li class="detail-empty">当前没有账户影响。</li>';
  elements.summaryList.innerHTML = [`信号数: ${fmt(context.detail.signal_count)}`, `预估计划单数: ${fmt(context.signals.length)}`, `预估审批数: ${fmt(approvalCount)}`, `影响账户数: ${fmt(context.markets.length)}`, `目标总暴露: ${fmtPct(grossTarget)}`, `主影响账户: ${dominantMarket}`, `当前 verdict: ${context.detail.recommendation?.verdict || "N/A"}`, ...marketWeightDeltas.map((item) => `${item.market} 配置偏离: ${fmtPct(item.targetWeight - item.currentWeight)}`)].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  elements.links.innerHTML = context.markets.length ? context.markets.map((market) => `<a class="button" href="/dashboard/accounts/${encodeURIComponent(market)}">${escapeHtml(context.accountMap[market] || market)}</a>`).join("") : '<span class="detail-empty">暂无账户跳转。</span>';
  elements.accountDeltaTable.innerHTML = marketWeightDeltas.length ? marketWeightDeltas.map((item) => `<tr><td><strong>${escapeHtml(context.accountMap[item.market] || item.market)}</strong></td><td>${escapeHtml(fmtPct(item.currentWeight))}</td><td>${escapeHtml(fmtPct(item.targetWeight))}</td><td class="${Math.abs(item.targetWeight - item.currentWeight) <= 0.03 ? "status-ok" : item.targetWeight > item.currentWeight ? "status-warning" : "status-blocked"}">${escapeHtml(fmtPct(item.targetWeight - item.currentWeight))}</td><td>${escapeHtml(fmt(context.signals.filter((signal) => signal.market === item.market).length))}</td></tr>`).join("") : '<tr><td colspan="5" class="table-empty">当前没有账户配置影响。</td></tr>';
  elements.signalsTable.innerHTML = context.signals.length ? context.signals.map((item) => `<tr><td><strong>${escapeHtml(item.symbol)}</strong></td><td>${escapeHtml(item.market)}</td><td>${escapeHtml(item.side)}</td><td>${escapeHtml(fmtPct(item.target_weight))}</td><td>${escapeHtml(item.reason)}</td></tr>`).join("") : '<tr><td colspan="5" class="table-empty">当前没有信号。</td></tr>';
}

function renderImpactGap(elements, context, gapSummary) {
  elements.gapTable.innerHTML = gapSummary.mappedSignals.length ? gapSummary.mappedSignals.map((row) => {
    const gapLabel = row.gapStatus === "missing_plan" ? "未进计划" : row.gapStatus === "plan_no_position" ? "已进计划，未建仓" : row.gapStatus === "aligned" ? "接近目标" : "持仓未到位";
    const gapClass = gapLabel === "接近目标" ? "status-ok" : gapLabel === "已进计划，未建仓" ? "status-warning" : "status-blocked";
    return `<tr><td><strong>${escapeHtml(row.item.symbol)}</strong></td><td>${escapeHtml(row.item.market)}</td><td>${escapeHtml(fmtPct(row.item.target_weight))}</td><td>${escapeHtml(row.planWeight == null ? "N/A" : fmtPct(row.planWeight))}</td><td>${escapeHtml(row.holdingWeight == null ? "N/A" : fmtPct(row.holdingWeight))}</td><td class="${gapClass}">${escapeHtml(gapLabel)}</td></tr>`;
  }).join("") : '<tr><td colspan="6" class="table-empty">当前没有可对比的信号。</td></tr>';
  elements.gapMetrics.innerHTML = [metricTile("已对齐", fmt(gapSummary.alignedCount), "signals aligned", gapSummary.alignedCount ? "ok" : "warning"), metricTile("未进计划", fmt(gapSummary.missingPlanCount), "research not in plan", gapSummary.missingPlanCount ? "blocked" : "ok"), metricTile("未建仓", fmt(gapSummary.noPositionCount), "planned but no position", gapSummary.noPositionCount ? "warning" : "ok"), metricTile("未到位", fmt(gapSummary.misalignedCount), "holding gap remains", gapSummary.misalignedCount ? "warning" : "ok")].join("");
  const offTargetHoldings = context.totalPositions.filter((position) => context.markets.includes(position.market) && !context.signals.some((item) => item.symbol === position.symbol));
  elements.offTargetList.innerHTML = offTargetHoldings.length ? offTargetHoldings.slice(0, 6).map((position) => `<li>${escapeHtml(position.symbol)}: 当前权重 ${escapeHtml(fmtPct(position.weight))}</li>`).join("") : '<li class="detail-empty">当前没有多余持仓。</li>';
  const actions = [];
  if (gapSummary.missingPlanCount > 0) actions.push(`有 ${gapSummary.missingPlanCount} 个研究信号尚未进入今日计划。`);
  if (gapSummary.noPositionCount > 0) actions.push(`有 ${gapSummary.noPositionCount} 个计划单尚未形成持仓。`);
  if (gapSummary.misalignedCount > 0) actions.push(`有 ${gapSummary.misalignedCount} 个标的当前持仓仍未到目标权重。`);
  if (!actions.length) actions.push("研究信号、计划和当前持仓基本一致。");
  elements.actionsList.innerHTML = actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderImpactExecution(elements, context, gapSummary, executionSummary) {
  elements.executionMetrics.innerHTML = [metricTile("计划单", fmt(context.strategyPlans.length), "today plan items", context.strategyPlans.length ? "ok" : "warning"), metricTile("已出单", fmt(executionSummary.submittedCount), "recent order linked", executionSummary.submittedCount ? "ok" : "warning"), metricTile("已成交", fmt(executionSummary.filledCount), "filled orders", executionSummary.filledCount ? "ok" : "warning"), metricTile("待审批", fmt(executionSummary.pendingCount), "requires approval", executionSummary.pendingCount ? "warning" : "ok")].join("");
  elements.executionTable.innerHTML = context.strategyExecutions.length ? context.strategyExecutions.map(({ planItem, order }) => `<tr><td><strong>${escapeHtml(planItem.symbol)}</strong><br /><span class="meta-text">${escapeHtml(planItem.market)}</span></td><td>${escapeHtml(planItem.side)}</td><td>${escapeHtml(fmt(planItem.quantity, 4))}</td><td>${escapeHtml(planItem.requires_approval ? "manual" : "auto")}</td><td class="${order?.status === "filled" ? "status-ok" : order ? "status-warning" : "status-blocked"}">${escapeHtml(order?.status || "not_submitted")}</td><td>${escapeHtml(order?.filled_quantity == null ? "N/A" : fmt(order.filled_quantity, 4))}</td></tr>`).join("") : '<tr><td colspan="6" class="table-empty">当前策略今天没有计划单。</td></tr>';
  const blockers = [];
  if (gapSummary.missingPlanCount > 0) blockers.push(`${gapSummary.missingPlanCount} 个研究信号还没进今日计划。`);
  if (executionSummary.pendingCount > 0) blockers.push(`${executionSummary.pendingCount} 笔计划单需要人工审批。`);
  if (executionSummary.notSubmittedCount > 0) blockers.push(`${executionSummary.notSubmittedCount} 笔计划单还没生成订单状态。`);
  if (executionSummary.workingCount > 0) blockers.push(`${executionSummary.workingCount} 笔订单仍在提交/排队中。`);
  if (!blockers.length) blockers.push("当前没有明显执行卡点。");
  elements.blockersList.innerHTML = blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  elements.progressList.innerHTML = [`研究信号: ${fmt(context.signals.length)}`, `进入计划: ${fmt(context.strategyPlans.length)}`, `生成订单: ${fmt(executionSummary.submittedCount)}`, `完成成交: ${fmt(executionSummary.filledCount)}`].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderImpactApproval(elements, context, approvalSummary) {
  elements.approvalMetrics.innerHTML = [metricTile("待审批", fmt(context.strategyPendingApprovals.length), "pending manual decisions", context.strategyPendingApprovals.length ? "warning" : "ok"), metricTile("最近审批", fmt(context.strategyRecentApprovals.length), "latest approval records", context.strategyRecentApprovals.length ? "ok" : "empty"), metricTile("已批准", fmt(approvalSummary.approvedCount), "approved recently", approvalSummary.approvedCount ? "ok" : "empty"), metricTile("拒绝/过期", fmt(approvalSummary.rejectedCount), "rejected or expired", approvalSummary.rejectedCount ? "blocked" : "ok")].join("");
  elements.approvalTable.innerHTML = context.strategyRecentApprovals.length ? context.strategyRecentApprovals.map((item) => `<tr><td><strong>${escapeHtml(item.symbol)}</strong></td><td>${escapeHtml(item.market)}</td><td>${escapeHtml(item.side)}</td><td>${escapeHtml(fmt(item.quantity, 4))}</td><td class="${item.status === "approved" ? "status-ok" : item.status === "pending" ? "status-warning" : "status-blocked"}">${escapeHtml(item.status)}</td><td>${escapeHtml(item.decision_reason || item.reason || "N/A")}</td></tr>`).join("") : '<tr><td colspan="6" class="table-empty">当前策略最近没有人工审批记录。</td></tr>';
  elements.approvalPendingList.innerHTML = context.strategyPendingApprovals.length ? context.strategyPendingApprovals.map((item) => `<li>${escapeHtml(`${item.symbol} ${item.side} ${fmt(item.quantity, 4)}，待审批，理由：${item.reason || "N/A"}`)}</li>`).join("") : '<li class="detail-empty">当前策略没有待审批单。</li>';
  elements.approvalActionsList.innerHTML = approvalSummary.recentApprovalActions.length ? approvalSummary.recentApprovalActions.map((item) => `<li>${escapeHtml(item)}</li>`).join("") : '<li class="detail-empty">当前没有最近动作。</li>';
}

function renderImpactTimeline(elements, context) {
  const stageWeight = { signal: 1, plan: 2, approval_pending: 3, approval: 4, order: 5, fill: 6 };
  const timelineEvents = [
    ...context.signals.map((item) => ({ at: null, stage: "signal", label: `${item.symbol} 生成研究信号`, detail: `${item.side} / 目标 ${fmtPct(item.target_weight)} / ${item.reason}` })),
    ...context.strategyPlans.map((planItem) => ({ at: null, stage: "plan", label: `${planItem.symbol} 进入今日计划`, detail: `${planItem.side} ${fmt(planItem.quantity, 4)} / ${planItem.requires_approval ? "manual" : "auto"}` })),
    ...context.strategyRecentApprovals.map((item) => ({ at: item.decided_at || item.created_at, stage: item.status === "pending" ? "approval_pending" : "approval", label: `${item.symbol} 审批 ${item.status}`, detail: item.decision_reason || item.reason || "manual approval flow" })),
    ...context.strategyExecutions.filter((item) => item.order).map(({ planItem, order }) => ({ at: order.timestamp, stage: order.status === "filled" ? "fill" : "order", label: `${planItem.symbol} 订单 ${order.status}`, detail: `${planItem.side} / filled ${fmt(order.filled_quantity, 4)} / avg ${order.average_price == null ? "N/A" : fmt(order.average_price, 4)}` })),
  ].sort((left, right) => {
    if (left.at && right.at) return new Date(right.at).getTime() - new Date(left.at).getTime();
    if (left.at) return -1;
    if (right.at) return 1;
    return (stageWeight[right.stage] || 0) - (stageWeight[left.stage] || 0);
  });
  elements.timelineSummaryList.innerHTML = [`链路事件: ${fmt(timelineEvents.length)}`, `已进入计划: ${fmt(context.strategyPlans.length)}/${fmt(context.signals.length)}`, `审批事件: ${fmt(context.strategyRecentApprovals.length)}`, `订单事件: ${fmt(context.strategyExecutions.filter((item) => item.order).length)}`].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  elements.timelineList.innerHTML = timelineEvents.length ? timelineEvents.slice(0, 10).map((item) => `<li><strong>${escapeHtml(item.label)}</strong><br /><span class="meta-text">${escapeHtml(fmtTime(item.at))}</span><br />${escapeHtml(item.detail)}</li>`).join("") : '<li class="detail-empty">当前策略还没有链路事件。</li>';
}

function renderImpactReadiness(elements, context) {
  const recommendation = context.detail.recommendation || {};
  const historyCoverage = context.detail.history_coverage || {};
  const historyReady = Boolean(historyCoverage.ready);
  const validationReady = Number(recommendation.validation_pass_rate || 0) >= 0.6 && (recommendation.stability_bucket || "") === "stable";
  const correlationReady = Number(recommendation.max_selected_correlation || 0) < 0.7;
  const capacityReady = (recommendation.capacity_tier || "inactive") !== "inactive";
  const executableToday = context.strategyPlans.length > 0 || context.signals.length > 0;
  const deployReady = (recommendation.verdict || "") === "deploy_candidate" && historyReady && validationReady && correlationReady;
  elements.readinessMetrics.innerHTML = [metricTile("历史覆盖", historyReady ? "ready" : "blocked", `min ${fmtPct(historyCoverage.minimum_coverage_ratio)}`, historyReady ? "ok" : "blocked"), metricTile("验证稳定性", validationReady ? "ready" : "warning", `${recommendation.stability_bucket || "N/A"} / pass ${fmtPct(recommendation.validation_pass_rate)}`, validationReady ? "ok" : "warning"), metricTile("相关性门槛", correlationReady ? "ready" : "blocked", `max corr ${fmt(recommendation.max_selected_correlation)}`, correlationReady ? "ok" : "blocked"), metricTile("推进状态", deployReady ? "deploy" : (recommendation.verdict || "review"), recommendation.action || "N/A", deployReady ? "ok" : "warning")].join("");
  elements.readinessList.innerHTML = [`当前 verdict: ${recommendation.verdict || "N/A"}`, `研究动作: ${recommendation.action || "N/A"}`, `容量层级: ${recommendation.capacity_tier || "N/A"}`, `今日可执行: ${executableToday ? "yes" : "no"}`, `历史覆盖最小值: ${fmtPct(historyCoverage.minimum_coverage_ratio)}`].map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  const actions = [];
  if (!historyReady) actions.push("先补历史数据覆盖，再决定是否推进。");
  if (!validationReady) actions.push("先提升样本外验证和稳定性，再考虑 active。");
  if (!correlationReady) actions.push("先解决和已选策略的相关性，再谈推进。");
  if (!capacityReady) actions.push("当前容量不足，保持 research only。");
  if (!context.strategyPlans.length && context.signals.length) actions.push("今天有研究信号，但还没形成计划。");
  if (deployReady) actions.push("当前已接近 deploy candidate，可继续跟踪计划与执行偏差。");
  if (!actions.length) actions.push("当前没有新增推进动作。");
  elements.readinessActions.innerHTML = actions.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function renderImpact(detail) {
  const elements = impactElements();
  if (!elements) return;
  if (!detail) {
    renderImpactEmpty(elements);
    return;
  }
  const context = buildImpactContext(detail);
  const gapSummary = buildGapSummary(context);
  const executionSummary = buildExecutionSummary(context);
  const approvalSummary = buildApprovalSummary(context);
  renderImpactHeader(elements, context);
  renderImpactGap(elements, context, gapSummary);
  renderImpactExecution(elements, context, gapSummary, executionSummary);
  renderImpactApproval(elements, context, approvalSummary);
  renderImpactTimeline(elements, context);
  renderImpactReadiness(elements, context);
}

async function loadPayloads() {
  const [dashboardRes, activeRes, candidateRes, assetCorrRes] = await Promise.all([
    apiFetch(API.dashboardSummary),
    apiFetch(API.researchScorecard, { method: "POST" }),
    apiFetch(API.researchCandidatesScorecard, { method: "POST" }),
    apiFetch(API.researchCorrelation, { 
        method: "POST", 
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ symbols: ["SPY", "QQQ", "IWM", "EEM", "GLD", "TLT", "USO"] })
    }),
  ]);
  if (!dashboardRes.ok) throw new Error(dashboardRes.error);
  let marketAwareness = dashboardRes.data?.details?.market_awareness ?? null;
  if (!marketAwareness?.overall_regime) {
    const marketAwarenessRes = await apiFetch(API.researchMarketAwareness);
    if (marketAwarenessRes.ok) {
      marketAwareness = marketAwarenessRes.data;
    }
  }
  return {
    dashboard: dashboardRes.data,
    active: activeRes.data ?? {},
    candidates: candidateRes.data ?? {},
    assetCorrelations: assetCorrRes.data ?? {},
    marketAwareness,
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
  renderMarketAwareness(payload);

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
    state.dashboardSummary = payload.dashboard;
    renderResearch(payload);
    if (!state.selectedStrategyId) {
      const defaultStrategyId = filteredRows(payload.candidates?.rows ?? [])[0]?.strategy_id || null;
      state.selectedStrategyId = defaultStrategyId;
    }
    const detail = await loadStrategyImpact(state.selectedStrategyId);
    renderImpact(detail);
  } catch (error) {
    document.getElementById("research-overview-metrics").innerHTML = metricTile("Research Error", "Unavailable", error.message, "blocked");
    renderMarketAwareness({}, error.message);
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

refreshResearch().then(() => {
  initAutoRefresh(() => refreshResearch(), 300);
  document.querySelectorAll(".table-wrap").forEach((wrap) => {
    const tbody = wrap.querySelector("tbody[id]");
    if (tbody) addExportButton(wrap, tbody.id);
  });
});

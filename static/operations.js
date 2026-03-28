async function loadPayloads() {
  const [summaryRes, planRes, summaryListRes, liveRes, rolloutRes, qualityRes, incidentsRes, triggersRes, tcaRes, riskConfigRes, killSwitchRes] = await Promise.all([
    apiFetch(API.dashboardSummary),
    apiFetch(API.journalPlans()),
    apiFetch(API.journalSummaries()),
    apiFetch(API.opsLiveAcceptance),
    apiFetch(API.opsRollout),
    apiFetch(API.opsExecutionMetrics),
    apiFetch(API.opsIncidentsReplay(7)),
    apiFetch(API.ordersTriggers),
    apiFetch(API.opsTca),
    apiFetch(API.opsRiskConfig),
    apiFetch(API.killSwitch),
  ]);
  if (!summaryRes.ok) throw new Error(summaryRes.error);
  return {
    dashboard: summaryRes.data,
    plans: planRes.data ?? [],
    summaries: summaryListRes.data ?? [],
    liveAcceptance: liveRes.data ?? {},
    rollout: rolloutRes.data ?? {},
    executionQuality: qualityRes.data ?? {},
    incidents: incidentsRes.data ?? {},
    smartOrders: triggersRes.data ?? [],
    tca: tcaRes.data ?? {},
    riskConfig: riskConfigRes.data ?? {},
    killSwitch: killSwitchRes.data ?? {},
  };
}

function buildOperationsContext(payload) {
  const dashboard = payload.dashboard ?? {};
  return {
    payload,
    dashboard,
    latestPlan: dashboard.journal?.latest_plan ?? {},
    latestSummary: dashboard.journal?.latest_summary ?? {},
    live: payload.liveAcceptance ?? dashboard.details?.live_acceptance ?? {},
    gate: dashboard.details?.execution_gate ?? {},
    rollout: payload.rollout ?? {},
    quality: payload.executionQuality ?? {},
    incidents: payload.incidents ?? {},
    planRows: dashboard.trading_plan?.items ?? [],
    tca: payload.tca ?? {},
    risk: payload.riskConfig ?? {},
    killSwitch: payload.killSwitch ?? {},
    smartOrders: payload.smartOrders ?? [],
  };
}

function renderOperationsOverview(context) {
  document.getElementById("operations-updated").textContent = `Updated ${new Date().toLocaleString()}`;
  document.getElementById("operations-overview-metrics").innerHTML = [
    metricTile("计划状态", context.latestPlan.status ?? "N/A", context.latestPlan.headline ?? "", context.latestPlan.status === "planned" ? "ok" : context.latestPlan.status === "no_trade" ? "warning" : "blocked"),
    metricTile("总结阻塞项", fmt((context.latestSummary.blockers ?? []).length), `Live ready ${fmt(context.live.ready_for_live)}`, (context.latestSummary.blockers ?? []).length ? "blocked" : "ok"),
    metricTile("计划条目", fmt(context.planRows.length), `Signals ${fmt(context.dashboard.trading_plan?.signal_count)}`, context.planRows.length ? "ok" : "warning"),
    metricTile("执行 Gate", context.gate.should_block ? "Blocked" : context.gate.ready ? "Ready" : "Warning", `Policy ${fmt(context.gate.policy_stage)}`, context.gate.should_block ? "blocked" : context.gate.ready ? "ok" : "warning"),
  ].join("");
}

function renderOperationsPlan(context) {
  document.getElementById("operations-plan-headline").textContent = context.latestPlan.headline ?? "暂无计划摘要。";
  setList("operations-plan-reasons", context.latestPlan.reasons ?? [], "今日没有额外计划原因。");
  setList(
    "operations-blockers",
    [
      ...(context.latestSummary.blockers ?? []),
      ...(context.dashboard.details?.execution_gate?.reasons ?? []),
    ],
    "当前没有阻塞项。",
  );
  document.getElementById("operations-plan-table").innerHTML = context.planRows.length
    ? context.planRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.strategy_id)}</td>
          <td><strong>${escapeHtml(row.symbol)}</strong></td>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(row.side)}</td>
          <td>${escapeHtml(fmt(row.quantity, 4))}</td>
          <td>${escapeHtml(row.target_weight == null ? "N/A" : fmtPct(row.target_weight))}</td>
          <td>${escapeHtml(row.requires_approval ? "manual" : "auto")}</td>
          <td>${escapeHtml(row.reason ?? "")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="8" class="table-empty">今天没有交易计划，或计划被 gate 阻塞。</td></tr>';
}

function renderOperationsSummary(context) {
  document.getElementById("operations-summary-headline").textContent = context.latestSummary.headline ?? "暂无总结。";
  setList("operations-summary-highlights", context.latestSummary.highlights ?? [], "今天还没有总结亮点。");
  setList("operations-next-actions", context.latestSummary.next_actions ?? [], "当前没有下一步动作。");
}

function renderOperationsQuality(context) {
  document.getElementById("operations-quality-metrics").innerHTML = [
    metricTile("Ready For Live", fmt(context.live.ready_for_live), `Incidents ${fmt(context.live.incident_count)}`, context.live.ready_for_live ? "ok" : "warning"),
    metricTile("Rollout", fmt(context.rollout.current_recommendation), `Next ${fmt(context.rollout.next_stage ?? "N/A")}`, context.rollout.ready_for_rollout ? "ok" : "warning"),
    metricTile("异常率", fmtPct(context.quality.exception_rate || 0), `Risk hit ${fmtPct(context.quality.risk_hit_rate || 0)}`, Number(context.quality.exception_rate || 0) <= 0.05 ? "ok" : "blocked"),
    metricTile("授权状态", context.quality.authorization_ok ? "AUTHORIZED" : "UNAUTHORIZED", `Filled ${fmt(context.quality.filled_samples || 0)}`, context.quality.authorization_ok ? "ok" : "blocked"),
  ].join("");
  setList(
    "operations-live-blockers",
    [
      ...(context.live.blockers ?? []),
      ...((context.rollout.blockers ?? []).map((item) => `Rollout blocker: ${item}`)),
    ],
    "当前没有上线阻塞项。",
  );
  setList(
    "operations-rollout-list",
    [
      `current_recommendation: ${fmt(context.rollout.current_recommendation)}`,
      `next_stage: ${fmt(context.rollout.next_stage)}`,
      `ready_for_rollout: ${fmt(context.rollout.ready_for_rollout)}`,
      ...((context.rollout.recommendations ?? []).slice(0, 4)),
    ],
    "当前没有阶段建议。",
  );
}

function renderOperationsIncidents(context) {
  setList(
    "operations-incident-summary",
    [
      `window_days: ${fmt(context.incidents.window_days)}`,
      `event_count: ${fmt((context.incidents.events ?? []).length)}`,
      `latest_category: ${fmt((context.incidents.events ?? [])[0]?.category)}`,
    ],
    "当前没有事件摘要。",
  );
  setList(
    "operations-incident-list",
    (context.incidents.events ?? []).slice(0, 8).map((item) => `${item.occurred_at} / ${item.category} / ${item.label}`),
    "当前没有最近事件。",
  );
}

function renderSmartOrders(context) {
  const table = document.getElementById("smart-orders-table");
  if (!table) return;
  table.innerHTML = context.smartOrders.length
    ? context.smartOrders.map(renderSmartOrderRow).join("")
    : '<tr><td colspan="6" class="table-empty">没有活跃的 Smart Orders 监听规则。</td></tr>';
}

function renderTcaPanel(context) {
  document.getElementById("tca-metrics").innerHTML = [
    metricTile("平均滑点", `${fmt(context.tca.avg_slippage_bps || 0, 2)} bps`, "Slippage Gap", (context.tca.avg_slippage_bps || 0) < 5 ? "ok" : "warning"),
    metricTile("平均延迟", `${fmt(context.tca.avg_latency_sec || 0, 3)}s`, "Execution Speed", (context.tca.avg_latency_sec || 0) < 1.0 ? "ok" : "warning"),
    metricTile("执行样本", fmt(context.tca.execution_cycle_count || 0), "Cycle Count", "ok"),
    metricTile("异常率", fmtPct(context.tca.exception_rate || 0), "Error Rate", (context.tca.exception_rate || 0) < 0.05 ? "ok" : "blocked"),
  ].join("");
  const sentimentData = context.tca.sentiment_impact || {};
  document.getElementById("tca-sentiment-list").innerHTML = Object.keys(sentimentData).length
    ? Object.entries(sentimentData).map(([emotion, impact]) => `
        <div class="detail-item">
            <span class="detail-label">${emotion}</span>
            <span class="detail-value ${impact > 5 ? 'text-danger' : ''}">${fmt(impact, 2)} bps slip</span>
        </div>
    `).join("")
    : '<div class="detail-empty">无情绪对滑点影响数据。</div>';
  document.getElementById("tca-recent-list").innerHTML = context.tca.latest_execution_event
    ? `<li>Latest: <strong>${context.tca.latest_execution_event.action}</strong> at ${new Date(context.tca.latest_execution_event.created_at).toLocaleTimeString()}</li>`
    : '<li class="detail-empty">暂无近期执行记录。</li>';
}

function renderRiskPanel(context) {
  document.getElementById("risk-daily-sl").value = context.risk.daily_stop_loss || 0;
  document.getElementById("risk-max-weight").value = context.risk.max_single_stock_weight || 0;
  document.getElementById("risk-half-dd").value = context.risk.half_risk_drawdown || 0;
  document.getElementById("risk-no-dd").value = context.risk.no_new_risk_drawdown || 0;
  const ksBadge = document.getElementById("kill-switch-status");
  ksBadge.textContent = context.killSwitch.enabled ? "ACTIVE (HALTED)" : "INACTIVE (OK)";
  ksBadge.className = `status-badge ${context.killSwitch.enabled ? "blocked" : "ok"}`;
  document.getElementById("kill-switch-reason").textContent = `最后操作原因: ${context.killSwitch.latest?.reason || "N/A"}`;
}

function renderFillsTable(context) {
  const samples = context.quality.samples ?? [];
  document.getElementById("operations-fills-table").innerHTML = samples.length
    ? samples.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.symbol)}</strong></td>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(fmt(row.reference_price, 2))}</td>
          <td>${escapeHtml(fmt(row.fill_price, 2))}</td>
          <td style="font-family:var(--font-mono)">${fillSlippageHtml(row.recorded_slippage)}</td>
          <td>${fillTagHtml(row.emotional_tag)}</td>
          <td>
            ${row.within_threshold 
              ? `<span style="color:var(--ok)">OK</span>` 
              : `<span style="color:var(--panic)">超限 (Breach)</span>`}
          </td>
        </tr>
      `).join("")
    : '<tr><td colspan="7" class="table-empty">近期没有执行记录。</td></tr>';
}

function renderArchiveHistory(context) {
  setList(
    "operations-plan-history",
    (context.payload.plans ?? []).slice(0, 8).map((item) => `${item.as_of} / ${item.status} / ${item.headline}`),
    "暂无计划归档。",
  );
  setList(
    "operations-summary-history",
    (context.payload.summaries ?? []).slice(0, 8).map((item) => `${item.as_of} / ${item.headline}`),
    "暂无总结归档。",
  );
}

function renderSmartOrderRow(row) {
  const conditionsAst = (row.trigger_conditions ?? []).map((item) => `${item.metric} ${item.operator} ${item.target_value}`).join(" AND ");
  const timeText = row.triggered_at ? row.triggered_at.substring(11, 16) : "-";
  const sideVar = row.side === "BUY" ? "--ok" : "--panic";
  const statusClass = row.status === "TRIGGERED" ? "status-ok" : row.status === "PENDING" ? "status-warning" : "status-empty";
  return `
    <tr>
      <td><span class="meta-text" title="${row.smart_order_id}">${row.smart_order_id.substring(0, 8)}</span></td>
      <td><strong>${escapeHtml(row.symbol)}</strong></td>
      <td><span style="color:var(${sideVar})">${row.side}</span> / ${row.quantity}</td>
      <td style="font-family:var(--font-mono); font-size:11px">${escapeHtml(conditionsAst)}</td>
      <td>${timeText}</td>
      <td><span class="badge ${statusClass}">${escapeHtml(row.status)}</span></td>
    </tr>
  `;
}

function fillTagHtml(tag) {
  if (!tag) return '<span style="color:var(--text-muted)">-</span>';
  const colorMap = { FOMO: "var(--panic)", Panic: "var(--panic)", "Manual Plan": "var(--ok)", Rebound: "var(--warning)" };
  const color = colorMap[tag] || "var(--text)";
  return `<span style="display:inline-block; padding:2px 8px; background:rgba(255,255,255,0.05); border:1px solid ${color}; color:${color}; border-radius:12px; font-size:11px; font-weight:600;">${escapeHtml(tag)}</span>`;
}

function fillSlippageHtml(value) {
  const formatted = escapeHtml(fmt(value ?? 0, 4));
  if ((value || 0) > 0) return `<span style="color:var(--warning)">+${formatted}</span>`;
  if ((value || 0) < 0) return `<span style="color:var(--ok)">${formatted}</span>`;
  return formatted;
}

function renderOperations(payload) {
  const context = buildOperationsContext(payload);
  renderOperationsOverview(context);
  renderOperationsPlan(context);
  renderOperationsSummary(context);
  renderOperationsQuality(context);
  renderOperationsIncidents(context);
  renderSmartOrders(context);
  renderTcaPanel(context);
  renderRiskPanel(context);
  renderFillsTable(context);
  renderArchiveHistory(context);
}

async function refreshOperations() {
  try {
    const payload = await loadPayloads();
    renderOperations(payload);
  } catch (error) {
    document.getElementById("operations-overview-metrics").innerHTML = metricTile("Operations Error", "Unavailable", error.message, "blocked");
  }
}

async function initOperations() {
  try {
    const payload = await loadPayloads();
    renderOperations(payload);
  } catch (error) {
    console.error("[Operations] Init failed:", error);
    const container = document.getElementById("operations-overview-metrics");
    if (container) {
      container.innerHTML = `
        <article class="metric-tile blocked">
          <div class="metric-label">Operations Error</div>
          <div class="metric-value">Unavailable</div>
          <div class="metric-meta">${error.message}</div>
        </article>
      `;
    }
  }
}

// Risk Management Handlers
async function handleRiskUpdate(e) {
    e.preventDefault();
    const payload = {
        daily_stop_loss: parseFloat(document.getElementById("risk-daily-sl").value),
        max_single_stock_weight: parseFloat(document.getElementById("risk-max-weight").value),
        half_risk_drawdown: parseFloat(document.getElementById("risk-half-dd").value),
        no_new_risk_drawdown: parseFloat(document.getElementById("risk-no-dd").value)
    };
    const res = await apiFetch(API.opsRiskConfig, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
    });
    if (res.ok) {
        showToast("风控配置已更新", "success");
        initOperations();
    } else {
        showToast("更新失败: " + res.error, "error");
    }
}

async function handleKillSwitchToggle() {
    const ks = document.getElementById("kill-switch-status").textContent.includes("ACTIVE");
    const reason = prompt(`确定要${ks ? '取消' : '开启'}紧急关停吗？请输入原因:`);
    if (reason === null) return;
    
    const res = await apiFetch(API.killSwitchToggle(!ks, reason), {
        method: "POST"
    });
    if (res.ok) {
        showToast(`紧急关停已${ks ? '取消' : '开启'}`, "success");
        initOperations();
    } else {
        showToast("操作失败: " + res.error, "error");
    }
}

document.addEventListener("DOMContentLoaded", () => {
  initOperations();
  document.getElementById("refresh-operations")?.addEventListener("click", refreshOperations);
  document.getElementById("risk-config-form")?.addEventListener("submit", handleRiskUpdate);
  document.getElementById("toggle-kill-switch")?.addEventListener("click", handleKillSwitchToggle);
});

// Also try immediate init for module scripts
if (document.readyState === "complete" || document.readyState === "interactive") {
    initOperations();
}

/* Smart Orders Mock Interactions */
document.getElementById("eval-smart-order-btn")?.addEventListener("click", async (e) => {
  e.target.disabled = true;
  e.target.textContent = "跑批中...";
  const res = await apiFetch(API.opsEvaluateTriggers, { method: "POST" });
  if (res.ok) {
    showToast(`估值完成。扫描 ${res.data.evaluated} 条，触发 ${res.data.triggered} 条。`, "success");
    await refreshOperations();
  } else {
    showToast(`估值失败: ${res.error}`, "error");
  }
  e.target.disabled = false;
  e.target.textContent = "立即跑批估值";
});

document.getElementById("add-smart-order-btn")?.addEventListener("click", async (e) => {
  e.target.disabled = true;
  const mockOrder = {
    account: "total",
    symbol: "TSLA",
    market: "US",
    side: "BUY",
    quantity: 10,
    trigger_conditions: [
      { metric: "PRICE", operator: "<", target_value: 150.0 },
      { metric: "RSI_14", operator: "<", target_value: 30.0 }
    ]
  };
  const res = await apiFetch(API.ordersTriggers, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(mockOrder)
  });
  if (res.ok) {
    showToast("成功注入一条测试 Smart Order", "success");
    await refreshOperations();
  } else {
    showToast(`注入失败: ${res.error}`, "error");
  }
  e.target.disabled = false;
});

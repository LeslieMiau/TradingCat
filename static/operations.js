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

function renderOperations(payload) {
  const dashboard = payload.dashboard;
  const latestPlan = dashboard.journal?.latest_plan ?? {};
  const latestSummary = dashboard.journal?.latest_summary ?? {};
  const live = payload.liveAcceptance ?? dashboard.details?.live_acceptance ?? {};
  const gate = dashboard.details?.execution_gate ?? {};
  const rollout = payload.rollout ?? {};
  const quality = payload.executionQuality ?? {};
  const incidents = payload.incidents ?? {};
  const planRows = dashboard.trading_plan?.items ?? [];

  document.getElementById("operations-updated").textContent = `Updated ${new Date().toLocaleString()}`;
  document.getElementById("operations-overview-metrics").innerHTML = [
    metricTile("计划状态", latestPlan.status ?? "N/A", latestPlan.headline ?? "", latestPlan.status === "planned" ? "ok" : latestPlan.status === "no_trade" ? "warning" : "blocked"),
    metricTile("总结阻塞项", fmt((latestSummary.blockers ?? []).length), `Live ready ${fmt(live.ready_for_live)}`, (latestSummary.blockers ?? []).length ? "blocked" : "ok"),
    metricTile("计划条目", fmt(planRows.length), `Signals ${fmt(dashboard.trading_plan?.signal_count)}`, planRows.length ? "ok" : "warning"),
    metricTile("执行 Gate", gate.should_block ? "Blocked" : gate.ready ? "Ready" : "Warning", `Policy ${fmt(gate.policy_stage)}`, gate.should_block ? "blocked" : gate.ready ? "ok" : "warning"),
  ].join("");

  document.getElementById("operations-plan-headline").textContent = latestPlan.headline ?? "暂无计划摘要。";
  setList("operations-plan-reasons", latestPlan.reasons ?? [], "今日没有额外计划原因。");
  setList(
    "operations-blockers",
    [
      ...(latestSummary.blockers ?? []),
      ...(dashboard.details?.execution_gate?.reasons ?? []),
    ],
    "当前没有阻塞项。",
  );

  const tbody = document.getElementById("operations-plan-table");
  tbody.innerHTML = planRows.length
    ? planRows.map((row) => `
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

  document.getElementById("operations-summary-headline").textContent = latestSummary.headline ?? "暂无总结。";
  setList("operations-summary-highlights", latestSummary.highlights ?? [], "今天还没有总结亮点。");
  setList("operations-next-actions", latestSummary.next_actions ?? [], "当前没有下一步动作。");
  document.getElementById("operations-quality-metrics").innerHTML = [
    metricTile("Ready For Live", fmt(live.ready_for_live), `Incidents ${fmt(live.incident_count)}`, live.ready_for_live ? "ok" : "warning"),
    metricTile("Rollout", fmt(rollout.current_recommendation), `Next ${fmt(rollout.next_stage ?? "N/A")}`, rollout.ready_for_rollout ? "ok" : "warning"),
    metricTile("异常率", fmtPct(quality.exception_rate || 0), `Risk hit ${fmtPct(quality.risk_hit_rate || 0)}`, Number(quality.exception_rate || 0) <= 0.05 ? "ok" : "blocked"),
    metricTile("授权状态", quality.authorization_ok ? "AUTHORIZED" : "UNAUTHORIZED", `Filled ${fmt(quality.filled_samples || 0)}`, quality.authorization_ok ? "ok" : "blocked"),
  ].join("");
  setList(
    "operations-live-blockers",
    [
      ...(live.blockers ?? []),
      ...((rollout.blockers ?? []).map((item) => `Rollout blocker: ${item}`)),
    ],
    "当前没有上线阻塞项。",
  );
  setList(
    "operations-rollout-list",
    [
      `current_recommendation: ${fmt(rollout.current_recommendation)}`,
      `next_stage: ${fmt(rollout.next_stage)}`,
      `ready_for_rollout: ${fmt(rollout.ready_for_rollout)}`,
      ...((rollout.recommendations ?? []).slice(0, 4)),
    ],
    "当前没有阶段建议。",
  );
  setList(
    "operations-incident-summary",
    [
      `window_days: ${fmt(incidents.window_days)}`,
      `event_count: ${fmt((incidents.events ?? []).length)}`,
      `latest_category: ${fmt((incidents.events ?? [])[0]?.category)}`,
    ],
    "当前没有事件摘要。",
  );
  setList(
    "operations-incident-list",
    (incidents.events ?? []).slice(0, 8).map((item) => `${item.occurred_at} / ${item.category} / ${item.label}`),
    "当前没有最近事件。",
  );

  const triggersBody = document.getElementById("smart-orders-table");
  if (triggersBody) {
    const triggers = payload.smartOrders ?? [];
    triggersBody.innerHTML = triggers.length
      ? triggers.map((row) => {
          const conditionsAst = row.trigger_conditions.map(c => `${c.metric} ${c.operator} ${c.target_value}`).join(" AND ");
          const timeText = row.triggered_at ? row.triggered_at.substring(11, 16) : "-";
          return `
          <tr>
            <td><span class="meta-text" title="${row.smart_order_id}">${row.smart_order_id.substring(0, 8)}</span></td>
            <td><strong>${escapeHtml(row.symbol)}</strong></td>
            <td><span style="color:var(${row.side === 'BUY' ? '--ok' : '--panic'})">${row.side}</span> / ${row.quantity}</td>
            <td style="font-family:var(--font-mono); font-size:11px">${escapeHtml(conditionsAst)}</td>
            <td>${timeText}</td>
            <td><span class="badge ${row.status === 'TRIGGERED' ? 'status-ok' : row.status === 'PENDING' ? 'status-warning' : 'status-empty'}">${escapeHtml(row.status)}</span></td>
          </tr>
        `}).join("")
      : '<tr><td colspan="6" class="table-empty">没有活跃的 Smart Orders 监听规则。</td></tr>';
  }

  // Render TCA Metrics
  const tca = payload.tca ?? {};
  document.getElementById("tca-metrics").innerHTML = [
    metricTile("平均滑点", `${fmt(tca.avg_slippage_bps || 0, 2)} bps`, "Slippage Gap", (tca.avg_slippage_bps || 0) < 5 ? "ok" : "warning"),
    metricTile("平均延迟", `${fmt(tca.avg_latency_sec || 0, 3)}s`, "Execution Speed", (tca.avg_latency_sec || 0) < 1.0 ? "ok" : "warning"),
    metricTile("执行样本", fmt(tca.execution_cycle_count || 0), "Cycle Count", "ok"),
    metricTile("异常率", fmtPct(tca.exception_rate || 0), "Error Rate", (tca.exception_rate || 0) < 0.05 ? "ok" : "blocked"),
  ].join("");

  const sentimentList = document.getElementById("tca-sentiment-list");
  const sentimentData = tca.sentiment_impact || {};
  sentimentList.innerHTML = Object.keys(sentimentData).length
    ? Object.entries(sentimentData).map(([emo, impact]) => `
        <div class="detail-item">
            <span class="detail-label">${emo}</span>
            <span class="detail-value ${impact > 5 ? 'text-danger' : ''}">${fmt(impact, 2)} bps slip</span>
        </div>
    `).join("")
    : '<div class="detail-empty">无情绪对滑点影响数据。</div>';

  const recentTca = document.getElementById("tca-recent-list");
  recentTca.innerHTML = tca.latest_execution_event
    ? `<li>Latest: <strong>${tca.latest_execution_event.action}</strong> at ${new Date(tca.latest_execution_event.created_at).toLocaleTimeString()}</li>`
    : '<li class="detail-empty">暂无近期执行记录。</li>';

  // Render Risk Config
  const risk = payload.riskConfig || {};
  document.getElementById("risk-daily-sl").value = risk.daily_stop_loss || 0;
  document.getElementById("risk-max-weight").value = risk.max_single_stock_weight || 0;
  document.getElementById("risk-half-dd").value = risk.half_risk_drawdown || 0;
  document.getElementById("risk-no-dd").value = risk.no_new_risk_drawdown || 0;

  const ks = payload.killSwitch || {};
  const ksBadge = document.getElementById("kill-switch-status");
  ksBadge.textContent = ks.enabled ? "ACTIVE (HALTED)" : "INACTIVE (OK)";
  ksBadge.className = `status-badge ${ks.enabled ? 'blocked' : 'ok'}`;
  document.getElementById("kill-switch-reason").textContent = `最后操作原因: ${ks.latest?.reason || 'N/A'}`;

  const fillsBody = document.getElementById("operations-fills-table");
  const samples = quality.samples ?? [];
  fillsBody.innerHTML = samples.length
    ? samples.map((row) => {
        let tagHtml = "";
        if (row.emotional_tag) {
           const colorMap = {"FOMO": "var(--panic)", "Panic": "var(--panic)", "Manual Plan": "var(--ok)", "Rebound": "var(--warning)"};
           const color = colorMap[row.emotional_tag] || "var(--text)";
           tagHtml = `<span style="display:inline-block; padding:2px 8px; background:rgba(255,255,255,0.05); border:1px solid ${color}; color:${color}; border-radius:12px; font-size:11px; font-weight:600;">${escapeHtml(row.emotional_tag)}</span>`;
        } else {
           tagHtml = `<span style="color:var(--text-muted)">-</span>`;
        }
        
        let slipHtml = escapeHtml(fmt(row.recorded_slippage ?? 0, 4));
        if ((row.recorded_slippage || 0) > 0) slipHtml = `<span style="color:var(--warning)">+${slipHtml}</span>`;
        else if ((row.recorded_slippage || 0) < 0) slipHtml = `<span style="color:var(--ok)">${slipHtml}</span>`;
        
        return `
        <tr>
          <td><strong>${escapeHtml(row.symbol)}</strong></td>
          <td>${escapeHtml(row.market)}</td>
          <td>${escapeHtml(fmt(row.reference_price, 2))}</td>
          <td>${escapeHtml(fmt(row.fill_price, 2))}</td>
          <td style="font-family:var(--font-mono)">${slipHtml}</td>
          <td>${tagHtml}</td>
          <td>
            ${row.within_threshold 
              ? `<span style="color:var(--ok)">OK</span>` 
              : `<span style="color:var(--panic)">超限 (Breach)</span>`}
          </td>
        </tr>
      `}).join("")
    : '<tr><td colspan="7" class="table-empty">近期没有执行记录。</td></tr>';

  setList(
    "operations-plan-history",
    (payload.plans ?? []).slice(0, 8).map((item) => `${item.as_of} / ${item.status} / ${item.headline}`),
    "暂无计划归档。",
  );
  setList(
    "operations-summary-history",
    (payload.summaries ?? []).slice(0, 8).map((item) => `${item.as_of} / ${item.headline}`),
    "暂无总结归档。",
  );
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

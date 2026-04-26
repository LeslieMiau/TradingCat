async function loadPayloads() {
  const [summaryRes, planRes, summaryListRes, liveRes, rolloutRes, qualityRes, incidentsRes, triggersRes, tcaRes, riskConfigRes, killSwitchRes, evidenceTimelineRes] = await Promise.all([
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
    apiFetch(API.opsAcceptanceEvidenceTimeline(42)),
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
    evidenceTimeline: evidenceTimelineRes.data ?? {},
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
    evidenceTimeline: payload.evidenceTimeline ?? {},
    gateReadiness: (payload.rollout ?? {}).acceptance_gate_readiness ?? {},
  };
}

function renderOperationsOverview(context) {
  document.getElementById("operations-updated").textContent = `更新于 ${new Date().toLocaleString()}`;
  document.getElementById("operations-overview-metrics").innerHTML = [
    metricTile("计划状态", labelStatus(context.latestPlan.status), context.latestPlan.headline ?? "", context.latestPlan.status === "planned" ? "ok" : context.latestPlan.status === "no_trade" ? "warning" : "blocked"),
    metricTile("总结阻塞项", fmt((context.latestSummary.blockers ?? []).length), `实盘就绪 ${fmt(context.live.ready_for_live)}`, (context.latestSummary.blockers ?? []).length ? "blocked" : "ok"),
    metricTile("计划条目", fmt(context.planRows.length), `信号 ${fmt(context.dashboard.trading_plan?.signal_count)}`, context.planRows.length ? "ok" : "warning"),
    metricTile("执行门禁", context.gate.should_block ? "已阻塞" : context.gate.ready ? "就绪" : "预警", `策略档位 ${fmt(context.gate.policy_stage)}`, context.gate.should_block ? "blocked" : context.gate.ready ? "ok" : "warning"),
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
          <td>${escapeHtml(labelMarket(row.market))}</td>
          <td>${escapeHtml(labelSide(row.side))}</td>
          <td>${escapeHtml(fmt(row.quantity, 4))}</td>
          <td>${escapeHtml(row.target_weight == null ? "暂无" : fmtPct(row.target_weight))}</td>
          <td>${escapeHtml(row.requires_approval ? "人工" : "自动")}</td>
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
  const readiness = context.gateReadiness ?? {};
  const required = readiness.required_pass_streak;
  const current = readiness.current_pass_streak ?? 0;
  const streakLabel = required != null ? `${current} / ${required}` : `${current}`;
  const streakStatus = readiness.eligible
    ? "ok"
    : required != null && current >= required
      ? "ok"
      : required != null
        ? "blocked"
        : "warning";
  const summary = (context.evidenceTimeline ?? {}).summary ?? {};
  document.getElementById("operations-quality-metrics").innerHTML = [
    metricTile("实盘就绪", fmt(context.live.ready_for_live), `事件 ${fmt(context.live.incident_count)}`, context.live.ready_for_live ? "ok" : "warning"),
    metricTile("上线阶段", fmt(context.rollout.current_recommendation), `下一档 ${fmt(context.rollout.next_stage)}`, context.rollout.ready_for_rollout ? "ok" : "warning"),
    metricTile("连续通过", streakLabel, `目标 ${fmt(readiness.target_stage)} · 最高 ${fmt(readiness.max_pass_streak ?? 0)}`, streakStatus),
    metricTile("证据 42日", `${fmt(summary.pass_days ?? 0)} 天通过`, `失败 ${fmt(summary.fail_days ?? 0)} · 缺失 ${fmt(summary.missing_days ?? 0)}`, (summary.fail_days ?? 0) === 0 ? "ok" : "warning"),
    metricTile("异常率", fmtPct(context.quality.exception_rate || 0), `风控命中 ${fmtPct(context.quality.risk_hit_rate || 0)}`, Number(context.quality.exception_rate || 0) <= 0.05 ? "ok" : "blocked"),
    metricTile("授权状态", context.quality.authorization_ok ? "已授权" : "未授权", `成交样本 ${fmt(context.quality.filled_samples || 0)}`, context.quality.authorization_ok ? "ok" : "blocked"),
  ].join("");
  setList(
    "operations-live-blockers",
    [
      ...(context.live.blockers ?? []),
      ...((context.rollout.blockers ?? []).map((item) => `上线阶段阻塞: ${item}`)),
      ...((readiness.blockers ?? []).map((item) => `门禁阻塞: ${item}`)),
    ],
    "当前没有上线阻塞项。",
  );
  setList(
    "operations-rollout-list",
    [
      `当前建议档位: ${fmt(context.rollout.current_recommendation)}`,
      `下一档: ${fmt(context.rollout.next_stage)}`,
      `可推进上线: ${fmt(context.rollout.ready_for_rollout)}`,
      `门禁合格 (${fmt(readiness.target_stage)}): ${fmt(readiness.eligible)}`,
      `连续通过: ${streakLabel}`,
      ...((context.rollout.recommendations ?? []).slice(0, 4)),
    ],
    "当前没有阶段建议。",
  );
}

function renderOperationsIncidents(context) {
  setList(
    "operations-incident-summary",
    [
      `窗口天数: ${fmt(context.incidents.window_days)}`,
      `事件数量: ${fmt((context.incidents.events ?? []).length)}`,
      `最新类别: ${fmt((context.incidents.events ?? [])[0]?.category)}`,
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
    : '<tr><td colspan="6" class="table-empty">没有活跃的智能条件单监听规则。</td></tr>';
}

function renderTcaPanel(context) {
  document.getElementById("tca-metrics").innerHTML = [
    metricTile("平均滑点", `${fmt(context.tca.avg_slippage_bps || 0, 2)} bps`, "滑点偏差", (context.tca.avg_slippage_bps || 0) < 5 ? "ok" : "warning"),
    metricTile("平均延迟", `${fmt(context.tca.avg_latency_sec || 0, 3)}s`, "执行速度", (context.tca.avg_latency_sec || 0) < 1.0 ? "ok" : "warning"),
    metricTile("执行样本", fmt(context.tca.execution_cycle_count || 0), "执行轮次", "ok"),
    metricTile("异常率", fmtPct(context.tca.exception_rate || 0), "错误率", (context.tca.exception_rate || 0) < 0.05 ? "ok" : "blocked"),
  ].join("");
  const sentimentData = context.tca.sentiment_impact || {};
  document.getElementById("tca-sentiment-list").innerHTML = Object.keys(sentimentData).length
    ? Object.entries(sentimentData).map(([emotion, impact]) => `
        <div class="detail-item">
            <span class="detail-label">${emotion}</span>
            <span class="detail-value ${impact > 5 ? 'text-danger' : ''}">${fmt(impact, 2)} bps 滑点</span>
        </div>
    `).join("")
    : '<div class="detail-empty">无情绪对滑点影响数据。</div>';
  document.getElementById("tca-recent-list").innerHTML = context.tca.latest_execution_event
    ? `<li>最近：<strong>${context.tca.latest_execution_event.action}</strong>，${new Date(context.tca.latest_execution_event.created_at).toLocaleTimeString()}</li>`
    : '<li class="detail-empty">暂无近期执行记录。</li>';
}

function renderRiskPanel(context) {
  document.getElementById("risk-daily-sl").value = context.risk.daily_stop_loss || 0;
  document.getElementById("risk-max-weight").value = context.risk.max_single_stock_weight || 0;
  document.getElementById("risk-half-dd").value = context.risk.half_risk_drawdown || 0;
  document.getElementById("risk-no-dd").value = context.risk.no_new_risk_drawdown || 0;
  const ksBadge = document.getElementById("kill-switch-status");
  ksBadge.textContent = context.killSwitch.enabled ? "已激活（已暂停）" : "未激活（正常）";
  ksBadge.dataset.enabled = context.killSwitch.enabled ? "true" : "false";
  ksBadge.className = `status-badge ${context.killSwitch.enabled ? "blocked" : "ok"}`;
  document.getElementById("kill-switch-reason").textContent = `最后操作原因：${context.killSwitch.latest?.reason || "暂无"}`;
}

function renderFillsTable(context) {
  const samples = context.quality.samples ?? [];
  document.getElementById("operations-fills-table").innerHTML = samples.length
    ? samples.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.symbol)}</strong></td>
          <td>${escapeHtml(labelMarket(row.market))}</td>
          <td>${escapeHtml(fmt(row.reference_price, 2))}</td>
          <td>${escapeHtml(fmt(row.fill_price, 2))}</td>
          <td style="font-family:var(--font-mono)">${fillSlippageHtml(row.recorded_slippage)}</td>
          <td>${fillTagHtml(row.emotional_tag)}</td>
          <td>
            ${row.within_threshold
              ? `<span style="color:var(--ok)">正常</span>`
              : `<span style="color:var(--block)">超限</span>`}
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
  const sideVar = row.side === "BUY" ? "--ok" : "--block";
  const statusClass = row.status === "TRIGGERED" ? "status-ok" : row.status === "PENDING" ? "status-warning" : "status-empty";
  return `
    <tr>
      <td><span class="meta-text" title="${row.smart_order_id}">${row.smart_order_id.substring(0, 8)}</span></td>
      <td><strong>${escapeHtml(row.symbol)}</strong></td>
      <td><span style="color:var(${sideVar})">${labelSide(row.side)}</span> / ${row.quantity}</td>
      <td style="font-family:var(--font-mono); font-size:11px">${escapeHtml(conditionsAst)}</td>
      <td>${timeText}</td>
      <td><span class="badge ${statusClass}">${escapeHtml(labelStatus(row.status))}</span></td>
    </tr>
  `;
}

function fillTagHtml(tag) {
  if (!tag) return '<span style="color:var(--text-secondary)">-</span>';
  const colorMap = { FOMO: "var(--block)", Panic: "var(--block)", "Manual Plan": "var(--ok)", Rebound: "var(--warn)" };
  const color = colorMap[tag] || "var(--text)";
  return `<span style="display:inline-block; padding:2px 8px; background:rgba(255,255,255,0.05); border:1px solid ${color}; color:${color}; border-radius:12px; font-size:11px; font-weight:600;">${escapeHtml(tag)}</span>`;
}

function fillSlippageHtml(value) {
  const formatted = escapeHtml(fmt(value ?? 0, 4));
  if ((value || 0) > 0) return `<span style="color:var(--warn)">+${formatted}</span>`;
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
    document.getElementById("operations-overview-metrics").innerHTML = metricTile("运营错误", "不可用", error.message, "blocked");
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
          <div class="metric-label">运营错误</div>
          <div class="metric-value">不可用</div>
          <div class="metric-meta">${error.message}</div>
        </article>
      `;
    }
  }
}

// 风控操作处理
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
    const ks = document.getElementById("kill-switch-status").dataset.enabled === "true";
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
  initOperations().then(() => {
    initAutoRefresh(() => refreshOperations(), 120);
    document.querySelectorAll(".table-wrap").forEach((wrap) => {
      const tbody = wrap.querySelector("tbody[id]");
      if (tbody) addExportButton(wrap, tbody.id);
    });
  });
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
    showToast("成功注入一条测试智能条件单", "success");
    await refreshOperations();
  } else {
    showToast(`注入失败: ${res.error}`, "error");
  }
  e.target.disabled = false;
});

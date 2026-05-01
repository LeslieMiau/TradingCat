/* TradingCat — read-only trading-day cockpit. */

function badgeClass(status) {
  if (status === "ready" || status === "ok" || status === "clear") return "badge-ok";
  if (status === "blocked" || status === "offline") return "badge-fail";
  if (status === "no_trade" || status === "degraded" || status === "stale" || status === "open") return "badge-warn";
  return "badge";
}

function renderDecision(payload) {
  const decision = payload.decision || {};
  const status = document.getElementById("today-status");
  if (status) {
    status.className = `badge ${badgeClass(decision.status)}`;
    status.textContent = labelStatus(decision.status || "unknown");
  }
  const root = document.getElementById("today-decision");
  if (!root) return;
  const why = decision.why || [];
  root.innerHTML = [
    `<article class="metric-tile"><span>状态</span><strong>${escapeHtml(labelStatus(decision.status || "unknown"))}</strong><small>${escapeHtml((decision.tradable_markets || []).join(", ") || "无交易市场")}</small></article>`,
    `<article class="detail-card"><h3>原因</h3><ul class="detail-list">${why.length ? why.map(item => `<li>${escapeHtml(item)}</li>`).join("") : "<li class=\"detail-empty\">暂无阻塞原因</li>"}</ul></article>`,
    `<article class="detail-card"><h3>下一步</h3><p class="detail-paragraph">${escapeHtml(decision.next_step || "等待数据刷新")}</p></article>`,
  ].join("");
}

function renderMarkets(markets) {
  const root = document.getElementById("today-markets");
  if (!root) return;
  root.innerHTML = (markets || []).map(row => {
    const state = row.state || {};
    const blockers = state.blockers || [];
    return `<article class="detail-card">
      <h3>${escapeHtml(row.label || row.market)}</h3>
      <div class="tag-row">
        <span class="badge">${escapeHtml(row.phase || "unknown")}</span>
        <span class="badge ${row.is_trading_day ? "badge-ok" : "badge-warn"}">${row.is_trading_day ? "交易日" : "休市"}</span>
      </div>
      <ul class="detail-list">
        <li>结构: ${escapeHtml(state.bias_label || "unknown")}</li>
        <li>风险分: ${fmt(state.risk_score)}/10</li>
        <li>置信度: ${fmt(state.confidence)}%</li>
        ${blockers.slice(0, 2).map(item => `<li>${escapeHtml(item)}</li>`).join("")}
      </ul>
      <p class="meta-text">${escapeHtml(row.source_service)} · ${escapeHtml(row.source_field)}</p>
    </article>`;
  }).join("") || '<article class="detail-card"><span class="detail-empty">暂无市场状态</span></article>';
}

function renderHeartbeat(heartbeat) {
  const status = document.getElementById("today-heartbeat-status");
  if (status) {
    status.className = `badge ${badgeClass(heartbeat?.overall_status)}`;
    status.textContent = labelStatus(heartbeat?.overall_status || "unknown");
  }
  const root = document.getElementById("today-heartbeat");
  if (!root) return;
  const components = heartbeat?.components || [];
  root.innerHTML = components.map(component => `<article class="detail-card">
    <div class="panel-header compact-header">
      <h3>${escapeHtml(component.label || component.id)}</h3>
      <span class="badge ${badgeClass(component.status)}">${escapeHtml(labelStatus(component.status || "unknown"))}</span>
    </div>
    <p class="detail-paragraph">${escapeHtml(component.detail || "暂无详情")}</p>
    <ul class="detail-list">
      <li>观测: ${escapeHtml(fmtTime(component.observed_at))}</li>
      <li>来源: ${escapeHtml(component.source_service || "")} · ${escapeHtml(component.source_field || "")}</li>
    </ul>
  </article>`).join("") || '<article class="detail-card"><span class="detail-empty">暂无心跳数据</span></article>';
}

function renderActionQueue(queue) {
  const badge = document.getElementById("today-action-count");
  if (badge) {
    badge.className = `badge ${badgeClass(queue?.status)}`;
    badge.textContent = queue?.count ? `${fmt(queue.count)} 项` : "清空";
  }
  const tbody = document.getElementById("today-action-queue");
  if (!tbody) return;
  const rows = queue?.items || [];
  tbody.innerHTML = rows.map(item => `<tr>
    <td><span class="badge ${item.severity === "high" ? "badge-fail" : item.severity === "medium" ? "badge-warn" : "badge"}">${escapeHtml(labelStatus(item.severity || "low"))}</span></td>
    <td><strong>${escapeHtml(item.title || "")}</strong><br><span class="meta-text">${escapeHtml(item.detail || "")}</span></td>
    <td>${escapeHtml(item.source_service || "")}<br><code>${escapeHtml(item.source_field || "")}</code></td>
    <td><a class="button button-xs" href="${escapeHtml(item.target_url || "/dashboard/operations")}">查看</a></td>
  </tr>`).join("") || '<tr><td colspan="4" class="table-empty">暂无待处理动作</td></tr>';
}

function renderLiveReadiness(readiness) {
  const badge = document.getElementById("today-live-status");
  if (badge) {
    badge.className = `badge ${badgeClass(readiness?.status)}`;
    badge.textContent = readiness?.ready ? "可进入实盘" : labelStatus(readiness?.status || "unknown");
  }
  const root = document.getElementById("today-live-readiness");
  if (!root) return;
  const blockers = readiness?.blockers || [];
  root.innerHTML = [
    `<article class="metric-tile"><span>状态</span><strong>${escapeHtml(readiness?.ready ? "通过" : "阻断")}</strong><small>${escapeHtml(readiness?.source_service || "TradingDayWorkflowService")}</small></article>`,
    `<article class="detail-card"><h3>实盘阻断</h3><ul class="detail-list">${blockers.length ? blockers.slice(0, 6).map(item => `<li>${escapeHtml(item.detail)}<br><span class="meta-text">${escapeHtml(item.source_service)} · ${escapeHtml(item.source_field)}</span></li>`).join("") : '<li class="detail-empty">暂无阻断</li>'}</ul></article>`,
  ].join("");
}

function renderBlockers(blockers) {
  const tbody = document.getElementById("today-blockers");
  if (!tbody) return;
  tbody.innerHTML = (blockers || []).map(row => `<tr>
    <td>${escapeHtml(row.detail)}</td>
    <td>${escapeHtml(row.source_service)}</td>
    <td><code>${escapeHtml(row.source_field)}</code></td>
  </tr>`).join("") || '<tr><td colspan="3" class="table-empty">暂无阻塞项</td></tr>';
}

function renderWorkflow(payload) {
  const root = document.getElementById("today-workflow");
  if (!root) return;
  const plan = payload.pre_market?.plan || {};
  const intraday = payload.intraday?.insight_matrix || {};
  const review = payload.post_market?.execution_review || {};
  const summary = payload.post_market?.summary || {};
  root.innerHTML = [
    `<article class="detail-card"><h3>盘前</h3><p class="detail-paragraph">${escapeHtml(plan.headline || "暂无计划归档")}</p><ul class="detail-list">${(plan.reasons || []).slice(0, 3).map(item => `<li>${escapeHtml(item)}</li>`).join("") || '<li class="detail-empty">暂无计划原因</li>'}</ul></article>`,
    `<article class="detail-card"><h3>盘中</h3><ul class="detail-list"><li>近期订单 ${fmt(intraday.recent_order_count)}</li><li>风险市场 ${escapeHtml((intraday.risk_markets || []).join(", ") || "无")}</li></ul><p class="meta-text">${escapeHtml(intraday.source_service || "")} · ${escapeHtml(intraday.source_field || "")}</p></article>`,
    `<article class="detail-card"><h3>盘后</h3><p class="detail-paragraph">${escapeHtml(summary.headline || "暂无总结归档")}</p><ul class="detail-list"><li>订单 ${fmt(review.order_count)}</li><li>未完成 ${fmt(review.unfilled_count)}</li></ul><p class="meta-text">${escapeHtml(review.source_service || "")} · ${escapeHtml(review.source_field || "")}</p></article>`,
  ].join("");
}

function renderInsightMatrix(matrix) {
  const tbody = document.getElementById("today-insight-matrix");
  if (!tbody) return;
  const rows = matrix?.rows || [];
  tbody.innerHTML = rows.map(row => {
    const insightText = (row.insights || []).map(item => `${labelStatus(item.severity || "info")}: ${item.headline || item.kind}`).join("<br>");
    const position = row.position ? `${fmt(row.position.quantity)} / ${fmt(row.position.weight * 100)}%` : "无";
    const plan = row.plan_item ? `${escapeHtml(row.plan_item.side || "")} ${fmt(row.plan_item.quantity)}` : "无计划";
    const order = row.order ? `<br>${escapeHtml(row.order.status || "")}` : "";
    const approval = row.approval ? `<br>审批 ${escapeHtml(row.approval.status || "")}` : "";
    const risks = (row.risk_rules || []).map(item => item.rule).join(", ") || "无";
    return `<tr>
      <td><strong>${escapeHtml(row.symbol)}</strong><br><span class="meta-text">${escapeHtml(row.market || "")}</span></td>
      <td>${insightText || '<span class="detail-empty">无</span>'}</td>
      <td>${escapeHtml(position)}</td>
      <td>${plan}${order}${approval}</td>
      <td>${escapeHtml(risks)}</td>
    </tr>`;
  }).join("") || '<tr><td colspan="5" class="table-empty">暂无关联行</td></tr>';
}

async function loadToday() {
  const button = document.getElementById("refresh-today");
  if (button) button.disabled = true;
  try {
    const result = await apiFetch(API.dashboardTodayData());
    if (!result.ok) throw new Error(result.error || "加载失败");
    const payload = result.data || {};
    document.getElementById("today-updated").textContent = fmtTime(payload.generated_at);
    renderDecision(payload);
    renderMarkets(payload.markets || []);
    renderHeartbeat(payload.heartbeat || {});
    renderActionQueue(payload.action_queue || {});
    renderLiveReadiness(payload.live_readiness || {});
    renderBlockers(payload.decision?.blockers || []);
    renderWorkflow(payload);
    renderInsightMatrix(payload.intraday?.insight_matrix || {});
  } catch (error) {
    showToast(error.message || "今日工作台加载失败", "error");
  } finally {
    if (button) button.disabled = false;
  }
}

document.getElementById("refresh-today")?.addEventListener("click", loadToday);
loadToday();

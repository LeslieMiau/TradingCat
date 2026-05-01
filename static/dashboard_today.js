/* TradingCat — read-only trading-day cockpit. */

function badgeClass(status) {
  if (status === "ready") return "badge-ok";
  if (status === "blocked") return "badge-fail";
  if (status === "no_trade") return "badge-warn";
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

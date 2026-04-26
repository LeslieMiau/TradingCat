async function loadAccountPage() {
  const accountId = window.location.pathname.split("/").pop();
  const result = await apiFetch(API.dashboardSummary);
  if (!result.ok) {
    document.getElementById("account-title").textContent = "账户加载失败";
    document.getElementById("account-subtitle").textContent = result.error || "不可用";
    return;
  }
  const payload = result.data ?? {};
  const account = payload.accounts?.[accountId];
  if (!account) {
    document.getElementById("account-title").textContent = "账户不存在";
    document.getElementById("account-subtitle").textContent = accountId;
    return;
  }
  document.getElementById("account-title").textContent = account.label;
  document.getElementById("account-subtitle").textContent = `净值 ${money(account.nav)} / 持仓 ${fmt(account.position_count)} / 现金 ${money(account.cash)}`;
  document.getElementById("account-updated").textContent = `截至 ${payload.as_of}`;
  document.getElementById("account-curve-title").textContent = `${account.label}净值曲线`;
  document.getElementById("account-metrics").innerHTML = [
    metricTile("净值", money(account.nav), `现金 ${money(account.cash)}`, "ok"),
    metricTile("持仓市值", money(account.position_value), `持仓数 ${fmt(account.position_count)}`, "ok"),
    metricTile("现金占比", fmtPct(account.cash_weight), "流动性", "warning"),
    metricTile("总收益", fmtPct(account.total_return), `回撤 ${fmtPct(account.drawdown)}`, (account.total_return ?? 0) >= 0 ? "ok" : "blocked"),
    metricTile("日盈亏", money(account.daily_pnl), `周盈亏 ${money(account.weekly_pnl)}`, (account.daily_pnl ?? 0) >= 0 ? "ok" : "blocked"),
    metricTile("市场", labelMarket(account.account), "账户", "empty"),
  ].join("");
  renderCurve("account-nav-curve", account.nav_curve || []);

  const allocation = account.allocation_mix || {};
  document.getElementById("account-allocation-bars").innerHTML = `
    <div class="stack-row">
      <label>现金 / 股票 / 期权</label>
      <div class="stack-track">
        <span class="stack-segment cash" style="width:${(allocation.cash ?? 0) * 100}%"></span>
        <span class="stack-segment equity" style="width:${(allocation.equity ?? 0) * 100}%"></span>
        <span class="stack-segment option" style="width:${(allocation.option ?? 0) * 100}%"></span>
      </div>
    </div>
  `;
  document.getElementById("account-summary-list").innerHTML = [
    `现金: ${money(account.cash)}`,
    `持仓市值: ${money(account.position_value)}`,
    `现金占比: ${fmtPct(account.cash_weight)}`,
    `总收益: ${fmtPct(account.total_return)}`,
    `回撤: ${fmtPct(account.drawdown)}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const tradingPlan = payload.trading_plan || {};
  const gate = tradingPlan.gate || {};
  const recentOrders = payload.details?.recent_orders || [];
  const recentApprovals = tradingPlan.recent_approvals || [];
  const accountPlanItems = account.plan_items || [];
  document.getElementById("account-plan-list").innerHTML = [
    `计划条数: ${fmt(accountPlanItems.length)}`,
    `门禁就绪: ${fmt(gate.ready)}`,
    `门禁阻塞: ${fmt(gate.should_block)}`,
    `策略档位: ${fmt(gate.policy_stage)}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const positionsBody = document.getElementById("account-positions-table");
  positionsBody.innerHTML = (account.positions || []).length
    ? account.positions.map((row) => `
        <tr>
          <td><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(row.name ?? "")}</span></td>
          <td>${escapeHtml(labelMarket(row.market))}</td>
          <td>${escapeHtml(labelAssetClass(row.asset_class))}</td>
          <td>${escapeHtml(fmt(row.quantity, 4))}</td>
          <td>${escapeHtml(money(row.average_cost))}</td>
          <td>${escapeHtml(money(row.market_value))}</td>
          <td>${escapeHtml(fmtPct(row.weight))}</td>
          <td class="${row.unrealized_pnl >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(money(row.unrealized_pnl))}</td>
          <td class="${(row.unrealized_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.unrealized_return))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="9" class="table-empty">当前账户没有持仓。</td></tr>';

  const planBody = document.getElementById("account-plan-table");
  planBody.innerHTML = accountPlanItems.length
    ? accountPlanItems.map((row) => `
        <tr>
          <td>${escapeHtml(row.strategy_id)}</td>
          <td><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(labelMarket(row.market))}</span></td>
          <td>${escapeHtml(labelSide(row.side))}</td>
          <td>${escapeHtml(fmt(row.quantity, 4))}</td>
          <td>${escapeHtml(row.target_weight == null ? "暂无" : fmtPct(row.target_weight))}</td>
          <td>${escapeHtml(row.reference_price == null ? "暂无" : money(row.reference_price))}</td>
          <td>${escapeHtml(row.requires_approval ? "人工" : "自动")}</td>
          <td>${escapeHtml(row.reason ?? "")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="8" class="table-empty">当前账户今日没有交易计划。</td></tr>';

  const executionRows = accountPlanItems.map((row) => {
    const order = recentOrders.find((item) => item.order_intent_id === row.intent_id);
    const approval = recentApprovals.find((item) => item.intent_id === row.intent_id);
    return {
      ...row,
      order_status: order?.status || (row.requires_approval ? "pending" : "not_submitted"),
      filled_quantity: order?.filled_quantity ?? null,
      approval_status: approval?.status || (row.requires_approval ? "pending" : "auto"),
    };
  });
  const submittedCount = executionRows.filter((row) => row.order_status !== "not_submitted" && row.order_status !== "missing").length;
  const filledCount = executionRows.filter((row) => row.order_status === "filled").length;
  const pendingApprovalCount = executionRows.filter((row) => row.approval_status === "pending").length;
  document.getElementById("account-execution-metrics").innerHTML = [
    metricTile("计划单", fmt(executionRows.length), "今日计划条目", executionRows.length ? "ok" : "warning"),
    metricTile("已出单", fmt(submittedCount), "最近订单", submittedCount ? "ok" : "warning"),
    metricTile("已成交", fmt(filledCount), "成交订单", filledCount ? "ok" : "warning"),
    metricTile("待审批", fmt(pendingApprovalCount), "人工复核", pendingApprovalCount ? "warning" : "ok"),
  ].join("");
  document.getElementById("account-execution-table").innerHTML = executionRows.length
    ? executionRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.strategy_id)}</td>
          <td><strong>${escapeHtml(row.symbol)}</strong></td>
          <td>${escapeHtml(fmt(row.quantity, 4))}</td>
          <td class="status-${statusTone(row.order_status)}">${escapeHtml(labelStatus(row.order_status))}</td>
          <td>${escapeHtml(row.filled_quantity == null ? "暂无" : fmt(row.filled_quantity, 4))}</td>
          <td class="status-${statusTone(row.approval_status)}">${escapeHtml(labelStatus(row.approval_status))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="6" class="table-empty">当前账户没有执行链路数据。</td></tr>';
  const blockers = [];
  if (pendingApprovalCount > 0) blockers.push(`${pendingApprovalCount} 笔计划单待人工审批。`);
  if (executionRows.length > submittedCount) blockers.push(`${executionRows.length - submittedCount} 笔计划单还没转成订单状态。`);
  if (!blockers.length) blockers.push("当前账户没有明显执行卡点。");
  document.getElementById("account-execution-blockers").innerHTML = blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
  document.getElementById("account-execution-progress").innerHTML = [
    `计划单: ${fmt(executionRows.length)}`,
    `已出单: ${fmt(submittedCount)}`,
    `已成交: ${fmt(filledCount)}`,
    `待审批: ${fmt(pendingApprovalCount)}`,
  ].map((item) => `<li>${escapeHtml(item)}</li>`).join("");

  const exposureByStrategy = new Map();
  accountPlanItems.forEach((row) => {
    if (!exposureByStrategy.has(row.strategy_id)) {
      exposureByStrategy.set(row.strategy_id, {
        strategy_id: row.strategy_id,
        plan_count: 0,
        target_weight: 0,
        manual_count: 0,
        symbols: new Set(),
      });
    }
    const item = exposureByStrategy.get(row.strategy_id);
    item.plan_count += 1;
    item.target_weight += Number(row.target_weight || 0);
    item.manual_count += row.requires_approval ? 1 : 0;
    item.symbols.add(row.symbol);
  });
  const exposureRows = [...exposureByStrategy.values()].sort((left, right) => right.target_weight - left.target_weight);
  document.getElementById("account-strategy-exposure-table").innerHTML = exposureRows.length
    ? exposureRows.map((row) => `
        <tr>
          <td>${escapeHtml(row.strategy_id)}</td>
          <td>${escapeHtml(fmt(row.plan_count))}</td>
          <td>${escapeHtml(fmtPct(row.target_weight))}</td>
          <td>${escapeHtml(fmt(row.manual_count))}</td>
          <td>${escapeHtml([...row.symbols].join(", "))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前账户没有策略暴露。</td></tr>';
}

loadAccountPage();

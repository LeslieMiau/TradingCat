(function attachDashboardStrategy(global) {
  function planNote(state) {
    return state.summary?.journal?.latest_plan ?? {};
  }

  function labelSide(value) {
    if (value === "buy") return "买入";
    if (value === "sell") return "卖出";
    return displayValue(value);
  }

  function labelPlanStatus(value) {
    if (value === "planned") return "有计划";
    if (value === "no_trade") return "无交易";
    if (value === "blocked") return "已阻塞";
    return displayValue(value);
  }

  function renderStrategies(state) {
    const metricsEl = document.getElementById("strategy-metrics");
    const cards = document.getElementById("strategy-cards");
    const table = document.getElementById("strategies-table");
    if (!metricsEl && !cards && !table) {
      return;
    }

    const strategies = state.summary?.strategies ?? {};
    const snapshotNote = strategies.snapshot_status && strategies.snapshot_status !== "ready"
      ? `研究快照状态：${labelStatus(strategies.snapshot_status)} ${strategies.snapshot_reason ?? ""}`.trim()
      : null;
    const metrics = strategies.portfolio_metrics ?? {};
    if (metricsEl) {
      metricsEl.innerHTML = [
        metricTile("组合年化", fmtPct(metrics.annualized_return), `通过 ${fmt(strategies.portfolio_passed)}`, strategies.portfolio_passed ? "ok" : "warning"),
        metricTile("组合夏普", fmt(metrics.sharpe), `策略数 ${fmt(metrics.strategy_count)}`, "ok"),
        metricTile("组合最大回撤", fmtPct(metrics.max_drawdown), `Calmar ${fmt(metrics.calmar)}`, "warning"),
        metricTile("通过策略", fmt((strategies.accepted_strategy_ids ?? []).length), `已通过 ${(strategies.accepted_strategy_ids ?? []).join(", ") || "暂无"}`, (strategies.accepted_strategy_ids ?? []).length ? "ok" : "warning"),
        metricTile("数据阻塞", fmt(strategies.blocked_by_data_count), "因数据不足阻塞", strategies.blocked_by_data_count ? "blocked" : "ok"),
        metricTile("仅纸面", fmt(strategies.paper_only_count), "仅纸面跟踪", strategies.paper_only_count ? "warning" : "ok"),
      ].join("");
    }

    const rows = strategies.rows ?? [];
    if (cards) {
      cards.innerHTML = rows.length
        ? rows
            .map(
              (row) => `
                <article class="detail-card">
                  <h3><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.name)}</a></h3>
                  <p class="detail-paragraph">${escapeHtml(row.thesis)}</p>
                  <div class="tag-row">
                    <span class="badge status-${badgeTone(row.display_status === "blocked_by_data" ? "blocked" : row.display_status === "paper_only" ? "warning" : row.action)}">${escapeHtml(labelStatus(row.display_status ?? row.action))}</span>
                    <span class="tag">${escapeHtml(row.cadence)}</span>
                    <span class="tag">${escapeHtml(row.capacity_tier)}</span>
                  </div>
                  <p class="detail-paragraph">${escapeHtml(row.status_reason ?? "")}</p>
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
    }

    if (table) {
      table.innerHTML = rows.length
        ? rows
            .map(
              (row) => `
                <tr>
                  <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.name)}</a></strong><br /><span class="meta-text">${escapeHtml(row.strategy_id)}</span></td>
                  <td><span class="badge status-${badgeTone(row.display_status === "blocked_by_data" ? "blocked" : row.display_status === "paper_only" ? "warning" : row.action)}">${escapeHtml(labelStatus(row.display_status ?? row.action))}</span></td>
                  <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
                  <td>${escapeHtml(fmt(row.sharpe))}</td>
                  <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
                  <td>${escapeHtml(fmt(row.calmar))}</td>
                  <td>${escapeHtml(`${displayValue(row.stability_bucket)} / 通过 ${fmtPct(row.validation_pass_rate)}`)}<br /><span class="meta-text">${escapeHtml(row.status_reason ?? "")}</span></td>
                </tr>
              `,
            )
            .join("")
        : '<tr><td colspan="7" class="table-empty">当前没有策略指标。</td></tr>';
    }

    const perfTop = rows.slice().sort((a, b) => (b.annualized_return ?? 0) - (a.annualized_return ?? 0)).slice(0, 5);
    if (document.getElementById("strategy-perf-top-list")) {
      setList("strategy-perf-top-list", perfTop.map((row) => `${row.name}: 年化 ${fmtPct(row.annualized_return)} / 夏普 ${fmt(row.sharpe)}`), "暂无策略表现排名。");
    }
    const execTop = rows.filter((row) => row.action === "active" || row.action === "deploy").slice(0, 5);
    if (document.getElementById("strategy-exec-top-list")) {
      setList("strategy-exec-top-list", execTop.map((row) => `${row.name}: ${labelStatus(row.action)} / 年化 ${fmtPct(row.annualized_return)}`), "暂无执行中策略。");
    }
    if (document.getElementById("account-strategy-matrix-list")) {
      setList(
        "account-strategy-matrix-list",
        ["total", "CN", "HK", "US"].map((key) => {
          const count = rows.filter((row) => (row.markets ?? []).includes(key) || key === "total").length;
          return `${labelMarket(key)}: ${fmt(count)} 条策略`;
        }),
        "暂无账户-策略矩阵。",
      );
    }
    const nextActions = state.summary?.strategies?.next_actions ?? [];
    if (document.getElementById("research-group-summary-list")) {
      const items = snapshotNote ? [snapshotNote, ...nextActions] : nextActions;
      setList("research-group-summary-list", items.length ? items : ["暂无研究分组总览。"], "暂无研究分组总览。");
    }

    const planItems = state.summary?.trading_plan?.items ?? [];
    const strategyFundMap = new Map();
    planItems.forEach((item) => {
      const strategyId = item.strategy_id || "unknown";
      const notional = Number(item.reference_price || 0) * Number(item.quantity || 0);
      strategyFundMap.set(strategyId, (strategyFundMap.get(strategyId) || 0) + notional);
    });
    const fundRows = [...strategyFundMap.entries()].sort((left, right) => right[1] - left[1]).slice(0, 8);
    const totalFund = fundRows.reduce((sum, row) => sum + row[1], 0);
    const fundTable = document.getElementById("strategy-fund-top-table");
    if (fundTable) {
      fundTable.innerHTML = fundRows.length
        ? fundRows.map(([strategyId, notional]) => `
            <tr>
              <td><a href="/dashboard/strategies/${encodeURIComponent(strategyId)}">${escapeHtml(strategyId)}</a></td>
              <td>${escapeHtml(money(notional))}</td>
              <td>${escapeHtml(totalFund ? fmtPct(notional / totalFund) : "暂无")}</td>
              <td>${escapeHtml(fmt(planItems.filter((item) => item.strategy_id === strategyId).length))}</td>
            </tr>
          `).join("")
        : '<tr><td colspan="4" class="table-empty">当前没有策略资金占用数据。</td></tr>';
    }
  }

  function renderStrategyPlanBreakdown(state) {
    const metricsEl = document.getElementById("strategy-plan-metrics");
    const table = document.getElementById("strategy-plan-table");
    if (!metricsEl && !table) {
      return;
    }

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
    if (metricsEl) {
      metricsEl.innerHTML = [
        metricTile("涉及策略", fmt(rows.length), "今日计划涉及策略", rows.length ? "ok" : "warning"),
        metricTile("总计划单", fmt(items.length), "计划意图数", items.length ? "ok" : "warning"),
        metricTile("预估总金额", money(rows.reduce((sum, row) => sum + row.notional, 0)), "预估总名义金额", rows.length ? "ok" : "empty"),
        metricTile("待审批策略", fmt(rows.filter((row) => row.approvalCount > 0).length), "需要人工处理的策略", approvals.length ? "warning" : "ok"),
      ].join("");
    }

    if (table) {
      table.innerHTML = rows.length
        ? rows.map((row) => `
            <tr>
              <td><span class="badge status-${badgeTone(row.approvalCount ? "warning" : "ok")}">${escapeHtml(row.market)}</span></td>
              <td>${escapeHtml(fmt(row.itemCount))}</td>
              <td>${escapeHtml(money(row.notional))}</td>
              <td>${escapeHtml(fmt(row.approvalCount))}</td>
              <td>${escapeHtml([...row.strategies].slice(0, 3).map(labelMarket).join(", ") || "暂无")}</td>
            </tr>
          `).join("")
        : '<tr><td colspan="5" class="table-empty">今天还没有按策略拆分的计划。</td></tr>';
    }
  }

  function renderMarketPlanBreakdown(state) {
    const table = document.getElementById("market-plan-table");
    if (!table) {
      return;
    }

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
    table.innerHTML = rows.length
      ? rows.map((row) => `
          <tr>
            <td><span class="badge status-${badgeTone(row.approvalCount ? "warning" : "ok")}">${escapeHtml(row.market)}</span></td>
            <td>${escapeHtml(fmt(row.itemCount))}</td>
            <td>${escapeHtml(money(row.notional))}</td>
            <td>${escapeHtml(fmt(row.approvalCount))}</td>
            <td>${escapeHtml([...row.strategies].slice(0, 3).join(", ") || "暂无")}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="5" class="table-empty">今天还没有按市场拆分的计划。</td></tr>';
  }

  function renderMarketBudget(state) {
    const table = document.getElementById("market-budget-table");
    if (!table) {
      return;
    }

    const budgetRows = state.summary?.market_budget ?? [];
    table.innerHTML = budgetRows.length
      ? budgetRows.map((row) => `
          <tr>
            <td>${escapeHtml(labelMarket(row.market))}</td>
            <td>${escapeHtml(row.actualWeight == null ? "暂无" : fmtPct(row.actualWeight))}</td>
            <td>${escapeHtml(fmtPct(row.targetWeight))}</td>
            <td class="${Math.abs(Number(row.delta || 0)) <= 0.02 ? "status-ok" : Number(row.delta || 0) > 0 ? "status-warning" : "status-blocked"}">
              ${escapeHtml(row.delta == null ? "暂无" : fmtPct(row.delta))}
              <span class="badge status-${badgeTone(row.action === "aligned" ? "ok" : row.action === "overweight" ? "warning" : row.action === "underweight" ? "blocked" : "empty")}">${escapeHtml(labelStatus(row.action))}</span>
            </td>
          </tr>
        `).join("")
      : '<tr><td colspan="4" class="table-empty">当前没有市场预算数据。</td></tr>';
  }

  function renderCandidates(state) {
    const metricsEl = document.getElementById("candidate-metrics");
    const table = document.getElementById("candidates-table");
    const groupMetrics = document.getElementById("candidate-group-metrics");
    const groupsTable = document.getElementById("candidate-groups-table");
    if (!metricsEl && !table && !groupMetrics && !groupsTable) {
      return;
    }

    const candidates = state.summary?.candidates ?? {};
    const snapshotStatus = candidates.snapshot_status;
    const snapshotNote = snapshotStatus && snapshotStatus !== "ready"
      ? `研究快照状态：${labelStatus(snapshotStatus)} ${candidates.snapshot_reason ?? ""}`.trim()
      : null;
    if (metricsEl) {
      metricsEl.innerHTML = [
        metricTile("可继续研究", fmt(candidates.deploy_candidate_count), "可部署候选", candidates.deploy_candidate_count ? "ok" : "warning"),
        metricTile("仅纸面跟踪", fmt(candidates.paper_only_count), "纸面跟踪", candidates.paper_only_count ? "warning" : "ok"),
        metricTile("应淘汰", fmt(candidates.rejected_count), "淘汰", candidates.rejected_count ? "blocked" : "ok"),
        metricTile("下一步", fmt((candidates.next_actions ?? []).length), (candidates.next_actions ?? [])[0] ?? "暂无动作", "warning"),
      ].join("");
    }

    const rows = candidates.rows ?? [];
    const tops = candidates.top_candidates ?? [];
    if (document.getElementById("candidate-top-list")) {
      setList(
        "candidate-top-list",
        tops.map((row) => `${row.strategy_id}: ${labelVerdict(row.verdict)} / 评分 ${fmt(row.profitability_score)}`),
        "当前没有候选策略。",
      );
    }
    if (document.getElementById("candidate-actions-list")) {
      const actions = snapshotNote ? [snapshotNote, ...(candidates.next_actions ?? [])] : (candidates.next_actions ?? []);
      setList("candidate-actions-list", actions, "当前没有额外研究动作。");
    }
    if (table) {
      table.innerHTML = rows.length
        ? rows.map((row) => `
            <tr>
              <td><strong><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></strong></td>
              <td><span class="badge status-${badgeTone(row.verdict === "deploy_candidate" ? "ok" : row.verdict === "paper_only" ? "warning" : "blocked")}">${escapeHtml(labelVerdict(row.verdict))}</span></td>
              <td>${escapeHtml(fmt(row.profitability_score))}</td>
              <td>${escapeHtml(fmtPct(row.annualized_return))}</td>
              <td>${escapeHtml(fmt(row.sharpe))}</td>
              <td>${escapeHtml(fmtPct(row.max_drawdown))}</td>
              <td>${escapeHtml(fmt(row.max_selected_correlation))}</td>
            </tr>
          `).join("")
        : '<tr><td colspan="7" class="table-empty">当前没有候选策略评分。</td></tr>';
    }

    const verdictBuckets = new Map([
      ["deploy_candidate", { label: "deploy_candidate", rows: [] }],
      ["paper_only", { label: "paper_only", rows: [] }],
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

    if (groupMetrics) {
      groupMetrics.innerHTML = [
        metricTile("可部署组", fmt(groupRows.find((row) => row.label === "deploy_candidate")?.count ?? 0), "值得继续投入研究", (groupRows.find((row) => row.label === "deploy_candidate")?.count ?? 0) ? "ok" : "warning"),
        metricTile("纸面组", fmt(groupRows.find((row) => row.label === "paper_only")?.count ?? 0), "先观察再投入", (groupRows.find((row) => row.label === "paper_only")?.count ?? 0) ? "warning" : "ok"),
        metricTile("淘汰组", fmt(groupRows.find((row) => row.label === "reject")?.count ?? 0), "快速剔除", (groupRows.find((row) => row.label === "reject")?.count ?? 0) ? "blocked" : "ok"),
        metricTile("总候选", fmt(rows.length), "候选策略池", rows.length ? "ok" : "warning"),
      ].join("");
    }
    if (groupsTable) {
      groupsTable.innerHTML = groupRows.length
        ? groupRows.map((row) => `
            <tr>
              <td><span class="badge status-${badgeTone(row.label === "deploy_candidate" ? "ok" : row.label === "paper_only" ? "warning" : row.label === "reject" ? "blocked" : "empty")}">${escapeHtml(labelVerdict(row.label))}</span></td>
              <td>${escapeHtml(fmt(row.count))}</td>
              <td>${escapeHtml(row.avgProfitability == null ? "暂无" : fmt(row.avgProfitability))}</td>
              <td>${escapeHtml(row.avgAnnualizedReturn == null ? "暂无" : fmtPct(row.avgAnnualizedReturn))}</td>
              <td>${escapeHtml(row.avgSharpe == null ? "暂无" : fmt(row.avgSharpe))}</td>
              <td>${escapeHtml(row.avgMaxDrawdown == null ? "暂无" : fmtPct(row.avgMaxDrawdown))}</td>
            </tr>
          `).join("")
        : '<tr><td colspan="6" class="table-empty">当前没有研究分组数据。</td></tr>';
    }
  }

  function renderPlan(state) {
    const metricsEl = document.getElementById("plan-metrics");
    const headlineEl = document.getElementById("journal-plan-headline");
    const table = document.getElementById("plan-table");
    if (!metricsEl || !headlineEl || !table) {
      return;
    }

    const tradingPlan = state.summary?.trading_plan ?? {};
    const plan = planNote(state);
    const account = global.DashboardAccounts?.accountData(state) ?? {};
    const gate = tradingPlan.gate ?? {};
    const marketAwareness = tradingPlan.market_awareness ?? {};
    const rows = account.plan_items ?? [];
    metricsEl.innerHTML = [
      metricTile("信号", fmt(tradingPlan.signal_count), `意图 ${fmt(tradingPlan.intent_count)}`, "ok"),
      metricTile("自动 / 手工", `${fmt(tradingPlan.automated_count)} / ${fmt(tradingPlan.manual_count)}`, "自动 / 手工", tradingPlan.manual_count ? "warning" : "ok"),
      metricTile("计划状态", labelPlanStatus(plan.status), plan.headline ?? "暂无标题", badgeTone(plan.status)),
      metricTile("执行门禁", gate.should_block ? "已阻塞" : gate.ready ? "已就绪" : "预警", `策略档位 ${fmt(gate.policy_stage)}`, gate.should_block ? "blocked" : gate.ready ? "ok" : "warning"),
    ].join("");
    headlineEl.textContent = plan.headline ?? "暂无计划说明。";
    if (document.getElementById("journal-plan-reasons")) {
      setList("journal-plan-reasons", plan.reasons ?? [], "今日没有额外说明。");
    }
    if (document.getElementById("plan-side-notes")) {
      setList(
        "plan-side-notes",
        [
          `当前账户: ${displayValue(account.label)}`,
          `今日计划数: ${fmt(rows.length)}`,
          `待审批: ${fmt(Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals.length : tradingPlan.pending_approvals ?? 0)}`,
          `门禁就绪: ${fmt(gate.ready)}`,
          `市场姿态: ${displayValue(marketAwareness.overall_regime)}`,
          `操作节奏: ${displayValue(marketAwareness.risk_posture)}`,
          `信号数: ${fmt(plan.counts?.signal_count)}`,
          `自动 / 手工: ${fmt(plan.counts?.automated_count)} / ${fmt(plan.counts?.manual_count)}`,
        ],
        "暂无计划侧说明。",
      );
    }

    const planBody = [];
    if (marketAwareness.overall_regime) {
      planBody.push(
        `市场感知：${marketAwareness.overall_regime} / ${displayValue(marketAwareness.risk_posture)} / ${displayValue(marketAwareness.confidence)}。`,
      );
      (marketAwareness.actions ?? []).slice(0, 2).forEach((item) => {
        if (item?.text) {
          planBody.push(`市场建议：${item.text}`);
        }
      });
    }
    (plan.reasons ?? []).forEach((item) => planBody.push(`原因：${item}`));
    (plan.items ?? []).slice(0, 5).forEach((item) => {
      const side = item.side === "buy" ? "买入" : item.side === "sell" ? "卖出" : "未知";
      const target = item.target_weight == null ? "暂无" : fmtPct(item.target_weight);
      const qty = item.quantity == null ? "暂无" : fmt(item.quantity, 4);
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
    if (document.getElementById("plan-body-list")) {
      setList("plan-body-list", planBody, "今天的计划正文暂无内容。");
    }

    if (tradingPlan.error) {
      table.innerHTML = `<tr><td colspan="8" class="table-empty">${escapeHtml(tradingPlan.error)}</td></tr>`;
    } else if (!rows.length) {
      table.innerHTML = '<tr><td colspan="8" class="table-empty">当前账户今日没有交易计划。</td></tr>';
    } else {
      table.innerHTML = rows
        .map(
          (row) => `
            <tr>
              <td><a href="/dashboard/strategies/${encodeURIComponent(row.strategy_id)}">${escapeHtml(row.strategy_id)}</a></td>
              <td><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(row.market)}</span></td>
              <td>${escapeHtml(labelSide(row.side))}</td>
              <td>${escapeHtml(fmt(row.quantity, 4))}</td>
              <td>${escapeHtml(row.target_weight == null ? "暂无" : fmtPct(row.target_weight))}</td>
              <td>${escapeHtml(row.reference_price == null ? "暂无" : money(row.reference_price))}</td>
              <td><span class="badge status-${row.requires_approval ? "warning" : "ok"}">${row.requires_approval ? "人工" : "自动"}</span></td>
              <td>${escapeHtml(row.reason ?? "")}</td>
            </tr>
          `,
        )
        .join("");
    }
  }

  function renderSignalFunnel(state) {
    const metricsEl = document.getElementById("signal-funnel-metrics");
    const table = document.getElementById("signal-funnel-table");
    if (!metricsEl && !table) {
      return;
    }

    const tradingPlan = state.summary?.trading_plan ?? {};
    const recentOrders = state.summary?.details?.recent_orders ?? [];
    const signals = Number(tradingPlan.signal_count || 0);
    const intents = Number(tradingPlan.intent_count || 0);
    const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals.length : Number(tradingPlan.pending_approvals || 0);
    const orders = recentOrders.length;
    const fills = recentOrders.filter((item) => item.status === "filled").length;

    const ratio = (value, base) => {
      if (!base) return "暂无";
      return fmtPct(value / base);
    };

    if (metricsEl) {
      metricsEl.innerHTML = [
        metricTile("信号", fmt(signals), "研究信号", signals ? "ok" : "warning"),
        metricTile("计划", fmt(intents), `信号转化率 ${ratio(intents, signals)}`, intents ? "ok" : "warning"),
        metricTile("待审批", fmt(approvals), `计划占比 ${ratio(approvals, intents)}`, approvals ? "warning" : "ok"),
        metricTile("出单", fmt(orders), `计划转化率 ${ratio(orders, intents)}`, orders ? "ok" : "warning"),
        metricTile("成交", fmt(fills), `订单成交率 ${ratio(fills, orders)}`, fills ? "ok" : "warning"),
      ].join("");
    }

    if (table) {
      const rows = [
        { stage: "研究信号", count: signals, rate: "100.00%", note: "策略生成的原始候选信号" },
        { stage: "进入计划", count: intents, rate: ratio(intents, signals), note: "通过风控与 gate 后形成计划单" },
        { stage: "待审批", count: approvals, rate: ratio(approvals, intents), note: "需要人工确认的计划单" },
        { stage: "已出订单", count: orders, rate: ratio(orders, intents), note: "已经推送到 broker 的订单" },
        { stage: "已成交", count: fills, rate: ratio(fills, orders), note: "最近订单里状态为 filled 的数量" },
      ];
      table.innerHTML = rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.stage)}</td>
            <td>${escapeHtml(fmt(row.count))}</td>
            <td>${escapeHtml(row.rate)}</td>
            <td>${escapeHtml(row.note)}</td>
          </tr>
        `).join("");
    }
  }

  global.DashboardStrategy = {
    planNote,
    labelSide,
    labelPlanStatus,
    renderStrategies,
    renderStrategyPlanBreakdown,
    renderMarketPlanBreakdown,
    renderMarketBudget,
    renderCandidates,
    renderPlan,
    renderSignalFunnel,
  };
})(window);

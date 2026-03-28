(function attachDashboardOperations(global) {
  function summaryNote(state) {
    return state.summary?.journal?.latest_summary ?? {};
  }

  function formatGateReason(reason) {
    if (typeof reason === "string") {
      return { type: "gate", detail: reason };
    }
    return {
      type: reason?.type ?? "gate",
      detail: reason?.detail ?? "",
    };
  }

  function gateReasonText(reason) {
    const normalized = formatGateReason(reason);
    return normalized.detail ? `${normalized.type}: ${normalized.detail}` : normalized.type;
  }

  function renderExecutionBlockers(state) {
    const metricsEl = document.getElementById("execution-blocker-metrics");
    const table = document.getElementById("execution-blocker-table");
    if (!metricsEl && !table) {
      return;
    }

    const tradingPlan = state.summary?.trading_plan ?? {};
    const details = state.summary?.details ?? {};
    const gateReasons = details.execution_gate?.reasons ?? [];
    const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals : [];
    const recentOrders = details.recent_orders ?? [];
    const workingOrders = recentOrders.filter((item) => item.status && item.status !== "filled" && item.status !== "cancelled");
    const rejectedOrders = recentOrders.filter((item) => item.status === "rejected");

    const rows = [
      {
        type: "gate",
        count: gateReasons.length,
        tone: gateReasons.length ? "blocked" : "ok",
        note: gateReasons.length ? gateReasons.map(gateReasonText).join(" | ") : "当前没有 execution gate 阻塞。",
      },
      {
        type: "approval",
        count: approvals.length,
        tone: approvals.length ? "warning" : "ok",
        note: approvals.length ? approvals.slice(0, 3).map((item) => `${item.symbol}/${item.market}`).join(", ") : "当前没有待审批单。",
      },
      {
        type: "working_order",
        count: workingOrders.length,
        tone: workingOrders.length ? "warning" : "ok",
        note: workingOrders.length ? workingOrders.slice(0, 3).map((item) => `${item.broker_order_id}/${item.status}`).join(", ") : "当前没有处理中订单。",
      },
      {
        type: "rejected_order",
        count: rejectedOrders.length,
        tone: rejectedOrders.length ? "blocked" : "ok",
        note: rejectedOrders.length ? rejectedOrders.slice(0, 3).map((item) => `${item.broker_order_id}/${item.symbol}`).join(", ") : "当前没有被拒订单。",
      },
    ];

    if (metricsEl) {
      metricsEl.innerHTML = [
        metricTile("Gate 卡点", fmt(rows[0].count), "execution gate reasons", rows[0].tone),
        metricTile("审批卡点", fmt(rows[1].count), "pending approvals", rows[1].tone),
        metricTile("订单处理中", fmt(rows[2].count), "working broker orders", rows[2].tone),
        metricTile("拒单", fmt(rows[3].count), "rejected broker orders", rows[3].tone),
      ].join("");
    }
    if (table) {
      table.innerHTML = rows.map((row) => `
          <tr>
            <td>${escapeHtml(row.type)}</td>
            <td>${escapeHtml(fmt(row.count))}</td>
            <td><span class="badge status-${badgeTone(row.tone)}">${escapeHtml(row.tone)}</span></td>
            <td>${escapeHtml(row.note)}</td>
          </tr>
        `).join("");
    }
  }

  function renderPriorityActions(state) {
    const table = document.getElementById("priority-actions-table");
    if (!table) {
      return;
    }

    const details = state.summary?.details ?? {};
    const tradingPlan = state.summary?.trading_plan ?? {};
    const strategyActions = state.summary?.strategies?.next_actions ?? [];
    const candidateActions = state.summary?.candidates?.next_actions ?? [];
    const rebalanceRows = (state.rebalance?.rebalance_actions ?? []).filter((row) => row.action !== "hold");
    const approvals = Array.isArray(tradingPlan.pending_approvals) ? tradingPlan.pending_approvals : [];
    const gateReasons = details.execution_gate?.reasons ?? [];

    const actions = [];
    gateReasons.forEach((item, index) => {
      const gateReason = formatGateReason(item);
      actions.push({
        priority: index + 1,
        type: "gate",
        action: gateReason.type,
        reason: gateReason.detail,
      });
    });
    approvals.slice(0, 3).forEach((item) => {
      actions.push({
        priority: actions.length + 1,
        type: "approval",
        action: `Approve ${item.symbol}`,
        reason: item.reason || `${item.market} / ${item.side}`,
      });
    });
    rebalanceRows.slice(0, 3).forEach((item) => {
      actions.push({
        priority: actions.length + 1,
        type: "rebalance",
        action: `${item.action} ${item.symbol}`,
        reason: `delta ${fmtPct(item.delta)}`,
      });
    });
    [...strategyActions, ...candidateActions].slice(0, 4).forEach((item) => {
      actions.push({
        priority: actions.length + 1,
        type: "research",
        action: "Review strategy",
        reason: item,
      });
    });

    table.innerHTML = actions.length
      ? actions.slice(0, 10).map((row) => `
          <tr>
            <td>${escapeHtml(String(row.priority))}</td>
            <td><span class="badge status-${badgeTone(row.type === "gate" ? "blocked" : row.type === "approval" ? "warning" : row.type === "rebalance" ? "warning" : "ok")}">${escapeHtml(row.type)}</span></td>
            <td>${escapeHtml(row.action)}</td>
            <td>${escapeHtml(row.reason)}</td>
          </tr>
        `).join("")
      : '<tr><td colspan="4" class="table-empty">当前没有需要优先处理的动作。</td></tr>';
  }

  function renderSummaries(state) {
    const headlineEl = document.getElementById("journal-summary-headline");
    const queueMetrics = document.getElementById("queue-metrics");
    if (!headlineEl && !queueMetrics) {
      return;
    }

    const daily = state.summary?.summaries?.daily ?? {};
    const weekly = state.summary?.summaries?.weekly ?? {};
    const details = state.summary?.details ?? {};
    const note = summaryNote(state);
    const blockers = [
      ...(details.execution_gate?.reasons ?? []).map(gateReasonText),
      ...(details.live_acceptance?.blockers ?? []),
      ...(note.blockers ?? []),
    ];
    const actions = [
      ...(state.summary?.strategies?.next_actions ?? []),
      ...(daily.next_actions ?? []),
      ...(weekly.next_actions ?? []),
      ...(note.next_actions ?? []),
    ];

    if (headlineEl) {
      headlineEl.textContent = note.headline ?? "暂无总结。";
    }

    const bodyParts = [
      ...(note.highlights ?? []),
      ...(note.blockers ?? []).map((item) => `阻塞: ${item}`),
      ...(note.next_actions ?? []).map((item) => `下一步: ${item}`),
    ];
    const dailyItems = (note.highlights?.length ? note.highlights : daily.highlights ?? []).concat(bodyParts.length ? bodyParts : []);
    const uniqueDaily = [...new Set(dailyItems)];
    if (document.getElementById("daily-highlights")) {
      setList("daily-highlights", uniqueDaily, "今日暂无摘要。");
    }
    if (document.getElementById("weekly-highlights")) {
      setList("weekly-highlights", weekly.highlights ?? [], "本周暂无摘要。");
    }
    if (document.getElementById("blockers-list")) {
      const mergedBlockers = [...blockers, ...actions.map((item) => `待处理: ${item}`)];
      setList("blockers-list", mergedBlockers, "当前没有阻塞项或待处理动作。");
    }
    if (document.getElementById("global-incidents-list")) {
      setList(
        "global-incidents-list",
        (state.incidents?.events ?? []).slice(0, 6).map((item) => `${item.occurred_at} / ${item.category} / ${item.label}`),
        "最近没有关键事件。",
      );
    }

    const rawApprovals = state.summary?.trading_plan?.pending_approvals;
    const approvals = Array.isArray(rawApprovals) ? rawApprovals : [];
    const recentOrders = state.summary?.details?.recent_orders ?? [];
    const filledOrders = recentOrders.filter((item) => item.status === "filled").length;
    const workingOrders = recentOrders.filter((item) => item.status && item.status !== "filled" && item.status !== "cancelled").length;
    if (queueMetrics) {
      queueMetrics.innerHTML = [
        metricTile("待审批", fmt(approvals.length), "pending approval queue", approvals.length ? "warning" : "ok"),
        metricTile("最近订单", fmt(recentOrders.length), "recent broker orders", recentOrders.length ? "ok" : "warning"),
        metricTile("已成交", fmt(filledOrders), "filled recently", filledOrders ? "ok" : "warning"),
        metricTile("处理中", fmt(workingOrders), "submitted / pending", workingOrders ? "warning" : "ok"),
      ].join("");
    }
    if (document.getElementById("queue-approvals-list")) {
      setList(
        "queue-approvals-list",
        approvals.slice(0, 6).map((item) => `${item.symbol} / ${item.market} / ${item.side} / ${item.status}`),
        "当前没有待审批单。",
      );
    }
    if (document.getElementById("queue-orders-list")) {
      setList(
        "queue-orders-list",
        recentOrders.slice(0, 6).map((item) => `${item.broker_order_id} / ${item.status} / filled ${fmt(item.filled_quantity, 4)}`),
        "当前没有最近订单。",
      );
    }
    if (document.getElementById("filled-orders-list")) {
      setList(
        "filled-orders-list",
        recentOrders
          .filter((item) => item.status === "filled")
          .slice(0, 6)
          .map((item) => `${item.broker_order_id} / filled ${fmt(item.filled_quantity, 4)} / avg ${item.average_price == null ? "N/A" : money(item.average_price)}`),
        "当前没有最近成交单。",
      );
    }
    if (document.getElementById("probe-orders-list")) {
      const probe = details.broker_order_check ?? {};
      const probeItems = [];
      if (probe.symbol || probe.broker_order_id || probe.submission_status || probe.cancellation_status) {
        probeItems.push(
          `${fmt(probe.symbol)} / ${fmt(probe.submission_status)} / ${fmt(probe.cancellation_status)} / order ${fmt(probe.broker_order_id)}`,
        );
      }
      setList("probe-orders-list", probeItems, "当前没有最近验证单。");
    }
  }

  function renderAlphaRadar(state) {
    const table = document.getElementById("alpha-radar-table");
    if (!table || !state.alphaRadar) {
      return;
    }

    if (!state.alphaRadar.length) {
      table.innerHTML = '<tr><td colspan="6" class="table-empty">目前没有发现大单异动。</td></tr>';
      return;
    }

    table.innerHTML = state.alphaRadar.map((row) => `
        <tr>
          <td class="meta-text">${new Date(row.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}</td>
          <td class="tabular-nums"><strong>${escapeHtml(row.symbol)}</strong></td>
          <td><span class="badge ${row.type === "BLOCK" ? "status-ok" : "status-warning"}">${escapeHtml(row.type)}</span></td>
          <td><span class="badge ${row.sentiment === "BULLISH" ? "status-ok" : "status-blocked"}">${escapeHtml(row.sentiment)}</span></td>
          <td class="tabular-nums">${escapeHtml(money(row.premium))}</td>
          <td><span class="meta-text">${escapeHtml(row.status)}</span></td>
        </tr>
      `).join("");
  }

  function renderMacroCalendar(state) {
    const table = document.getElementById("macro-calendar-table");
    if (!table || !state.macroCalendar) {
      return;
    }

    if (!state.macroCalendar.length) {
      table.innerHTML = '<tr><td colspan="5" class="table-empty">未来 7 天暂无高影响力事件。</td></tr>';
      return;
    }

    table.innerHTML = state.macroCalendar.map((row) => {
      const dateStr = new Date(row.time).toLocaleDateString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
      const impactTone = row.impact === "High" ? "status-blocked" : "status-warning";
      return `
          <tr>
            <td class="meta-text">${escapeHtml(dateStr)}</td>
            <td>${escapeHtml(row.country)}</td>
            <td><strong>${escapeHtml(row.event)}</strong></td>
            <td><span class="badge ${impactTone}">● ${escapeHtml(row.impact)}</span></td>
            <td class="meta-text">${escapeHtml(row.previous || "-")} / ${escapeHtml(row.forecast || "-")}</td>
          </tr>
        `;
    }).join("");
  }

  global.DashboardOperations = {
    summaryNote,
    formatGateReason,
    gateReasonText,
    renderExecutionBlockers,
    renderPriorityActions,
    renderSummaries,
    renderAlphaRadar,
    renderMacroCalendar,
  };
})(window);

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

  function renderExecutionQueue(state) {
    const rawApprovals = state.summary?.trading_plan?.pending_approvals;
    const approvals = Array.isArray(rawApprovals) ? rawApprovals : [];
    const recentOrders = state.summary?.details?.recent_orders ?? [];

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
    renderExecutionQueue,
    renderAlphaRadar,
    renderMacroCalendar,
  };
})(window);

(function attachDashboardAccounts(global) {
  function accountData(state) {
    return state.summary?.accounts?.[state.activeAccount] ?? null;
  }

  function renderTabs(state) {
    document.querySelectorAll("#account-tabs .tab").forEach((node) => {
      node.classList.toggle("is-active", node.dataset.account === state.activeAccount);
    });
    const detailLink = document.getElementById("account-detail-link");
    if (detailLink) {
      detailLink.href = `/dashboard/accounts/${encodeURIComponent(state.activeAccount)}`;
    }
  }

  function renderOverview(state) {
    const overviewCards = document.getElementById("overview-cards");
    if (!overviewCards) {
      return;
    }

    const details = state.summary?.details ?? {};
    const gate = details.execution_gate ?? {};
    const live = details.live_acceptance ?? {};
    const account = accountData(state) ?? {};
    const tone = gate.should_block ? "blocked" : gate.ready ? "ok" : "warning";
    const cards = [
      metricTile("当前账户 NAV", money(account.nav || 0), `${account.label ?? ""} / 现金 ${money(account.cash || 0)}`, "ok"),
      metricTile("持仓市值", money(account.position_value || 0), `持仓数 ${fmt(account.positions?.length || 0)}`, "ok"),
      metricTile("现金占比", fmtPct(account.cash_weight || account.cash_ratio || 0), `现金 ${money(account.cash || 0)}`, "warning"),
      metricTile("总收益", `${fmtPct(account.total_return ?? 0)} ${trendIcon(account.total_return ?? 0)}`, `回撤 ${fmtPct(account.drawdown ?? 0)}`, (account.total_return ?? 0) >= 0 ? "ok" : "blocked"),
      metricTile("日 / 周盈亏", `${money(account.daily_pnl ?? 0)} ${trendIcon(account.daily_pnl ?? 0)} / ${money(account.weekly_pnl ?? 0)}`, "盈亏", (account.daily_pnl ?? 0) >= 0 ? "ok" : "blocked"),
      metricTile("运行状态", live.ready_for_live ? "实盘就绪" : (gate.should_block ? "已阻塞" : "预警"), `门禁 ${displayValue(gate.policy_stage)} / 实盘 ${live.ready_for_live ? "就绪" : "等待"}`, tone),
    ];
    overviewCards.innerHTML = cards.join("");

    const toplineUpdated = document.getElementById("topline-updated");
    if (toplineUpdated) {
      const now = new Date();
      toplineUpdated.innerHTML = `更新于 ${now.toLocaleString()} ${freshnessIndicator(now)}`;
    }

    const curveTitle = document.getElementById("curve-title");
    if (curveTitle) {
      curveTitle.textContent = `${account.label ?? "总账户"}净值曲线`;
    }

    const navCurve = document.getElementById("nav-curve");
    if (navCurve) {
      renderCurve("nav-curve", account.nav_curve ?? [], {
        smooth: true,
        interactive: true,
        overlays: state.macroCalendar || [],
      });
    }
  }

  function renderAssets(state) {
    const tbody = document.getElementById("assets-table");
    if (!tbody) {
      return;
    }

    const account = accountData(state) ?? {};
    const rows = account.positions ?? [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="table-empty">当前账户没有持仓。</td></tr>';
    } else {
      tbody.innerHTML = rows
        .map(
          (row) => `
            <tr>
              <td data-label="资产"><strong>${escapeHtml(row.symbol)}</strong><br /><span class="meta-text">${escapeHtml(row.name ?? "")}</span></td>
          <td data-label="市场">${escapeHtml(labelMarket(row.market))}</td>
          <td data-label="类别">${escapeHtml(labelAssetClass(row.asset_class))}</td>
              <td data-label="数量">${escapeHtml(fmt(row.quantity, 4))}</td>
              <td data-label="均价">${escapeHtml(money(row.average_cost))}</td>
              <td data-label="市值">${escapeHtml(money(row.market_value))}</td>
              <td data-label="配置">${escapeHtml(fmtPct(row.weight))}</td>
              <td data-label="浮盈亏" class="${row.unrealized_pnl >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(money(row.unrealized_pnl))} ${trendIcon(row.unrealized_pnl)}</td>
              <td data-label="收益" class="${(row.unrealized_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(row.unrealized_return))}</td>
            </tr>
          `,
        )
        .join("");
    }

    const allocationBars = document.getElementById("allocation-bars");
    if (allocationBars) {
      const allocation = account.allocation_mix ?? {};
      allocationBars.innerHTML = `
        <div class="stack-row">
          <label>现金 / 股票 / 期权</label>
          <div class="stack-track">
            <span class="stack-segment cash" style="width:${(allocation.cash ?? 0) * 100}%"></span>
            <span class="stack-segment equity" style="width:${(allocation.equity ?? 0) * 100}%"></span>
            <span class="stack-segment option" style="width:${(allocation.option ?? 0) * 100}%"></span>
          </div>
        </div>
      `;
    }

    if (document.getElementById("account-bullets")) {
      setList(
        "account-bullets",
        [
          `账户: ${displayValue(account.label)}`,
          `NAV: ${money(account.nav)}`,
          `现金: ${money(account.cash)}`,
          `持仓市值: ${money(account.position_value)}`,
          `现金占比: ${fmtPct(account.cash_weight)}`,
        ],
        "暂无账户说明。",
      );
    }

    const compareTable = document.getElementById("account-compare-table");
    if (compareTable) {
      const allAccounts = state.summary?.accounts ?? {};
      const gate = state.summary?.details?.execution_gate ?? {};
      const live = state.summary?.details?.live_acceptance ?? {};
      const compareRows = ["total", "CN", "HK", "US"]
        .map((key) => {
          const item = allAccounts[key];
          if (!item) return null;
          const status = key === "total"
            ? (live.ready_for_live ? "live_ready" : gate.should_block ? "blocked" : "warning")
            : ((item.plan_items?.length ?? 0) > 0 ? "planned" : "idle");
          return { key, item, status };
        })
        .filter(Boolean);
      compareTable.innerHTML = compareRows.length
        ? compareRows.map(({ key, item, status }) => `
            <tr>
              <td><strong><a href="/dashboard/accounts/${encodeURIComponent(key)}">${escapeHtml(item.label)}</a></strong></td>
              <td>${escapeHtml(money(item.nav))}</td>
              <td>${escapeHtml(fmtPct(item.cash_weight))}</td>
              <td class="${(item.total_return ?? 0) >= 0 ? "status-ok" : "status-blocked"}">${escapeHtml(fmtPct(item.total_return))}</td>
              <td>${escapeHtml(fmt((item.plan_items || []).length))}</td>
              <td>${escapeHtml(fmt(item.position_count))}</td>
              <td><span class="badge status-${badgeTone(status === "blocked" ? "blocked" : status === "live_ready" ? "ok" : status === "planned" ? "warning" : "empty")}">${escapeHtml(labelStatus(status))}</span></td>
            </tr>
          `).join("")
        : '<tr><td colspan="7" class="table-empty">当前没有账户对照数据。</td></tr>';
    }

    const cashUsageMetrics = document.getElementById("cash-usage-metrics");
    const cashUsageTable = document.getElementById("cash-usage-table");
    if (cashUsageMetrics || cashUsageTable) {
      const allAccounts = state.summary?.accounts ?? {};
      const planItems = state.summary?.trading_plan?.items ?? [];
      const notionalByAccount = new Map([
        ["CN", 0],
        ["HK", 0],
        ["US", 0],
      ]);
      const planCountByAccount = new Map([
        ["CN", 0],
        ["HK", 0],
        ["US", 0],
      ]);
      planItems.forEach((item) => {
        const market = item.market || "unknown";
        const notional = Number(item.reference_price || 0) * Number(item.quantity || 0);
        notionalByAccount.set(market, (notionalByAccount.get(market) || 0) + notional);
        planCountByAccount.set(market, (planCountByAccount.get(market) || 0) + 1);
      });
      const usageRows = ["total", "CN", "HK", "US"]
        .map((key) => {
          const item = allAccounts[key];
          if (!item) return null;
          const planNotional = key === "total"
            ? [...notionalByAccount.values()].reduce((sum, value) => sum + value, 0)
            : Number(notionalByAccount.get(key) || 0);
          const planCount = key === "total"
            ? planItems.length
            : Number(planCountByAccount.get(key) || 0);
          const cashUsage = Number(item.cash || 0) > 0 ? planNotional / Number(item.cash) : null;
          return {
            key,
            label: item.label,
            cash: Number(item.cash || 0),
            planNotional,
            planCount,
            cashUsage,
          };
        })
        .filter(Boolean);

      if (cashUsageMetrics) {
        cashUsageMetrics.innerHTML = [
          metricTile("总计划金额", money(usageRows.find((row) => row.key === "total")?.planNotional ?? 0), "今日预估名义金额", usageRows.length ? "ok" : "warning"),
          metricTile("最高使用率", fmtPct(Math.max(...usageRows.map((row) => Number(row.cashUsage || 0)), 0)), "单账户最高现金占用", usageRows.length ? "warning" : "empty"),
          metricTile("触达账户", fmt(usageRows.filter((row) => row.planCount > 0 && row.key !== "total").length), "今日有计划的账户", usageRows.length ? "ok" : "warning"),
          metricTile("总计划单", fmt(planItems.length), "计划意图数", planItems.length ? "ok" : "warning"),
        ].join("");
      }

      if (cashUsageTable) {
        cashUsageTable.innerHTML = usageRows.length
          ? usageRows.map((row) => `
              <tr>
                <td><strong>${escapeHtml(row.label)}</strong></td>
                <td>${escapeHtml(money(row.cash))}</td>
                <td>${escapeHtml(money(row.planNotional))}</td>
                <td>${escapeHtml(row.cashUsage != null ? fmtPct(row.cashUsage) : "暂无")}</td>
                <td>${escapeHtml(fmt(row.planCount))}</td>
              </tr>
            `).join("")
          : '<tr><td colspan="5" class="table-empty">当前没有现金使用数据。</td></tr>';
      }
    }
  }

  global.DashboardAccounts = {
    accountData,
    renderTabs,
    renderOverview,
    renderAssets,
  };
})(window);

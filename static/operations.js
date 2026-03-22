async function loadPayloads() {
  const [summaryResp, planResp, summaryListResp, liveResp, rolloutResp, qualityResp, incidentsResp] = await Promise.all([
    fetch("/dashboard/summary", { headers: { Accept: "application/json" } }),
    fetch("/journal/plans", { headers: { Accept: "application/json" } }),
    fetch("/journal/summaries", { headers: { Accept: "application/json" } }),
    fetch("/ops/live-acceptance", { headers: { Accept: "application/json" } }),
    fetch("/ops/rollout", { headers: { Accept: "application/json" } }),
    fetch("/ops/execution-metrics", { headers: { Accept: "application/json" } }),
    fetch("/ops/incidents/replay?window_days=7", { headers: { Accept: "application/json" } }),
  ]);
  if (!summaryResp.ok || !planResp.ok || !summaryListResp.ok || !liveResp.ok || !rolloutResp.ok || !qualityResp.ok || !incidentsResp.ok) {
    throw new Error("operations endpoints unavailable");
  }
  return {
    dashboard: await summaryResp.json(),
    plans: await planResp.json(),
    summaries: await summaryListResp.json(),
    liveAcceptance: await liveResp.json(),
    rollout: await rolloutResp.json(),
    executionQuality: await qualityResp.json(),
    incidents: await incidentsResp.json(),
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
    metricTile("Rollout", fmt(rollout.current_recommendation), `Next ${fmt(rollout.next_stage)}`, rollout.ready_for_rollout ? "ok" : "warning"),
    metricTile("异常率", fmtPct(quality.exception_rate), `Risk hit ${fmtPct(quality.risk_hit_rate)}`, Number(quality.exception_rate || 0) <= 0.05 ? "ok" : "blocked"),
    metricTile("授权状态", fmt(quality.authorization_ok), `Filled ${fmt(quality.filled_samples)}`, quality.authorization_ok ? "ok" : "blocked"),
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

document.getElementById("refresh-operations")?.addEventListener("click", refreshOperations);

refreshOperations();

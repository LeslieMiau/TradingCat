/* =========================================================================
   TradingCat — Autonomous Cycle Dashboard Panel
   ========================================================================= */

const DashboardAutonomous = (() => {
  /* Phase labels with colors */
  const PHASE_META = {
    sleep:       { label: "休眠",    css: "phase-sleep" },
    pre_market:  { label: "盘前",    css: "phase-pre-market" },
    opening:     { label: "开盘",    css: "phase-opening" },
    intraday:    { label: "盘中",    css: "phase-intraday" },
    closing:     { label: "收盘",    css: "phase-closing" },
    post_market: { label: "盘后",    css: "phase-post-market" },
  };

  function phaseBadge(phase) {
    const meta = PHASE_META[phase] || { label: phase, css: "" };
    return `<span class="badge ${meta.css}">${meta.label}</span>`;
  }

  function statusBadge(status) {
    const cls = status === "success" ? "badge-ok" : status === "error" ? "badge-fail" : "badge-warn";
    const label = status === "success" ? "成功" : status === "error" ? "失败" : status;
    return `<span class="badge ${cls}">${label}</span>`;
  }

  function renderPhases(phases) {
    const container = document.getElementById("cycle-phases");
    if (!container) return;
    const html = ["CN", "HK", "US"].map(m => {
      const p = phases[m];
      if (!p) return "";
      return `<div class="phase-chip">
        <span class="phase-market">${m}</span>
        ${phaseBadge(p.phase)}
        <span class="phase-date meta-text">${p.local_date}${p.is_trading_day ? "" : " (休市)"}</span>
      </div>`;
    }).join("");
    container.innerHTML = html || `<span class="meta-text">暂无数据</span>`;
  }

  function detailLink(jid, detail) {
    if (jid.startsWith("pre_market_briefing")) return '<a href="/dashboard/briefing" class="button button-xs">详情</a>';
    if (jid.startsWith("post_market_reflection")) return '<a href="/dashboard/review" class="button button-xs">详情</a>';
    if (jid === "intraday_insight_scan") return '<a href="/dashboard/insights" class="button button-xs">详情</a>';
    return "";
  }

  function renderJobs(jobs, runs) {
    const tbody = document.getElementById("cycle-jobs-body");
    if (!tbody) return;

    const ordered = [
      "pre_market_briefing", "pre_market_briefing_us", "pre_market_briefing_hk",
      "intraday_insight_scan",
      "post_market_reflection", "post_market_reflection_us", "post_market_reflection_hk",
    ];

    const rows = ordered.map(jid => {
      const job = jobs[jid];
      if (!job) return "";
      const run = runs[jid];
      const nextRun = job.next_run_at ? fmtTime(job.next_run_at) : "—";
      const lastRun = run ? fmtTime(run.executed_at) : "—";
      const lastStatus = run ? statusBadge(run.status) : "—";
      const detail = run?.detail ? escapeHtml(run.detail).slice(0, 60) : "—";
      const interval = job.interval_seconds ? `${(job.interval_seconds / 60).toFixed(0)} 分钟` : "—";
      const dLink = detailLink(jid, run?.detail);
      return `<tr>
        <td>${escapeHtml(job.name)}</td>
        <td>${job.enabled ? '<span class="badge badge-ok">启用</span>' : '<span class="badge badge-fail">停用</span>'}</td>
        <td>${nextRun}</td>
        <td>${interval}</td>
        <td>${lastRun}</td>
        <td>${lastStatus}</td>
        <td title="${escapeHtml(run?.detail || "")}">${detail}</td>
        <td>${dLink}</td>
      </tr>`;
    }).join("");

    tbody.innerHTML = rows || `<tr><td colspan="8" class="table-empty">暂无数据</td></tr>`;
  }

  function renderAutonomous(state) {
    if (!state.cycleStatus) return;
    renderPhases(state.cycleStatus.phases);
    renderJobs(state.cycleStatus.jobs, state.cycleStatus.recent_runs);
  }

  /* ── Public API ── */
  return { renderAutonomous };
})();

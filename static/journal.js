const journalState = {
  account: "total",
  latestPlan: null,
  latestSummary: null,
  plans: [],
  summaries: [],
  selectedPlanIndex: 0,
  selectedSummaryIndex: 0,
  error: null,
};

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll("\"", "&quot;")
    .replaceAll("'", "&#39;");
}

function fmt(value, digits = 2) {
  if (value == null) return "N/A";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function fmtPct(value) {
  if (value == null) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function labelSide(value) {
  if (value === "buy") return "买入";
  if (value === "sell") return "卖出";
  return value == null ? "N/A" : String(value);
}

function labelPlanStatus(value) {
  if (value === "planned") return "有计划";
  if (value === "no_trade") return "无交易";
  if (value === "blocked") return "已阻塞";
  return value == null ? "N/A" : String(value);
}

function labelAccount(value) {
  if (value === "total") return "总账户";
  if (value === "CN") return "A股";
  if (value === "HK") return "港股";
  if (value === "US") return "美股";
  return value == null ? "N/A" : String(value);
}

function setList(id, items, emptyText) {
  const node = document.getElementById(id);
  if (!node) return;
  if (!items || !items.length) {
    node.innerHTML = `<li class="detail-empty">${escapeHtml(emptyText)}</li>`;
    return;
  }
  node.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function badgeTone(kind) {
  if (kind === "planned" || kind === "ok" || kind === true) return "ok";
  if (kind === "blocked" || kind === false) return "blocked";
  if (kind === "no_trade" || kind === "warning") return "warning";
  return "empty";
}

function metricTile(label, value, subvalue, tone = "empty") {
  return `
    <article class="metric-tile">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value status-${tone}">${escapeHtml(value)}</span>
      <div class="metric-subvalue">${escapeHtml(subvalue ?? "")}</div>
    </article>
  `;
}

async function fetchJson(url) {
  const response = await fetch(url, { headers: { Accept: "application/json" } });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error(`${url} -> ${response.status}`);
  return response.json();
}

async function loadJournal() {
  const account = encodeURIComponent(journalState.account);
  try {
    const [latestPlan, latestSummary, plans, summaries] = await Promise.all([
      fetchJson(`/journal/plans/latest?account=${account}`),
      fetchJson(`/journal/summaries/latest?account=${account}`),
      fetchJson(`/journal/plans?account=${account}`),
      fetchJson(`/journal/summaries?account=${account}`),
    ]);
    journalState.latestPlan = latestPlan;
    journalState.latestSummary = latestSummary;
    journalState.plans = plans ?? [];
    journalState.summaries = summaries ?? [];
    journalState.selectedPlanIndex = 0;
    journalState.selectedSummaryIndex = 0;
    journalState.error = null;
  } catch (error) {
    journalState.error = error.message;
    journalState.latestPlan = null;
    journalState.latestSummary = null;
    journalState.plans = [];
    journalState.summaries = [];
  }
}

function renderTabs() {
  document.querySelectorAll("#journal-account-tabs .tab").forEach((node) => {
    node.classList.toggle("is-active", node.dataset.account === journalState.account);
  });
}

function renderJournal() {
  renderTabs();
  document.getElementById("journal-updated").textContent = `Updated ${new Date().toLocaleString()}`;
  if (journalState.error) {
    const message = journalState.error;
    document.getElementById("journal-metrics").innerHTML = metricTile("日报状态", "Unavailable", message, "blocked");
    document.getElementById("journal-latest-plan-headline").textContent = message;
    document.getElementById("journal-latest-summary-headline").textContent = message;
    setList("journal-latest-plan-body", [], message);
    setList("journal-latest-summary-body", [], message);
    document.getElementById("journal-timeline-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-plans-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-summaries-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-plan-preview-headline").textContent = message;
    document.getElementById("journal-summary-preview-headline").textContent = message;
    setList("journal-plan-preview-body", [], message);
    setList("journal-summary-preview-body", [], message);
    return;
  }

  const latestPlan = journalState.latestPlan;
  const latestSummary = journalState.latestSummary;
  const summaryByDate = new Map(journalState.summaries.map((item) => [String(item.as_of), item]));
  document.getElementById("journal-metrics").innerHTML = [
    metricTile("计划状态", labelPlanStatus(latestPlan?.status), latestPlan?.headline ?? "暂无计划", badgeTone(latestPlan?.status)),
    metricTile("信号 / 计划", `${fmt(latestPlan?.counts?.signal_count ?? 0)} / ${fmt(latestPlan?.counts?.intent_count ?? 0)}`, `手工 ${fmt(latestPlan?.counts?.manual_count ?? 0)}`, (latestPlan?.counts?.intent_count ?? 0) > 0 ? "ok" : "warning"),
    metricTile("总结亮点", fmt((latestSummary?.highlights ?? []).length), `阻塞 ${fmt((latestSummary?.blockers ?? []).length)}`, (latestSummary?.blockers ?? []).length ? "warning" : "ok"),
    metricTile("明日动作", fmt((latestSummary?.next_actions ?? []).length), `账户 ${labelAccount(journalState.account)}`, (latestSummary?.next_actions ?? []).length ? "warning" : "ok"),
  ].join("");

  document.getElementById("journal-latest-plan-headline").textContent = latestPlan?.headline ?? "今天还没有计划归档。";
  const latestPlanBody = [];
  (latestPlan?.reasons ?? []).forEach((item) => latestPlanBody.push(`原因：${item}`));
  (latestPlan?.items ?? []).slice(0, 6).forEach((item) => {
    latestPlanBody.push(`${item.symbol} / ${labelSide(item.side)} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.reason ?? "暂无原因说明"}`);
  });
  if (!latestPlanBody.length && latestPlan?.status === "no_trade") {
    latestPlanBody.push("今天没有交易计划。");
  }
  setList("journal-latest-plan-body", latestPlanBody, "今天还没有计划正文。");

  document.getElementById("journal-latest-summary-headline").textContent = latestSummary?.headline ?? "今天还没有总结归档。";
  const latestSummaryBody = [];
  (latestSummary?.highlights ?? []).forEach((item) => latestSummaryBody.push(`亮点：${item}`));
  (latestSummary?.blockers ?? []).forEach((item) => latestSummaryBody.push(`阻塞：${item}`));
  (latestSummary?.next_actions ?? []).forEach((item) => latestSummaryBody.push(`下一步：${item}`));
  setList("journal-latest-summary-body", latestSummaryBody, "今天还没有总结正文。");
  const timelineRows = journalState.plans.slice(0, 7).map((planItem) => {
    const summaryItem = summaryByDate.get(String(planItem.as_of));
    return {
      as_of: planItem.as_of,
      status: planItem.status,
      intentCount: planItem.counts?.intent_count ?? 0,
      blockerCount: (summaryItem?.blockers ?? []).length,
      nextAction: (summaryItem?.next_actions ?? [])[0] ?? "N/A",
    };
  });
  document.getElementById("journal-timeline-table").innerHTML = timelineRows.length
    ? timelineRows.map((item) => `
        <tr>
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td><span class="badge status-${badgeTone(item.status)}">${escapeHtml(labelPlanStatus(item.status))}</span></td>
          <td>${escapeHtml(fmt(item.intentCount))}</td>
          <td>${escapeHtml(fmt(item.blockerCount))}</td>
          <td>${escapeHtml(item.nextAction)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有近 7 日日报时间线。</td></tr>';

  document.getElementById("journal-plans-table").innerHTML = journalState.plans.length
    ? journalState.plans.slice(0, 14).map((item, index) => `
        <tr data-plan-index="${index}" class="${index === journalState.selectedPlanIndex ? "is-selected" : ""}">
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td><span class="badge status-${badgeTone(item.status)}">${escapeHtml(labelPlanStatus(item.status))}</span></td>
          <td>${escapeHtml(item.headline ?? "")}</td>
          <td>${escapeHtml(`${fmt(item.counts?.signal_count ?? 0)} / ${fmt(item.counts?.intent_count ?? 0)}`)}</td>
          <td>${escapeHtml((item.reasons ?? [])[0] ?? ((item.items ?? [])[0]?.reason ?? "暂无正文预览"))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有计划归档记录。</td></tr>';
  const selectedPlan = journalState.plans[journalState.selectedPlanIndex] ?? latestPlan;
  document.getElementById("journal-plan-preview-headline").textContent = selectedPlan?.headline ?? "暂无计划详情。";
  const selectedPlanBody = [];
  (selectedPlan?.reasons ?? []).forEach((item) => selectedPlanBody.push(`原因：${item}`));
  (selectedPlan?.items ?? []).forEach((item) => {
    const side = item.side === "buy" ? "买入" : item.side === "sell" ? "卖出" : "未知";
    selectedPlanBody.push(`${item.symbol} / ${labelSide(item.side)} / 数量 ${fmt(item.quantity ?? 0, 4)} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.reason ?? "暂无原因说明"}`);
  });
  setList("journal-plan-preview-body", selectedPlanBody, "当前没有计划详情内容。");

  document.getElementById("journal-summaries-table").innerHTML = journalState.summaries.length
    ? journalState.summaries.slice(0, 14).map((item, index) => `
        <tr data-summary-index="${index}" class="${index === journalState.selectedSummaryIndex ? "is-selected" : ""}">
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td>${escapeHtml(item.headline ?? "")}</td>
          <td>${escapeHtml((item.highlights ?? [])[0] ?? "N/A")}</td>
          <td>${escapeHtml((item.blockers ?? [])[0] ?? "N/A")}</td>
          <td>${escapeHtml((item.next_actions ?? [])[0] ?? "N/A")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有总结归档记录。</td></tr>';
  const selectedSummary = journalState.summaries[journalState.selectedSummaryIndex] ?? latestSummary;
  document.getElementById("journal-summary-preview-headline").textContent = selectedSummary?.headline ?? "暂无总结详情。";
  const selectedSummaryBody = [];
  (selectedSummary?.highlights ?? []).forEach((item) => selectedSummaryBody.push(`亮点：${item}`));
  (selectedSummary?.blockers ?? []).forEach((item) => selectedSummaryBody.push(`阻塞：${item}`));
  (selectedSummary?.next_actions ?? []).forEach((item) => selectedSummaryBody.push(`下一步：${item}`));
  setList("journal-summary-preview-body", selectedSummaryBody, "当前没有总结详情内容。");
}

async function refreshJournal() {
  await loadJournal();
  renderJournal();
}

document.getElementById("refresh-journal")?.addEventListener("click", () => {
  refreshJournal();
});

document.querySelectorAll("#journal-account-tabs .tab").forEach((node) => {
  node.addEventListener("click", () => {
    journalState.account = node.dataset.account || "total";
    refreshJournal();
  });
});

document.addEventListener("click", (event) => {
  const timelineRow = event.target.closest("tr[data-timeline-day]");
  if (timelineRow) {
    const day = timelineRow.dataset.timelineDay || "";
    const planIndex = journalState.plans.findIndex((item) => String(item.as_of) === day);
    const summaryIndex = journalState.summaries.findIndex((item) => String(item.as_of) === day);
    if (planIndex >= 0) journalState.selectedPlanIndex = planIndex;
    if (summaryIndex >= 0) journalState.selectedSummaryIndex = summaryIndex;
    renderJournal();
    return;
  }
  const planRow = event.target.closest("tr[data-plan-index]");
  if (planRow) {
    journalState.selectedPlanIndex = Number(planRow.dataset.planIndex || 0);
    renderJournal();
    return;
  }
  const summaryRow = event.target.closest("tr[data-summary-index]");
  if (summaryRow) {
    journalState.selectedSummaryIndex = Number(summaryRow.dataset.summaryIndex || 0);
    renderJournal();
  }
});

refreshJournal();
document.getElementById("journal-metrics").innerHTML = metricTile("日报状态", "Unavailable", message, "blocked");
    document.getElementById("journal-latest-plan-headline").textContent = message;
    document.getElementById("journal-latest-summary-headline").textContent = message;
    setList("journal-latest-plan-body", [], message);
    setList("journal-latest-summary-body", [], message);
    document.getElementById("journal-timeline-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-plans-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-summaries-table").innerHTML = `<tr><td colspan="5" class="table-empty">${escapeHtml(message)}</td></tr>`;
    document.getElementById("journal-plan-preview-headline").textContent = message;
    document.getElementById("journal-summary-preview-headline").textContent = message;
    setList("journal-plan-preview-body", [], message);
    setList("journal-summary-preview-body", [], message);
    return;
  }

  const latestPlan = journalState.latestPlan;
  const latestSummary = journalState.latestSummary;
  const summaryByDate = new Map(journalState.summaries.map((item) => [String(item.as_of), item]));
  document.getElementById("journal-metrics").innerHTML = [
    metricTile("计划状态", latestPlan?.status ?? "N/A", latestPlan?.headline ?? "暂无计划", badgeTone(latestPlan?.status)),
    metricTile("信号 / 计划", `${fmt(latestPlan?.counts?.signal_count ?? 0)} / ${fmt(latestPlan?.counts?.intent_count ?? 0)}`, `手工 ${fmt(latestPlan?.counts?.manual_count ?? 0)}`, (latestPlan?.counts?.intent_count ?? 0) > 0 ? "ok" : "warning"),
    metricTile("总结亮点", fmt((latestSummary?.highlights ?? []).length), `阻塞 ${fmt((latestSummary?.blockers ?? []).length)}`, (latestSummary?.blockers ?? []).length ? "warning" : "ok"),
    metricTile("明日动作", fmt((latestSummary?.next_actions ?? []).length), `account ${journalState.account}`, (latestSummary?.next_actions ?? []).length ? "warning" : "ok"),
  ].join("");

  document.getElementById("journal-latest-plan-headline").textContent = latestPlan?.headline ?? "今天还没有计划归档。";
  const latestPlanBody = [];
  (latestPlan?.reasons ?? []).forEach((item) => latestPlanBody.push(`原因：${item}`));
  (latestPlan?.items ?? []).slice(0, 6).forEach((item) => {
    latestPlanBody.push(`${item.symbol} / ${labelSide(item.side)} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.reason ?? "暂无原因说明"}`);
  });
  if (!latestPlanBody.length && latestPlan?.status === "no_trade") {
    latestPlanBody.push("今天没有交易计划。");
  }
  setList("journal-latest-plan-body", latestPlanBody, "今天还没有计划正文。");

  document.getElementById("journal-latest-summary-headline").textContent = latestSummary?.headline ?? "今天还没有总结归档。";
  const latestSummaryBody = [];
  (latestSummary?.highlights ?? []).forEach((item) => latestSummaryBody.push(`亮点：${item}`));
  (latestSummary?.blockers ?? []).forEach((item) => latestSummaryBody.push(`阻塞：${item}`));
  (latestSummary?.next_actions ?? []).forEach((item) => latestSummaryBody.push(`下一步：${item}`));
  setList("journal-latest-summary-body", latestSummaryBody, "今天还没有总结正文。");
  const timelineRows = journalState.plans.slice(0, 7).map((planItem) => {
    const summaryItem = summaryByDate.get(String(planItem.as_of));
    return {
      as_of: planItem.as_of,
      status: planItem.status,
      intentCount: planItem.counts?.intent_count ?? 0,
      blockerCount: (summaryItem?.blockers ?? []).length,
      nextAction: (summaryItem?.next_actions ?? [])[0] ?? "N/A",
    };
  });
  document.getElementById("journal-timeline-table").innerHTML = timelineRows.length
    ? timelineRows.map((item) => `
        <tr>
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td><span class="badge status-${badgeTone(item.status)}">${escapeHtml(labelPlanStatus(item.status))}</span></td>
          <td>${escapeHtml(fmt(item.intentCount))}</td>
          <td>${escapeHtml(fmt(item.blockerCount))}</td>
          <td>${escapeHtml(item.nextAction)}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有近 7 日日报时间线。</td></tr>';

  document.getElementById("journal-plans-table").innerHTML = journalState.plans.length
    ? journalState.plans.slice(0, 14).map((item, index) => `
        <tr data-plan-index="${index}" class="${index === journalState.selectedPlanIndex ? "is-selected" : ""}">
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td><span class="badge status-${badgeTone(item.status)}">${escapeHtml(labelPlanStatus(item.status))}</span></td>
          <td>${escapeHtml(item.headline ?? "")}</td>
          <td>${escapeHtml(`${fmt(item.counts?.signal_count ?? 0)} / ${fmt(item.counts?.intent_count ?? 0)}`)}</td>
          <td>${escapeHtml((item.reasons ?? [])[0] ?? ((item.items ?? [])[0]?.reason ?? "暂无正文预览"))}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有计划归档记录。</td></tr>';
  const selectedPlan = journalState.plans[journalState.selectedPlanIndex] ?? latestPlan;
  document.getElementById("journal-plan-preview-headline").textContent = selectedPlan?.headline ?? "暂无计划详情。";
  const selectedPlanBody = [];
  (selectedPlan?.reasons ?? []).forEach((item) => selectedPlanBody.push(`原因：${item}`));
  (selectedPlan?.items ?? []).forEach((item) => {
    const side = item.side === "buy" ? "买入" : item.side === "sell" ? "卖出" : "未知";
    selectedPlanBody.push(`${item.symbol} / ${labelSide(item.side)} / 数量 ${fmt(item.quantity ?? 0, 4)} / 目标权重 ${item.target_weight == null ? "N/A" : fmtPct(item.target_weight)} / ${item.reason ?? "暂无原因说明"}`);
  });
  setList("journal-plan-preview-body", selectedPlanBody, "当前没有计划详情内容。");

  document.getElementById("journal-summaries-table").innerHTML = journalState.summaries.length
    ? journalState.summaries.slice(0, 14).map((item, index) => `
        <tr data-summary-index="${index}" class="${index === journalState.selectedSummaryIndex ? "is-selected" : ""}">
          <td>${escapeHtml(String(item.as_of ?? ""))}</td>
          <td>${escapeHtml(item.headline ?? "")}</td>
          <td>${escapeHtml((item.highlights ?? [])[0] ?? "N/A")}</td>
          <td>${escapeHtml((item.blockers ?? [])[0] ?? "N/A")}</td>
          <td>${escapeHtml((item.next_actions ?? [])[0] ?? "N/A")}</td>
        </tr>
      `).join("")
    : '<tr><td colspan="5" class="table-empty">当前没有总结归档记录。</td></tr>';
  const selectedSummary = journalState.summaries[journalState.selectedSummaryIndex] ?? latestSummary;
  document.getElementById("journal-summary-preview-headline").textContent = selectedSummary?.headline ?? "暂无总结详情。";
  const selectedSummaryBody = [];
  (selectedSummary?.highlights ?? []).forEach((item) => selectedSummaryBody.push(`亮点：${item}`));
  (selectedSummary?.blockers ?? []).forEach((item) => selectedSummaryBody.push(`阻塞：${item}`));
`${item.symbol} / ${labelSide(item.side)} / 数量 ${fmt(item.quantity ?? 0, 4)} / 目标权重 ${
        item.target_weight == null ? "N/A" : fmtPct(item.target_weight)
      } / ${item.requires_approval ? "人工审批" : "自动执行"} / ${item.reason ?? "暂无原因说明"}`,
    );
  });
  dailyPreviewBody.push(`总结标题：${selectedSummary?.headline ?? "暂无总结标题"}`);
  (selectedSummary?.highlights ?? []).forEach((item) => dailyPreviewBody.push(`亮点：${item}`));
  (selectedSummary?.blockers ?? []).forEach((item) => dailyPreviewBody.push(`阻塞：${item}`));
  (selectedSummary?.next_actions ?? []).forEach((item) => dailyPreviewBody.push(`下一步：${item}`));
  setList("journal-daily-preview-body", dailyPreviewBody, "当前没有日报详情内容。");
}

function updateJournalLinks() {
  const day = currentJournalDay();
  const account = encodeURIComponent(journalState.account);
  const asOf = encodeURIComponent(day);
  const planLink = document.getElementById("journal-plan-link");
  const summaryLink = document.getElementById("journal-summary-link");
  const dailyLink = document.getElementById("journal-daily-link");
  const markdownLink = document.getElementById("journal-markdown-link");
  if (planLink) planLink.href = `/journal/plans/latest?account=${account}&as_of=${asOf}`;
  if (summaryLink) summaryLink.href = `/journal/summaries/latest?account=${account}&as_of=${asOf}`;
  if (dailyLink) dailyLink.href = `/journal/daily?account=${account}&as_of=${asOf}`;
  if (markdownLink) markdownLink.href = `/journal/markdown/latest?account=${account}&as_of=${asOf}`;
}


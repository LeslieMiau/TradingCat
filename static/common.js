/* =========================================================================
   TradingCat — shared utility functions
   ========================================================================= */

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
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

function fmtPct(value) {
  if (value == null) return "N/A";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function money(value) {
  if (value == null) return "N/A";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(value) {
  if (!value) return "N/A";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function badgeTone(kind) {
  if (kind === true || kind === "ok" || kind === "keep" || kind === "active" || kind === "planned" || kind === "deploy_candidate") return "ok";
  if (kind === false || kind === "blocked" || kind === "drop" || kind === "rejected" || kind === "reject") return "blocked";
  if (kind === "paper_only" || kind === "warning" || kind === "hold" || kind === "no_trade") return "warning";
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

function setList(id, items, emptyText) {
  const node = document.getElementById(id);
  if (!node) return;
  if (!items || !items.length) {
    node.innerHTML = `<li class="detail-empty">${escapeHtml(emptyText)}</li>`;
    return;
  }
  node.innerHTML = items.map((item) => `<li>${escapeHtml(item)}</li>`).join("");
}

function heatTone(value) {
  if (value == null) return "rgba(22, 32, 43, 0.05)";
  if (value >= 0.7) return "rgba(180, 35, 24, 0.34)";
  if (value >= 0.4) return "rgba(247, 144, 9, 0.22)";
  if (value >= 0) return "rgba(14, 138, 97, 0.12)";
  if (value <= -0.7) return "rgba(180, 35, 24, 0.34)";
  if (value <= -0.4) return "rgba(247, 144, 9, 0.22)";
  return "rgba(14, 138, 97, 0.18)";
}

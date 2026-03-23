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
  /* value may contain trusted HTML (e.g. trendIcon), so only escape if plain string */
  const safeValue = typeof value === "string" && value.includes("<span") ? value : escapeHtml(value);
  return `
    <article class="metric-tile">
      <span class="metric-label">${escapeHtml(label)}</span>
      <span class="metric-value status-${tone}">${safeValue}</span>
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

/* =========================================================================
   Toast Notification System
   ========================================================================= */
function showToast(message, type = "info", duration = 3000) {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span class="toast-msg">${escapeHtml(message)}</span><button class="toast-close" aria-label="关闭">&times;</button>`;
  toast.querySelector(".toast-close").addEventListener("click", () => dismissToast(toast));
  container.appendChild(toast);
  setTimeout(() => dismissToast(toast), duration);
}

function dismissToast(toast) {
  if (!toast || toast.classList.contains("toast-out")) return;
  toast.classList.add("toast-out");
  toast.addEventListener("animationend", () => toast.remove());
}

/* =========================================================================
   Skeleton Loading Generators
   ========================================================================= */
function skeletonTile(count = 1) {
  let html = "";
  for (let i = 0; i < count; i++) {
    html += `<article class="metric-tile"><span class="skeleton skeleton-label"></span><span class="skeleton skeleton-value"></span><span class="skeleton skeleton-sub"></span></article>`;
  }
  return html;
}

function skeletonTableRows(cols, rows = 3) {
  let html = "";
  for (let r = 0; r < rows; r++) {
    html += "<tr>";
    for (let c = 0; c < cols; c++) {
      const w = c === 0 ? "60%" : "45%";
      html += `<td><span class="skeleton" style="width:${w};height:14px;display:inline-block"></span></td>`;
    }
    html += "</tr>";
  }
  return html;
}

function skeletonList(count = 3) {
  let html = "";
  for (let i = 0; i < count; i++) {
    const w = 50 + Math.round(Math.random() * 30);
    html += `<li><span class="skeleton" style="width:${w}%;height:14px;display:inline-block"></span></li>`;
  }
  return html;
}

/* =========================================================================
   API Fetch with Retry
   ========================================================================= */
async function apiFetch(url, options = {}, retries = 2) {
  const defaults = { headers: { Accept: "application/json" } };
  const merged = { ...defaults, ...options, headers: { ...defaults.headers, ...(options.headers || {}) } };
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url, merged);
      if (response.ok) {
        const data = await response.json();
        return { ok: true, data, error: null };
      }
      if (response.status >= 500 && attempt < retries) {
        showToast(`${url} 请求失败，正在重试...`, "warning", 2000);
        await new Promise((r) => setTimeout(r, (attempt + 1) * 1500));
        continue;
      }
      return { ok: false, data: null, error: `${url} → ${response.status}` };
    } catch (err) {
      if (attempt < retries) {
        showToast("网络错误，正在重试...", "warning", 2000);
        await new Promise((r) => setTimeout(r, (attempt + 1) * 1500));
        continue;
      }
      return { ok: false, data: null, error: err.message };
    }
  }
  return { ok: false, data: null, error: `${url} 请求最终失败` };
}

/* =========================================================================
   Error State with Retry
   ========================================================================= */
function renderErrorState(containerId, message, retryFn) {
  const el = document.getElementById(containerId);
  if (!el) return;
  el.innerHTML = `
    <div class="error-state">
      <div class="error-state__icon">!</div>
      <p class="error-state__msg">${escapeHtml(message)}</p>
      ${retryFn ? '<button class="button button-primary button-sm error-state__retry">重试</button>' : ""}
    </div>
  `;
  if (retryFn) {
    el.querySelector(".error-state__retry").addEventListener("click", retryFn);
  }
}

/* =========================================================================
   Trend Indicator
   ========================================================================= */
function trendIcon(value) {
  if (value == null || value === 0) return '<span class="trend-icon trend-flat">→</span>';
  return value > 0
    ? '<span class="trend-icon trend-up">↑</span>'
    : '<span class="trend-icon trend-down">↓</span>';
}

/* =========================================================================
   Data Freshness Indicator
   ========================================================================= */
function freshnessIndicator(timestamp) {
  if (!timestamp) return "";
  const now = Date.now();
  const parsed = timestamp instanceof Date ? timestamp.getTime() : new Date(timestamp).getTime();
  if (Number.isNaN(parsed)) return "";
  const minutes = Math.max(0, (now - parsed) / 60000);
  if (minutes < 5) return '<span class="freshness-dot freshness-fresh" title="数据新鲜"></span>';
  if (minutes < 30) return '<span class="freshness-dot freshness-stale" title="数据略旧"></span>';
  return '<span class="freshness-dot freshness-expired" title="数据可能已过期"></span>';
}

/* =========================================================================
   Unified Empty State
   ========================================================================= */
function emptyState(message) {
  return `<div class="empty-state">
    <span class="empty-state__icon">—</span>
    <span class="empty-state__msg">${escapeHtml(message)}</span>
  </div>`;
}

/* =========================================================================
   Table Search
   ========================================================================= */
function enableTableSearch(inputId, tableBodyId) {
  const input = document.getElementById(inputId);
  const tbody = document.getElementById(tableBodyId);
  if (!input || !tbody) return;
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    tbody.querySelectorAll("tr").forEach((tr) => {
      if (!query) { tr.style.display = ""; return; }
      const text = tr.textContent.toLowerCase();
      tr.style.display = text.includes(query) ? "" : "none";
    });
  });
}

/* =========================================================================
   Keyboard Shortcuts
   ========================================================================= */
const _shortcuts = [];
function registerShortcut(key, description, handler) {
  _shortcuts.push({ key, description, handler });
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;
    if (e.key === "?" && !e.ctrlKey && !e.metaKey) { e.preventDefault(); toggleShortcutOverlay(); return; }
    if (e.key === "Escape") { closeShortcutOverlay(); return; }
    for (const s of _shortcuts) {
      if (e.key === s.key && !e.ctrlKey && !e.metaKey && !e.altKey) { e.preventDefault(); s.handler(); return; }
    }
  });
}

function toggleShortcutOverlay() {
  let overlay = document.getElementById("shortcut-overlay");
  if (overlay) { overlay.remove(); return; }
  overlay = document.createElement("div");
  overlay.id = "shortcut-overlay";
  overlay.className = "shortcut-overlay";
  overlay.innerHTML = `
    <div class="shortcut-overlay__card">
      <h3>键盘快捷键</h3>
      <div class="shortcut-overlay__list">
        ${_shortcuts.map((s) => `<div class="shortcut-row"><kbd>${escapeHtml(s.key)}</kbd><span>${escapeHtml(s.description)}</span></div>`).join("")}
        <div class="shortcut-row"><kbd>?</kbd><span>显示 / 隐藏快捷键</span></div>
        <div class="shortcut-row"><kbd>Esc</kbd><span>关闭面板</span></div>
      </div>
    </div>
  `;
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

function closeShortcutOverlay() {
  document.getElementById("shortcut-overlay")?.remove();
}

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
  if (value == null) return "暂无";
  if (typeof value === "number") {
    return Number.isInteger(value)
      ? value.toLocaleString()
      : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
  }
  if (typeof value === "boolean") return value ? "是" : "否";
  return String(value);
}

function fmtPct(value) {
  if (value == null) return "暂无";
  return `${(Number(value) * 100).toFixed(2)}%`;
}

function money(value) {
  if (value == null) return "暂无";
  return Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(value) {
  if (!value) return "暂无";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value);
  return parsed.toLocaleString();
}

function displayValue(value, fallback = "暂无") {
  if (value == null || value === "" || value === "N/A") return fallback;
  return String(value);
}

function labelSide(value) {
  const labels = {
    buy: "买入",
    sell: "卖出",
    BUY: "买入",
    SELL: "卖出",
  };
  return labels[value] || displayValue(value);
}

function labelMarket(value) {
  const labels = {
    total: "总账户",
    CN: "A股",
    HK: "港股",
    US: "美股",
    unknown: "未知市场",
  };
  return labels[value] || displayValue(value);
}

function labelAssetClass(value) {
  const labels = {
    stock: "股票",
    etf: "ETF",
    option: "期权",
    cash: "现金",
  };
  return labels[value] || displayValue(value);
}

function labelStatus(value) {
  const labels = {
    ok: "正常",
    ready: "就绪",
    warning: "预警",
    blocked: "已阻塞",
    planned: "有计划",
    no_trade: "无交易",
    active: "活跃",
    idle: "空闲",
    live_ready: "实盘就绪",
    pending: "待处理",
    submitted: "已提交",
    working: "处理中",
    filled: "已成交",
    cancelled: "已撤销",
    rejected: "已拒绝",
    expired: "已过期",
    approved: "已批准",
    aligned: "已对齐",
    not_submitted: "未提交",
    missing: "缺失",
    manual: "人工",
    auto: "自动",
    gate: "门禁",
    approval: "审批",
    working_order: "处理中订单",
    rejected_order: "拒单",
    external_fill: "外部成交",
    deploy_candidate: "可部署候选",
    paper_only: "纸面跟踪",
    reject: "淘汰",
    keep: "保留",
    drop: "淘汰",
    overweight: "超配",
    underweight: "低配",
    High: "高",
    Medium: "中",
    Low: "低",
    BULLISH: "偏多",
    BEARISH: "偏空",
    BLOCK: "大单",
    SWEEP: "扫单",
    READY: "就绪",
    WAIT: "等待",
    AUTHORIZED: "已授权",
    UNAUTHORIZED: "未授权",
    TRIGGERED: "已触发",
    PENDING: "等待触发",
    bullish: "偏多",
    build_risk: "可加风险",
    supportive: "支撑",
    high: "高",
    complete: "完整",
    participate: "参与",
    constructive: "偏积极",
    greed: "贪婪",
    neutral: "中性",
    caution: "谨慎",
    hold_pace: "控制节奏",
    mixed: "分化",
    medium: "中",
    degraded: "降级",
    hedged: "对冲",
    selective: "择机",
    wait: "等待",
    risk_off: "风险收缩",
    pause_new_adds: "暂停加仓",
    reduce_risk: "降风险",
    low: "低",
    fallback: "回退",
    defensive: "防御",
    avoid: "回避",
    fear: "恐慌",
    unknown: "未知",
    missing: "缺失",
    error: "错误",
  };
  return labels[value] || displayValue(value);
}

function labelVerdict(value) {
  return labelStatus(value);
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
    <article class="metric-tile metric-tile--${tone}">
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
  if (value == null) return "rgba(13, 16, 22, 0.3)";
  if (value >= 0.7) return "rgba(208, 64, 64, 0.35)";
  if (value >= 0.4) return "rgba(200, 162, 78, 0.22)";
  if (value >= 0) return "rgba(45, 157, 94, 0.14)";
  if (value <= -0.7) return "rgba(208, 64, 64, 0.35)";
  if (value <= -0.4) return "rgba(200, 162, 78, 0.22)";
  return "rgba(45, 157, 94, 0.18)";
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
/* =========================================================================
   Keyboard Shortcuts
   ========================================================================= */
const _shortcuts = [];

// Example keys: "Ctrl+B", "Shift+X", "Escape", "?"
function registerShortcut(keyCombo, description, handler) {
  const parts = keyCombo.toLowerCase().split("+");
  const key = parts.pop();
  const ctrl = parts.includes("ctrl");
  const shift = parts.includes("shift");
  const meta = parts.includes("meta") || parts.includes("cmd");
  const alt = parts.includes("alt");
  
  _shortcuts.push({ combo: keyCombo, key, ctrl, shift, meta, alt, description, handler });
}

function initKeyboardShortcuts() {
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA" || e.target.isContentEditable) return;
    
    // Help overlay overlay
    if (e.key === "?" && !e.ctrlKey && !e.metaKey && !e.altKey) { 
      e.preventDefault(); 
      toggleShortcutOverlay(); 
      return; 
    }
    
    if (e.key === "Escape") { 
      closeShortcutOverlay();
      // Allow escape to close modals or overlays
    }
    
    const passedKey = e.key.toLowerCase();
    for (const s of _shortcuts) {
      if (
        passedKey === s.key &&
        !!e.ctrlKey === s.ctrl &&
        !!e.shiftKey === s.shift &&
        !!e.metaKey === s.meta &&
        !!e.altKey === s.alt
      ) {
        e.preventDefault();
        s.handler();
        return;
      }
    }
  });
}

function toggleShortcutOverlay() {
  let overlay = document.getElementById("shortcut-overlay");
  if (overlay) { overlay.remove(); return; }
  overlay = document.createElement("div");
  overlay.id = "shortcut-overlay";
  overlay.className = "shortcut-overlay";
  
  let rows = _shortcuts.map(s => {
    // Format keys for display
    const keys = s.combo.split("+").map(k => `<kbd>${escapeHtml(k)}</kbd>`).join(" + ");
    return `<div class="shortcut-row"><div class="shortcut-keys">${keys}</div><span>${escapeHtml(s.description)}</span></div>`;
  }).join("");
  
  overlay.innerHTML = `
    <div class="shortcut-overlay__card">
      <h3>键盘快捷键 (Global Hotkeys)</h3>
      <div class="shortcut-overlay__list">
        ${rows}
        <div class="shortcut-row"><div class="shortcut-keys"><kbd>?</kbd></div><span>显示 / 隐藏快捷键</span></div>
        <div class="shortcut-row"><div class="shortcut-keys"><kbd>Esc</kbd></div><span>关闭面板</span></div>
      </div>
    </div>
  `;
  overlay.addEventListener("click", (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

function closeShortcutOverlay() {
  document.getElementById("shortcut-overlay")?.remove();
}

// Automatically init keyboard shortcut listener when script loads
document.addEventListener("DOMContentLoaded", () => {
  initKeyboardShortcuts();

  // Broker status indicator in sidebar
  if (typeof API !== "undefined" && API.brokerStatus) {
    apiFetch(API.brokerStatus).then((res) => {
      const dot = document.querySelector(".sidebar-status-dot");
      if (!dot) return;
      if (res.ok && res.data) {
        const connected = res.data.connected ?? res.data.status === "ok";
        dot.className = `sidebar-status-dot ${connected ? "ok" : "blocked"}`;
        dot.title = connected ? "Broker 已连接" : "Broker 断开";
      } else {
        dot.className = "sidebar-status-dot warning";
        dot.title = "Broker 状态未知";
      }
    });
  }
});

/* =========================================================================
   Auto-Refresh Timer
   ========================================================================= */
const _autoRefresh = { interval: null, remaining: 0, callback: null, duration: 0 };

function initAutoRefresh(callback, defaultSeconds = 60) {
  _autoRefresh.callback = callback;
  _autoRefresh.duration = defaultSeconds;

  let pill = document.getElementById("auto-refresh-pill");
  if (pill) return; // already initialized

  pill = document.createElement("div");
  pill.id = "auto-refresh-pill";
  pill.className = "auto-refresh-pill";
  pill.innerHTML = `
    <button class="ar-toggle" type="button" title="自动刷新">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
        <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
      </svg>
      <span class="ar-label">自动</span>
    </button>
    <span class="ar-countdown" hidden></span>
    <select class="ar-interval" title="刷新间隔">
      <option value="30">30s</option>
      <option value="60" selected>60s</option>
      <option value="120">2m</option>
      <option value="300">5m</option>
      <option value="0">关</option>
    </select>
  `;

  // Insert after the first hero-actions or at end of header
  const anchor = document.querySelector(".hero-actions");
  if (anchor) anchor.appendChild(pill);
  else document.querySelector("header")?.appendChild(pill);

  const toggle = pill.querySelector(".ar-toggle");
  const countdown = pill.querySelector(".ar-countdown");
  const select = pill.querySelector(".ar-interval");

  toggle.addEventListener("click", () => {
    if (_autoRefresh.interval) stopAutoRefresh();
    else startAutoRefresh(Number(select.value));
  });

  select.addEventListener("change", () => {
    stopAutoRefresh();
    const v = Number(select.value);
    if (v > 0) startAutoRefresh(v);
  });

  // Start by default
  startAutoRefresh(defaultSeconds);
}

function startAutoRefresh(seconds) {
  if (!seconds || !_autoRefresh.callback) return;
  stopAutoRefresh();
  _autoRefresh.duration = seconds;
  _autoRefresh.remaining = seconds;

  const pill = document.getElementById("auto-refresh-pill");
  const countdown = pill?.querySelector(".ar-countdown");
  const toggle = pill?.querySelector(".ar-toggle");
  if (countdown) { countdown.removeAttribute("hidden"); }
  if (toggle) toggle.classList.add("ar-active");

  _autoRefresh.interval = setInterval(() => {
    _autoRefresh.remaining--;
    if (countdown) countdown.textContent = `${_autoRefresh.remaining}s`;
    if (_autoRefresh.remaining <= 0) {
      _autoRefresh.remaining = _autoRefresh.duration;
      _autoRefresh.callback();
    }
  }, 1000);
  if (countdown) countdown.textContent = `${seconds}s`;
}

function stopAutoRefresh() {
  if (_autoRefresh.interval) {
    clearInterval(_autoRefresh.interval);
    _autoRefresh.interval = null;
  }
  const pill = document.getElementById("auto-refresh-pill");
  const countdown = pill?.querySelector(".ar-countdown");
  const toggle = pill?.querySelector(".ar-toggle");
  if (countdown) { countdown.setAttribute("hidden", ""); countdown.textContent = ""; }
  if (toggle) toggle.classList.remove("ar-active");
}

/* =========================================================================
   CSV Export for Tables
   ========================================================================= */
function exportTableCsv(tableId, filename) {
  const table = document.getElementById(tableId);
  if (!table) { showToast("找不到表格", "error"); return; }

  const rows = [];
  table.querySelectorAll("tr").forEach((tr) => {
    const cells = [];
    tr.querySelectorAll("th, td").forEach((cell) => {
      let text = cell.textContent.trim().replace(/"/g, '""');
      if (text.includes(",") || text.includes('"') || text.includes("\n")) text = `"${text}"`;
      cells.push(text);
    });
    if (cells.length) rows.push(cells.join(","));
  });

  const blob = new Blob(["\uFEFF" + rows.join("\n")], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || `${tableId}-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
  showToast("CSV 已导出", "success", 2000);
}

function addExportButton(tableWrapSelector, tableId, label) {
  const wrap = typeof tableWrapSelector === "string"
    ? document.querySelector(tableWrapSelector)
    : tableWrapSelector;
  if (!wrap || wrap.querySelector(".csv-export-btn")) return;

  const btn = document.createElement("button");
  btn.className = "button button-sm csv-export-btn";
  btn.type = "button";
  btn.textContent = label || "导出 CSV";
  btn.style.cssText = "position:absolute;right:8px;top:8px;font-size:11px;padding:3px 10px;opacity:0;transition:opacity 0.2s;";
  wrap.style.position = "relative";
  wrap.addEventListener("mouseenter", () => { btn.style.opacity = "1"; });
  wrap.addEventListener("mouseleave", () => { btn.style.opacity = "0"; });
  btn.addEventListener("click", (e) => { e.stopPropagation(); exportTableCsv(tableId); });
  wrap.appendChild(btn);
}

/* =========================================================================
   Command Palette (Ctrl+K)
   ========================================================================= */
const _commandPalette = { entries: [], visible: false };

function registerCommand(label, description, handler, group = "通用") {
  _commandPalette.entries.push({ label, description, handler, group });
}

function showCommandPalette() {
  if (_commandPalette.visible) { closeCommandPalette(); return; }
  _commandPalette.visible = true;

  const overlay = document.createElement("div");
  overlay.id = "command-palette";
  overlay.className = "command-palette-overlay";
  overlay.innerHTML = `
    <div class="command-palette">
      <div class="cp-search-wrap">
        <svg class="cp-search-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input class="cp-input" type="text" placeholder="搜索命令、页面、策略..." autofocus />
        <kbd class="cp-kbd">Esc</kbd>
      </div>
      <div class="cp-results"></div>
    </div>
  `;

  document.body.appendChild(overlay);
  overlay.addEventListener("click", (e) => { if (e.target === overlay) closeCommandPalette(); });

  const input = overlay.querySelector(".cp-input");
  const results = overlay.querySelector(".cp-results");
  let selected = 0;

  function render(query) {
    const q = (query || "").toLowerCase();
    const filtered = q
      ? _commandPalette.entries.filter((e) => e.label.toLowerCase().includes(q) || e.description.toLowerCase().includes(q) || e.group.toLowerCase().includes(q))
      : _commandPalette.entries;

    const grouped = {};
    filtered.forEach((e) => { (grouped[e.group] = grouped[e.group] || []).push(e); });
    selected = 0;

    let html = "";
    let idx = 0;
    for (const [group, items] of Object.entries(grouped)) {
      html += `<div class="cp-group">${escapeHtml(group)}</div>`;
      for (const item of items) {
        html += `<div class="cp-item${idx === selected ? " cp-selected" : ""}" data-idx="${idx}">
          <span class="cp-item-label">${escapeHtml(item.label)}</span>
          <span class="cp-item-desc">${escapeHtml(item.description)}</span>
        </div>`;
        idx++;
      }
    }
    results.innerHTML = html || '<div class="cp-empty">没有匹配的命令</div>';

    results.querySelectorAll(".cp-item").forEach((el) => {
      el.addEventListener("click", () => {
        const i = Number(el.dataset.idx);
        const flat = q ? filtered : _commandPalette.entries;
        if (flat[i]) { closeCommandPalette(); flat[i].handler(); }
      });
    });
  }

  input.addEventListener("input", () => render(input.value));

  input.addEventListener("keydown", (e) => {
    const items = results.querySelectorAll(".cp-item");
    if (e.key === "ArrowDown") { e.preventDefault(); selected = Math.min(selected + 1, items.length - 1); }
    else if (e.key === "ArrowUp") { e.preventDefault(); selected = Math.max(selected - 1, 0); }
    else if (e.key === "Enter") {
      e.preventDefault();
      const active = results.querySelector(".cp-selected");
      if (active) active.click();
      return;
    } else if (e.key === "Escape") { closeCommandPalette(); return; }
    items.forEach((el, i) => el.classList.toggle("cp-selected", i === selected));
    items[selected]?.scrollIntoView({ block: "nearest" });
  });

  render("");
  setTimeout(() => input.focus(), 10);
}

function closeCommandPalette() {
  _commandPalette.visible = false;
  document.getElementById("command-palette")?.remove();
}

/* =========================================================================
   Approval Action Helpers
   ========================================================================= */
async function approveRequest(requestId, reason) {
  const r = reason || prompt("审批通过原因 (可留空):");
  if (r === null) return; // cancelled
  const res = await apiFetch(API.approvalApprove(requestId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: r || "dashboard approved" }),
  });
  if (res.ok) showToast("已批准", "success");
  else showToast(res.error || "审批失败", "error");
  return res;
}

async function rejectRequest(requestId, reason) {
  const r = reason || prompt("拒绝原因:");
  if (!r) { showToast("需要填写拒绝原因", "warning"); return; }
  const res = await apiFetch(API.approvalReject(requestId), {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ reason: r }),
  });
  if (res.ok) showToast("已拒绝", "success");
  else showToast(res.error || "拒绝失败", "error");
  return res;
}

function approvalActions(requestId) {
  return `<span class="approval-actions" data-request-id="${escapeHtml(requestId)}">
    <button class="btn-approve" title="批准" type="button">✓</button>
    <button class="btn-reject" title="拒绝" type="button">✗</button>
  </span>`;
}

function bindApprovalActions(container, refreshFn) {
  (container || document).querySelectorAll(".approval-actions").forEach((el) => {
    const id = el.dataset.requestId;
    el.querySelector(".btn-approve")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      const res = await approveRequest(id);
      if (res?.ok && refreshFn) refreshFn();
    });
    el.querySelector(".btn-reject")?.addEventListener("click", async (e) => {
      e.stopPropagation();
      const res = await rejectRequest(id);
      if (res?.ok && refreshFn) refreshFn();
    });
  });
}

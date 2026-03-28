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

/* =========================================================================
   Global Trading Hotkeys (Institutional)
   ========================================================================= */
function initGlobalTradingHotkeys() {
  registerShortcut("Ctrl+X", "一键撤销所有挂单", async () => {
    if (!confirm("⚠️ 确定要撤销所有未完成订单吗 (Cancel All Open)?")) return;
    const res = await apiFetch("/orders/cancel-open", { method: "POST" });
    if (res.ok) {
      showToast("所有挂单已撤销", "success");
    } else {
      showToast(res.error || "撤单失败", "error");
    }
  });

  registerShortcut("Shift+X", "触发全局一键核按钮 (Kill Switch)", async () => {
    if (!confirm("🚨 警告：这会触发系统 Kill Switch 并清仓！确定执行吗？")) return;
    const res = await apiFetch("/kill-switch", { method: "POST" });
    if (res.ok) {
      showToast("Kill Switch 已激活！系统已锁定。", "error", 5000);
    } else {
      showToast(res.error || "触发失败", "error");
    }
  });

  registerShortcut("Ctrl+B", "极速手动买入 (Quick Trade)", () => {
    showQuickTradeModal();
  });
}

function showQuickTradeModal() {
  let modal = document.getElementById("quick-trade-modal");
  if (modal) modal.remove();

  modal = document.createElement("div");
  modal.id = "quick-trade-modal";
  modal.className = "shortcut-overlay";
  modal.innerHTML = `
    <div class="shortcut-overlay__card" style="min-width: 400px;">
      <h3 style="margin-bottom: 20px; color: var(--accent);">
        ⚡ 极速下单 (Quick Trade)
      </h3>
      <div id="quick-trade-error" style="display:none; padding:12px; margin-bottom:16px; background:rgba(224,36,36,0.15); border-left:3px solid var(--panic); color:#ff6b6b; font-size:13px; font-weight:500;"></div>
      <form id="quick-trade-form" style="display:flex; flex-direction:column; gap:12px;">
        <label>
          <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">标的代码 (Symbol)</span>
          <input type="text" id="qt-symbol" required placeholder="例如: SPY" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-family:var(--font-mono); text-transform:uppercase;">
        </label>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <label>
            <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">方向 (Side)</span>
            <select id="qt-side" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="buy">买入 (BUY)</option>
              <option value="sell">卖出 (SELL)</option>
            </select>
          </label>
          <label>
            <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">市场 (Market)</span>
            <select id="qt-market" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="US">行情 (US)</option>
              <option value="HK">港股 (HK)</option>
              <option value="CN">A股 (CN)</option>
            </select>
          </label>
        </div>
        <label>
          <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">数量 (Quantity)</span>
          <input type="number" id="qt-qty" required min="1" step="1" value="100" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-family:var(--font-mono);">
        </label>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <label>
            <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">执行算法 (Algo)</span>
            <select id="qt-algo" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="NONE">直接成交 (Direct)</option>
              <option value="TWAP">TWAP (时间加权)</option>
              <option value="VWAP">VWAP (成交量加权)</option>
              <option value="LADDER">LADDER (梯阶/网格)</option>
            </select>
          </label>
          <label>
            <span style="display:block; font-size:12px; color:var(--text-muted); margin-bottom:4px;">原因 (Reason / Tag)</span>
            <select id="qt-reason" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="Manual Plan">计划内执行 (Planned)</option>
              <option value="FOMO">怕错过 (FOMO)</option>
              <option value="Panic">恐慌规避 (Panic)</option>
              <option value="Rebound">抢反弹 (Rebound)</option>
            </select>
          </label>
        </div>

        <div id="qt-ladder-params" style="display:none; grid-template-columns: 1fr 1fr 1fr; gap:12px; margin-top:12px; padding:12px; background:rgba(var(--primary-rgb), 0.05); border-radius:4px; border:1px dashed var(--primary-color);">
          <label>
            <span style="display:block; font-size:11px; color:var(--primary-color); margin-bottom:4px;">档位 (Levels)</span>
            <input type="number" id="qt-ladder-levels" value="5" min="2" max="20" style="width:100%; padding:6px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:12px;">
          </label>
          <label>
            <span style="display:block; font-size:11px; color:var(--primary-color); margin-bottom:4px;">起始价 (Start)</span>
            <input type="number" id="qt-ladder-start" step="0.01" style="width:100%; padding:6px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:12px;">
          </label>
          <label>
            <span style="display:block; font-size:11px; color:var(--primary-color); margin-bottom:4px;">终止价 (End)</span>
            <input type="number" id="qt-ladder-end" step="0.01" style="width:100%; padding:6px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:12px;">
          </label>
        </div>
        <div style="display:flex; justify-content:flex-end; gap:12px; margin-top:20px;">
          <button type="button" class="button" id="qt-cancel">取消 (Esc)</button>
          <button type="submit" class="button button-primary">执行下单 (Enter)</button>
        </div>
      </form>
    </div>
  `;

  document.body.appendChild(modal);
  
  // Focus logic
  setTimeout(() => document.getElementById("qt-symbol").focus(), 10);

  // Events
  document.getElementById("qt-cancel").addEventListener("click", () => modal.remove());
  modal.addEventListener("click", (e) => { if (e.target === modal) modal.remove(); });

  const algoSelect = document.getElementById("qt-algo");
  const ladderParams = document.getElementById("qt-ladder-params");
  algoSelect.addEventListener("change", () => {
    ladderParams.style.display = algoSelect.value === "LADDER" ? "grid" : "none";
  });
  
  document.getElementById("quick-trade-form").addEventListener("submit", async (e) => {
    e.preventDefault();
    const payload = {
      symbol: document.getElementById("qt-symbol").value.toUpperCase().trim(),
      side: document.getElementById("qt-side").value,
      market: document.getElementById("qt-market").value,
      quantity: Number(document.getElementById("qt-qty").value),
      reason: document.getElementById("qt-reason").value,
      algo_strategy: document.getElementById("qt-algo").value,
      algo_levels: document.getElementById("qt-algo").value === 'LADDER' ? Number(document.getElementById("qt-ladder-levels").value) : null,
      algo_price_start: document.getElementById("qt-algo").value === 'LADDER' ? Number(document.getElementById("qt-ladder-start").value) : null,
      algo_price_end: document.getElementById("qt-algo").value === 'LADDER' ? Number(document.getElementById("qt-ladder-end").value) : null,
    };
    
    document.querySelector("#quick-trade-form button[type='submit']").innerText = "提交中...";
    document.querySelector("#quick-trade-form button[type='submit']").disabled = true;
    
    const res = await apiFetch("/orders/manual", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    
    if (res.ok) {
      showToast("订单已提交", "success");
      modal.remove();
    } else {
      // Show hard block error natively in modal
      const errBox = document.getElementById("quick-trade-error");
      errBox.style.display = "block";
      errBox.innerText = "🛑 风险拦截 (Hard Block): " + (res.data?.error || res.error || "未知拒单原因");
      
      document.querySelector("#quick-trade-form button[type='submit']").innerText = "执行下单 (Enter)";
      document.querySelector("#quick-trade-form button[type='submit']").disabled = false;
    }
  });
}

// Automatically init the hotkeys and the global keys when script loads
document.addEventListener("DOMContentLoaded", () => {
  initKeyboardShortcuts();
  initGlobalTradingHotkeys();
});

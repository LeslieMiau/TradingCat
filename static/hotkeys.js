/* =========================================================================
   TradingCat — Global Trading Hotkeys (Institutional)
   Extracted from common.js — safety-critical shortcuts available on all pages
   ========================================================================= */

function initGlobalTradingHotkeys() {
  registerShortcut("Ctrl+X", "一键撤销所有挂单", async () => {
    if (!confirm("⚠️ 确定要撤销所有未完成订单吗 (Cancel All Open)?")) return;
    const res = await apiFetch(API.ordersCancelOpen, { method: "POST" });
    if (res.ok) {
      showToast("所有挂单已撤销", "success");
    } else {
      showToast(res.error || "撤单失败", "error");
    }
  });

  registerShortcut("Shift+X", "触发全局一键核按钮 (Kill Switch)", async () => {
    if (!confirm("🚨 警告：这会触发系统 Kill Switch 并清仓！确定执行吗？")) return;
    const res = await apiFetch(API.killSwitch, { method: "POST" });
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
      <div id="quick-trade-error" style="display:none; padding:12px; margin-bottom:16px; background:var(--block-soft); border-left:3px solid var(--block); color:#ff6b6b; font-size:13px; font-weight:500;"></div>
      <form id="quick-trade-form" style="display:flex; flex-direction:column; gap:12px;">
        <label>
          <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">标的代码 (Symbol)</span>
          <input type="text" id="qt-symbol" required placeholder="例如: SPY" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-family:var(--font-mono); text-transform:uppercase;">
        </label>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <label>
            <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">方向 (Side)</span>
            <select id="qt-side" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="buy">买入 (BUY)</option>
              <option value="sell">卖出 (SELL)</option>
            </select>
          </label>
          <label>
            <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">市场 (Market)</span>
            <select id="qt-market" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="US">行情 (US)</option>
              <option value="HK">港股 (HK)</option>
              <option value="CN">A股 (CN)</option>
            </select>
          </label>
        </div>
        <label>
          <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">数量 (Quantity)</span>
          <input type="number" id="qt-qty" required min="1" step="1" value="100" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-family:var(--font-mono);">
        </label>
        <div style="display:grid; grid-template-columns: 1fr 1fr; gap:12px;">
          <label>
            <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">执行算法 (Algo)</span>
            <select id="qt-algo" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="NONE">直接成交 (Direct)</option>
              <option value="TWAP">TWAP (时间加权)</option>
              <option value="VWAP">VWAP (成交量加权)</option>
              <option value="LADDER">LADDER (梯阶/网格)</option>
            </select>
          </label>
          <label>
            <span style="display:block; font-size:12px; color:var(--text-secondary); margin-bottom:4px;">原因 (Reason / Tag)</span>
            <select id="qt-reason" style="width:100%; padding:8px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px;">
              <option value="Manual Plan">计划内执行 (Planned)</option>
              <option value="FOMO">怕错过 (FOMO)</option>
              <option value="Panic">恐慌规避 (Panic)</option>
              <option value="Rebound">抢反弹 (Rebound)</option>
            </select>
          </label>
        </div>

        <div id="qt-ladder-params" style="display:none; grid-template-columns: 1fr 1fr 1fr; gap:12px; margin-top:12px; padding:12px; background:var(--accent-soft); border-radius:4px; border:1px dashed var(--accent);">
          <label>
            <span style="display:block; font-size:11px; color:var(--accent); margin-bottom:4px;">档位 (Levels)</span>
            <input type="number" id="qt-ladder-levels" value="5" min="2" max="20" style="width:100%; padding:6px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:12px;">
          </label>
          <label>
            <span style="display:block; font-size:11px; color:var(--accent); margin-bottom:4px;">起始价 (Start)</span>
            <input type="number" id="qt-ladder-start" step="0.01" style="width:100%; padding:6px; background:var(--bg); border:1px solid var(--border); color:var(--text); border-radius:4px; font-size:12px;">
          </label>
          <label>
            <span style="display:block; font-size:11px; color:var(--accent); margin-bottom:4px;">终止价 (End)</span>
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

    const res = await apiFetch(API.ordersManual, {
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

// Auto-register trading hotkeys when script loads
document.addEventListener("DOMContentLoaded", () => {
  initGlobalTradingHotkeys();
});

/* Dashboard — 洞察详情页 */
(function () {
  "use strict";

  var insightId = null;
  var insightData = null;

  function init() {
    var root = document.getElementById("insight-detail-root");
    if (!root) return;
    insightId = root.getAttribute("data-insight-id");
    if (!insightId) return;

    document.getElementById("btn-ack").addEventListener("click", handleAck);
    document.getElementById("btn-dismiss").addEventListener("click", handleDismiss);

    loadInsight();
  }

  function loadInsight() {
    apiFetch(API.insightDetail(insightId))
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "加载失败");
        insightData = r.data || {};
        renderAll(insightData);
      })
      .catch(function (err) {
        showToast("加载失败: " + err.message, "error");
        document.getElementById("insight-header").innerHTML =
          '<p class="detail-empty">加载失败: ' + escapeHtml(err.message) + "</p>";
      });
  }

  function renderAll(data) {
    renderSummary(data);
    renderEvidence(data);
    renderRecommendation(data);
    renderActionStatus(data);
  }

  function renderSummary(data) {
    var headerEl = document.getElementById("insight-header");
    var metaEl = document.getElementById("insight-meta");
    if (!headerEl || !metaEl) return;

    var severityClass = data.severity === "urgent" ? "badge-error" : data.severity === "notable" ? "badge-warn" : "badge-info";
    var severityLabel = data.severity === "urgent" ? "紧急" : data.severity === "notable" ? "关注" : "信息";
    var ts = data.triggered_at ? new Date(data.triggered_at).toLocaleString("zh-CN") : "";
    var expires = data.expires_at ? new Date(data.expires_at).toLocaleString("zh-CN") : "";

    headerEl.innerHTML =
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">' +
      '<span class="badge ' + severityClass + '" style="font-size:14px;padding:4px 12px;">' + severityLabel + "</span>" +
      '<h3 style="margin:0;">' + escapeHtml(data.headline || "") + "</h3></div>";

    var kindLabel = {
      correlation_break: "相关性断裂", sector_divergence: "板块背离",
      flow_anomaly: "资金流异动", news_driven: "新闻驱动"
    }[data.kind] || data.kind || "";
    var confPct = Math.round((data.confidence || 0) * 100);
    var subjects = (data.subjects || []).map(function (s) {
      return '<span class="badge badge-subject">' + escapeHtml(s) + "</span>";
    }).join(" ");

    metaEl.innerHTML =
      '<span class="badge badge-info">' + escapeHtml(kindLabel) + "</span>" +
      subjects +
      '<span class="meta-text">置信度: ' + confPct + "%</span>" +
      '<span class="meta-text">触发: ' + escapeHtml(ts) + "</span>" +
      (expires ? '<span class="meta-text">过期: ' + escapeHtml(expires) + "</span>" : "");
  }

  function renderEvidence(data) {
    var el = document.getElementById("evidence-list");
    if (!el) return;
    var chain = data.causal_chain || [];
    if (!chain.length) {
      el.innerHTML = '<p class="detail-empty">无证据链数据</p>';
      return;
    }
    el.innerHTML = '<div class="evidence-list">' + chain.map(function (ev, idx) {
      return '<div class="evidence-item">' +
        '<span class="evidence-index">#' + (idx + 1) + "</span>" +
        '<span class="evidence-source">' + escapeHtml(ev.source || "") + "</span>" +
        '<span class="evidence-fact">' + escapeHtml(ev.fact || "") + "</span>" +
        (ev.value && Object.keys(ev.value).length
          ? '<pre style="font-size:11px;margin:4px 0 0 28px;color:var(--text-muted);">' + JSON.stringify(ev.value, null, 2) + "</pre>"
          : "") +
        "</div>";
    }).join("") + "</div>";
  }

  function renderRecommendation(data) {
    var el = document.getElementById("recommendation-body");
    if (!el) return;
    var rec = data.recommendation;
    if (!rec) {
      el.innerHTML = '<p class="detail-empty">暂无交易建议（AI 生成中...）</p>' +
        '<button id="btn-gen-rec" class="button button-sm" type="button">生成交易建议</button>';
      var btn = document.getElementById("btn-gen-rec");
      if (btn) {
        btn.addEventListener("click", function () {
          btn.disabled = true;
          btn.textContent = "生成中...";
          // Reload with recommendation generation
          apiFetch(API.insightDetail(insightId))
            .then(function (r) {
              if (!r.ok) throw new Error(r.error || "加载失败");
              insightData = r.data || {};
              renderRecommendation(insightData);
            })
            .catch(function (err) { showToast("生成失败: " + err.message, "error"); });
        });
      }
      return;
    }
    var actionLabel = { buy: "买入", sell: "卖出", hold: "持有", watch: "观望", avoid: "回避" }[rec.action] || rec.action;
    var actionClass = { buy: "badge-ok", sell: "badge-fail", hold: "badge-info", watch: "badge-warn", avoid: "badge-fail" }[rec.action] || "";
    var riskLabel = { low: "低", medium: "中", high: "高" }[rec.risk_level] || rec.risk_level;
    var horizonLabel = { intraday: "日内", short_term: "短期", medium_term: "中期" }[rec.time_horizon] || rec.time_horizon;
    var confPct = Math.round((rec.confidence || 0.5) * 100);
    el.innerHTML =
      '<div style="display:flex;align-items:center;gap:12px;margin-bottom:12px;">' +
      '<span class="badge ' + actionClass + '" style="font-size:16px;padding:6px 16px;">' + actionLabel + "</span>" +
      '<strong style="font-size:18px;">' + escapeHtml(rec.symbol || "") + "</strong>" +
      "</div>" +
      '<div class="summary-grid" style="grid-template-columns:1fr 1fr 1fr;gap:12px;margin-bottom:12px;">' +
      (rec.entry_price ? _detailBox("入场价", rec.entry_price) : "") +
      (rec.target_price ? _detailBox("目标价", rec.target_price) : "") +
      (rec.stop_loss ? _detailBox("止损价", rec.stop_loss) : "") +
      "</div>" +
      '<div style="display:flex;gap:16px;font-size:13px;color:var(--text-muted);margin-bottom:8px;">' +
      '<span>周期: ' + horizonLabel + "</span>" +
      '<span>风险: ' + riskLabel + "</span>" +
      '<span>置信度: ' + confPct + "%</span>" +
      "</div>" +
      '<div style="position:relative;height:8px;background:var(--surface-2);border-radius:4px;margin-bottom:12px;">' +
      '<div style="width:' + confPct + "%;height:100%;background:var(--accent);border-radius:4px;" + '"></div></div>' +
      '<p style="font-size:14px;line-height:1.6;">' + escapeHtml(rec.rationale || "") + "</p>";
  }

  function _detailBox(label, value) {
    return '<div class="detail-card" style="text-align:center;padding:12px;">' +
      '<div style="font-size:11px;color:var(--text-muted);">' + label + "</div>" +
      '<div style="font-size:20px;font-weight:600;margin-top:4px;">' + escapeHtml(String(value)) + "</div></div>";
  }

  function renderActionStatus(data) {
    var el = document.getElementById("insight-action-status");
    if (!el) return;
    var action = data.user_action || "pending";
    var label = { pending: "待处理", dismissed: "已否决", acknowledged: "已读", acted: "已操作" }[action] || action;
    if (action !== "pending") {
      el.textContent = label;
    }
  }

  function handleAck() {
    apiFetch(API.insightAck(insightId), { method: "POST", body: {} })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "操作失败");
        showToast("已标记已读");
        loadInsight();
      })
      .catch(function (err) { showToast("操作失败: " + err.message, "error"); });
  }

  function handleDismiss() {
    var reason = prompt("否决原因（可选）:");
    apiFetch(API.insightDismiss(insightId), { method: "POST", body: { reason: reason || "" } })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "操作失败");
        showToast("已否决");
        loadInsight();
      })
      .catch(function (err) { showToast("操作失败: " + err.message, "error"); });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

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
    var ai = data._ai_explanation;
    if (!ai) {
      el.innerHTML = '<p class="detail-empty">暂无 AI 分析（点击下方生成为 AI 分析）</p>' +
        '<button id="btn-gen-ai" class="button button-sm" type="button">生成 AI 分析</button>';
      var btn = document.getElementById("btn-gen-ai");
      if (btn) {
        btn.addEventListener("click", function () {
          btn.disabled = true;
          btn.textContent = "生成中...";
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
    var confPct = Math.round((ai.confidence || 0.5) * 100);
    var factors = ai.key_factors || [];
    var risks = ai.risk_factors || [];
    var timeWindow = ai.reference_time_window || "N/A";
    el.innerHTML =
      '<div style="margin-bottom:12px;">' +
      '<div style="display:flex;gap:16px;font-size:13px;color:var(--text-muted);margin-bottom:8px;">' +
      '<span>参考窗口: ' + escapeHtml(timeWindow) + "</span>" +
      '<span>置信度: ' + confPct + "%</span>" +
      "</div>" +
      '<div style="position:relative;height:8px;background:var(--surface-2);border-radius:4px;margin-bottom:12px;">' +
      '<div style="width:' + confPct + "%;height:100%;background:var(--accent);border-radius:4px;" + '"></div></div>' +
      '<p style="font-size:14px;line-height:1.6;margin-bottom:16px;">' + escapeHtml(ai.summary || "") + "</p>" +
      (factors.length ? '<div style="margin-bottom:12px;"><strong style="font-size:13px;">关键因素</strong><ul style="font-size:13px;line-height:1.8;margin:6px 0 0 0;padding-left:20px;">' +
        factors.map(function (f) { return "<li>" + escapeHtml(f) + "</li>"; }).join("") + "</ul></div>" : "") +
      (risks.length ? '<div><strong style="font-size:13px;">风险因素</strong><ul style="font-size:13px;line-height:1.8;margin:6px 0 0 0;padding-left:20px;">' +
        risks.map(function (r) { return "<li>" + escapeHtml(r) + "</li>"; }).join("") + "</ul></div>" : "") +
      "</div>";
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

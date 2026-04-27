/* InsightEngine dashboard — list, filter, dismiss, acknowledge. */
(function attachModule(global) {
  "use strict";

  const DashboardInsights = {
    _activeFilter: "all",
    _items: [],
  };

  /* ── public API ── */

  DashboardInsights.init = function init() {
    document.getElementById("refresh-insights").addEventListener("click", function () {
      DashboardInsights.render();
    });
    document.getElementById("run-insights").addEventListener("click", function () {
      DashboardInsights.runEngine();
    });
    document.querySelectorAll("#insight-tabs .tab").forEach(function (tab) {
      tab.addEventListener("click", function () {
        document.querySelectorAll("#insight-tabs .tab").forEach(function (t) { t.classList.remove("is-active"); });
        tab.classList.add("is-active");
        DashboardInsights._activeFilter = tab.getAttribute("data-filter");
        DashboardInsights._renderList();
      });
    });
    DashboardInsights.render();
  };

  DashboardInsights.render = function render() {
    apiFetch(API.insightsList)
      .then(function (resp) {
        if (!resp.ok) {
          throw new Error(resp.error || "加载失败");
        }
        var payload = resp.data || {};
        DashboardInsights._items = payload.items || [];
        DashboardInsights._renderList();
      })
      .catch(function (err) {
        console.warn("[DashboardInsights] fetch failed:", err);
        document.getElementById("insights-panel").innerHTML =
          '<p class="detail-empty" style="text-align:center;padding:3rem 0;">加载失败: ' + escapeHtml(err.message) + "</p>";
      });
  };

  DashboardInsights.runEngine = function runEngine() {
    var btn = document.getElementById("run-insights");
    btn.disabled = true;
    btn.textContent = "运行中...";
    apiFetch(API.insightsRun, { method: "POST", body: {} })
      .then(function (runResp) {
        if (!runResp.ok) {
          throw new Error(runResp.error || "运行失败");
        }
        showToast("引擎运行完成");
        return apiFetch(API.insightsList);
      })
      .then(function (listResp) {
        if (!listResp.ok) {
          throw new Error(listResp.error || "加载失败");
        }
        var payload = listResp.data || {};
        DashboardInsights._items = payload.items || [];
        DashboardInsights._renderList();
      })
      .catch(function (err) {
        showToast("引擎运行失败: " + err.message, "error");
      })
      .finally(function () {
        btn.disabled = false;
        btn.textContent = "运行引擎";
      });
  };

  /* ── internals ── */

  function _filtered() {
    var f = DashboardInsights._activeFilter;
    if (f === "all") return DashboardInsights._items;
    if (f === "urgent") return DashboardInsights._items.filter(function (i) { return i.severity === "urgent"; });
    if (f === "notable") return DashboardInsights._items.filter(function (i) { return i.severity === "notable"; });
    return DashboardInsights._items;
  }

  DashboardInsights._renderList = function _renderList() {
    var container = document.getElementById("insights-panel");
    var items = _filtered();
    var countEl = document.getElementById("insight-count");
    if (countEl) countEl.textContent = items.length + " 条洞察";

    if (!items.length) {
      container.innerHTML = '<p class="detail-empty" style="text-align:center;padding:3rem 0;">暂无洞察</p>';
      return;
    }

    container.innerHTML = '<div class="insight-list">' + items.map(_renderCard).join("") + "</div>";
  };

  function _renderCard(insight) {
    var severityClass = insight.severity === "urgent" ? "badge-error" : insight.severity === "notable" ? "badge-warn" : "badge-info";
    var severityLabel = insight.severity === "urgent" ? "紧急" : insight.severity === "notable" ? "关注" : "信息";
    var ts = insight.triggered_at ? new Date(insight.triggered_at).toLocaleString("zh-CN") : "";
    var subjectsHtml = (insight.subjects || []).map(function (s) {
      return '<span class="badge badge-subject">' + escapeHtml(s) + "</span>";
    }).join(" ");
    var action = insight.user_action || "pending";
    var actionLabel = action === "dismissed" ? "已否决" : action === "acknowledged" ? "已读" : "";
    var expandedId = "ev-" + insight.id;

    return (
      '<article class="insight-card" data-id="' + escapeHtml(insight.id) + '">' +
        '<div class="insight-card-header">' +
          '<span class="badge ' + severityClass + '">' + severityLabel + "</span>" +
          '<span class="insight-headline">' + escapeHtml(insight.headline) + "</span>" +
          (actionLabel ? '<span class="meta-text" style="margin-left:auto;">' + actionLabel + "</span>" : "") +
        "</div>" +
        '<div class="insight-card-meta">' +
          subjectsHtml +
          '<span class="meta-text">置信度: ' + (insight.confidence * 100).toFixed(0) + "%</span>" +
          '<span class="meta-text">' + escapeHtml(ts) + "</span>" +
        "</div>" +
        '<div class="insight-card-actions">' +
          '<button class="button button-xs" onclick="DashboardInsights._toggleEvidence(\'' + expandedId + '\')">展开</button> ' +
          (action === "pending" ? (
            '<button class="button button-xs" onclick="DashboardInsights._ack(\'' + escapeHtml(insight.id) + '\')">已读</button> ' +
            '<button class="button button-xs" onclick="DashboardInsights._dismiss(\'' + escapeHtml(insight.id) + '\')">否决</button>'
          ) : "") +
        "</div>" +
        '<div id="' + expandedId + '" class="insight-evidence" style="display:none;">' +
          _renderCausalChain(insight.causal_chain || []) +
        "</div>" +
      "</article>"
    );
  }

  DashboardInsights._toggleEvidence = function _toggleEvidence(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = el.style.display === "none" ? "block" : "none";
  };

  function _renderCausalChain(evidence) {
    if (!evidence.length) return "";
    var html = '<div class="evidence-list"><h4 style="margin:0 0 0.5rem;font-size:13px;">证据链</h4>';
    evidence.forEach(function (ev, idx) {
      html += (
        '<div class="evidence-item">' +
          '<span class="evidence-index">#' + (idx + 1) + "</span>" +
          '<span class="evidence-source">' + escapeHtml(ev.source || "") + "</span>" +
          '<span class="evidence-fact">' + escapeHtml(ev.fact || "") + "</span>" +
        "</div>"
      );
    });
    html += "</div>";
    return html;
  }

  DashboardInsights._dismiss = function _dismiss(id) {
    var reason = prompt("否决原因（可选）:");
    apiFetch(API.insightDismiss(id), { method: "POST", body: { reason: reason || "" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error(resp.error || "否决失败");
        showToast("已否决");
        DashboardInsights.render();
      })
      .catch(function (err) { showToast("操作失败: " + err.message, "error"); });
  };

  DashboardInsights._ack = function _ack(id) {
    var note = prompt("备注（可选）:");
    apiFetch(API.insightAck(id), { method: "POST", body: { note: note || "" } })
      .then(function (resp) {
        if (!resp.ok) throw new Error(resp.error || "标记失败");
        showToast("已标记已读");
        DashboardInsights.render();
      })
      .catch(function (err) { showToast("操作失败: " + err.message, "error"); });
  };

  /* ── export ── */
  global.DashboardInsights = DashboardInsights;

  /* auto-init on DOMContentLoaded */
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { DashboardInsights.init(); });
  } else {
    DashboardInsights.init();
  }
})(window);

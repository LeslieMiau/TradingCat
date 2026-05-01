/* Dashboard — 盘前简报详情页 */
(function () {
  "use strict";

  function loadData(asOf) {
    var url = API.briefingData(asOf);
    return apiFetch(url).then(function (r) {
      if (!r.ok) throw new Error(r.error || "加载失败");
      return r.data || {};
    });
  }

  function runBriefing() {
    var btn = document.getElementById("run-briefing");
    btn.disabled = true;
    btn.textContent = "运行中...";
    // Trigger the pre_market_briefing scheduler job
    apiFetch(API.schedulerRun("pre_market_briefing"), { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "运行失败");
        showToast("简报已生成");
        return loadData();
      })
      .then(function (data) { renderAll(data); })
      .catch(function (err) { showToast("运行失败: " + err.message, "error"); })
      .finally(function () { btn.disabled = false; btn.textContent = "运行简报"; });
  }

  function renderAll(data) {
    renderOverview(data);
    renderLevels(data);
    renderSectors(data);
    renderRecommendations(data);
    renderAIBriefing(data);
    renderAwareness(data);
  }

  function renderOverview(data) {
    var el = document.getElementById("overview-cards");
    if (!el) return;
    var a = data.awareness_snapshot || {};
    var regime = a.overall_regime || "N/A";
    var risk = a.risk_posture || "N/A";
    var conf = a.confidence || "N/A";
    var regimeLabel = { bullish: "看涨", neutral: "中性", caution: "谨慎", risk_off: "避险" }[regime] || regime;
    var regimeClass = { bullish: "badge-ok", neutral: "badge-warn", caution: "badge-warn", risk_off: "badge-fail" }[regime] || "";
    var riskClass = { build_risk: "badge-ok", hold_pace: "badge-info", reduce_risk: "badge-warn", pause_new_adds: "badge-fail" }[risk] || "";
    var riskLabel = { build_risk: "加仓", hold_pace: "稳健", reduce_risk: "减仓", pause_new_adds: "暂停" }[risk] || risk;

    el.innerHTML = [
      metricTile("市场体制", '<span class="badge ' + regimeClass + '">' + regimeLabel + "</span>", regime),
      metricTile("风险姿态", '<span class="badge ' + riskClass + '">' + riskLabel + "</span>", risk),
      metricTile("置信度", conf, ""),
      metricTile("参与状态", data.skipped_reason ? "已跳过" : "已准备", data.skipped_reason || "简报就绪"),
    ].join("");
  }

  function renderLevels(data) {
    var tbody = document.getElementById("levels-table");
    if (!tbody) return;
    var levels = data.support_resistance || [];
    if (!levels.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="table-empty">暂无数据（运行简报后生成）</td></tr>';
      return;
    }
    tbody.innerHTML = levels.map(function (l) {
      var s = (l.support_levels || []).join(", ") || "—";
      var r = (l.resistance_levels || []).join(", ") || "—";
      return "<tr><td>" + escapeHtml(l.asset || "—") + "</td><td>" + escapeHtml(s) + "</td><td>" + escapeHtml(r) + "</td></tr>";
    }).join("");
  }

  function renderSectors(data) {
    var el = document.getElementById("sectors-list");
    if (!el) return;
    var sectors = data.sector_rotation || [];
    if (!sectors.length) {
      el.innerHTML = '<p class="detail-empty">暂无数据（运行简报后生成）</p>';
      return;
    }
    el.innerHTML = sectors.map(function (s) {
      var dir = s.direction || "neutral";
      var dirLabel = { strengthening: "走强", weakening: "走弱", neutral: "中性" }[dir] || dir;
      var dirClass = { strengthening: "badge-ok", weakening: "badge-fail", neutral: "badge-warn" }[dir] || "";
      return '<article class="detail-card"><h4>' + escapeHtml(s.sector || "—") + '</h4>' +
        '<p style="font-size:13px;">' + escapeHtml(s.observation || "") + '</p>' +
        '<span class="badge ' + dirClass + '" style="margin-top:4px;">' + dirLabel + "</span></article>";
    }).join("");
  }

  function renderRecommendations(data) {
    var el = document.getElementById("recommendations-list");
    if (!el) return;
    var obs = data.observations || [];
    if (!obs.length) {
      el.innerHTML = '<p class="detail-empty">暂无观察（运行简报后生成）</p>';
      return;
    }
    el.innerHTML = obs.map(function (o) {
      var confPct = Math.round((o.confidence || 0.5) * 100);
      var horizonLabel = { intraday: "日内", short_term: "短期", medium_term: "中期" }[o.time_horizon] || o.time_horizon || "N/A";
      return '<article class="detail-card" style="border-left:3px solid var(--accent);">' +
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">' +
        '<strong>' + escapeHtml(o.symbol || "") + "</strong>" +
        "</div>" +
        '<div style="margin:8px 0;display:flex;gap:12px;font-size:12px;color:var(--text-muted);">' +
        '<span>周期: ' + horizonLabel + "</span>" +
        '<span>置信度: ' + confPct + "%</span>" +
        "</div>" +
        '<div style="position:relative;height:6px;background:var(--surface-2);border-radius:3px;margin-bottom:8px;">' +
        '<div style="width:' + confPct + "%;height:100%;background:var(--accent);border-radius:3px;" + '"></div></div>' +
        '<p style="font-size:13px;margin:0;">' + escapeHtml(o.observation || o.rationale || "") + "</p>" +
        "</article>";
    }).join("");
  }

  function renderAIBriefing(data) {
    var el = document.getElementById("ai-analysis-content");
    if (!el) return;
    var text = data.briefing_text || "暂无内容（运行简报后生成）";
    el.innerHTML = text;
  }

  function renderAwareness(data) {
    var el = document.getElementById("awareness-raw");
    if (!el) return;
    el.textContent = JSON.stringify(data.awareness_snapshot || {}, null, 2);
  }

  /* ── Init ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("refresh-briefing").addEventListener("click", function () {
      loadData().then(renderAll).catch(function (err) {
        showToast("刷新失败: " + err.message, "error");
      });
    });
    document.getElementById("run-briefing").addEventListener("click", runBriefing);
    loadData().then(renderAll).catch(function (err) {
      showToast("加载失败: " + err.message, "error");
    });
  });
})();

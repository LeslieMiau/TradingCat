/* Dashboard — 盘后复盘详情页 */
(function () {
  "use strict";

  function loadData(asOf) {
    var url = API.reviewData(asOf);
    return apiFetch(url).then(function (r) {
      if (!r.ok) throw new Error(r.error || "加载失败");
      return r.data || {};
    });
  }

  function runReview() {
    var btn = document.getElementById("run-review");
    btn.disabled = true;
    btn.textContent = "运行中...";
    apiFetch(API.schedulerRun("post_market_reflection"), { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "运行失败");
        showToast("复盘已完成");
        return loadData();
      })
      .then(function (data) { renderAll(data); })
      .catch(function (err) { showToast("运行失败: " + err.message, "error"); })
      .finally(function () { btn.disabled = false; btn.textContent = "运行复盘"; });
  }

  function renderAll(data) {
    renderPlan(data);
    renderSummary(data);
    renderDeviations(data);
    renderScores(data);
    renderLessons(data);
    renderAdjustments(data);
    renderJournal(data);
  }

  function renderPlan(data) {
    var plan = data.plan || {};
    var headlineEl = document.getElementById("plan-headline");
    var metricsEl = document.getElementById("plan-metrics");
    var reasonsEl = document.getElementById("plan-reasons");
    if (headlineEl) headlineEl.textContent = plan.headline || "暂无计划";
    var statusLabel = { planned: "已计划", no_trade: "不交易", blocked: "阻塞" }[plan.status] || plan.status || "—";
    var counts = plan.counts || {};
    if (metricsEl) {
      metricsEl.innerHTML = "<tr><td>" + escapeHtml(statusLabel) + "</td><td>" +
        (counts.signal_count || 0) + "</td><td>" +
        (counts.intent_count || 0) + "</td><td>" +
        (counts.manual_count || 0) + "</td></tr>";
    }
    if (reasonsEl) {
      var reasons = plan.reasons || [];
      reasonsEl.innerHTML = reasons.length
        ? reasons.map(function (r) { return "<li>" + escapeHtml(r) + "</li>"; }).join("")
        : '<li class="detail-empty">暂无原因说明</li>';
    }
  }

  function renderSummary(data) {
    var summary = data.summary || {};
    var headlineEl = document.getElementById("summary-headline");
    if (headlineEl) headlineEl.textContent = summary.headline || "暂无总结";
    ["highlights", "blockers", "next_actions"].forEach(function (key) {
      var el = document.getElementById("summary-" + key);
      if (!el) return;
      var items = summary[key] || [];
      el.innerHTML = items.length
        ? items.map(function (i) { return "<li>" + escapeHtml(i) + "</li>"; }).join("")
        : '<li class="detail-empty">暂无</li>';
    });
  }

  function renderDeviations(data) {
    var el = document.getElementById("deviations-list");
    if (!el) return;
    var devs = data.deviations || [];
    el.innerHTML = devs.length
      ? devs.map(function (d) { return "<li><span class='badge badge-fail' style='margin-right:6px;'>偏差</span>" + escapeHtml(d) + "</li>"; }).join("")
      : '<li class="detail-empty">计划与总结一致，无明显偏差</li>';
  }

  function renderScores(data) {
    var tbody = document.getElementById("scores-table");
    if (!tbody) return;
    var scores = data.trade_scores || [];
    if (!scores.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="table-empty">暂无评分（运行复盘后生成）</td></tr>';
      return;
    }
    tbody.innerHTML = scores.map(function (s) {
      return "<tr><td>" + escapeHtml(s.symbol || "—") + "</td><td>" +
        _scoreBadge(s.score) + "</td><td>" +
        (s.entry_quality != null ? s.entry_quality + "/10" : "—") + "</td><td>" +
        (s.exit_quality != null ? s.exit_quality + "/10" : "—") + "</td><td>" +
        (s.sizing_quality != null ? s.sizing_quality + "/10" : "—") + "</td><td>" +
        escapeHtml(s.notes || "") + "</td></tr>";
    }).join("");
  }

  function _scoreBadge(score) {
    if (score == null) return "—";
    var cls = score >= 7 ? "badge-ok" : score >= 4 ? "badge-warn" : "badge-fail";
    return '<span class="badge ' + cls + '">' + score + "/10</span>";
  }

  function renderLessons(data) {
    var el = document.getElementById("lessons-list");
    if (!el) return;
    var lessons = data.lessons_learned || [];
    if (!lessons.length) {
      el.innerHTML = '<p class="detail-empty">暂无经验教训（运行复盘后生成）</p>';
      return;
    }
    var catLabel = { execution: "执行类", planning: "计划类", risk_management: "风控类" };
    var catClass = { execution: "badge-warn", planning: "badge-info", risk_management: "badge-fail" };
    el.innerHTML = lessons.map(function (l) {
      var cat = l.category || "";
      return '<article class="detail-card">' +
        '<span class="badge ' + (catClass[cat] || "") + '" style="margin-bottom:6px;">' + (catLabel[cat] || cat) + "</span>" +
        "<p>" + escapeHtml(l.lesson || "") + "</p>" +
        (l.impact ? '<p style="font-size:12px;color:var(--text-muted);">影响: ' + escapeHtml(l.impact) + "</p>" : "") +
        "</article>";
    }).join("");
  }

  function renderAdjustments(data) {
    var el = document.getElementById("adjustments-list");
    if (!el) return;
    var adjs = data.adjustments || [];
    if (!adjs.length) {
      el.innerHTML = '<p class="detail-empty">暂无调整建议（运行复盘后生成）</p>';
      return;
    }
    el.innerHTML = adjs.map(function (a) {
      return '<article class="detail-card" style="border-left:3px solid var(--accent);">' +
        "<h4>" + escapeHtml(a.adjustment || "") + "</h4>" +
        (a.reason ? '<p style="font-size:13px;">原因: ' + escapeHtml(a.reason) + "</p>" : "") +
        (a.target_outcome ? '<p style="font-size:12px;color:var(--text-muted);">预期效果: ' + escapeHtml(a.target_outcome) + "</p>" : "") +
        "</article>";
    }).join("");
  }

  function renderJournal(data) {
    var el = document.getElementById("ai-journal-content");
    if (!el) return;
    el.innerHTML = data.ai_journal_text || "暂无内容（运行复盘后生成）";
  }

  /* ── Init ── */
  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("refresh-review").addEventListener("click", function () {
      loadData().then(renderAll).catch(function (err) {
        showToast("刷新失败: " + err.message, "error");
      });
    });
    document.getElementById("run-review").addEventListener("click", runReview);
    loadData().then(renderAll).catch(function (err) {
      showToast("加载失败: " + err.message, "error");
    });
  });
})();

/* Daily Log — unified briefing + review + journal */
(function () {
  "use strict";

  var CACHE = { briefing: null, review: null, journal: null };
  var ACTIVE_TAB = "briefing";

  // ── Tab switching ──────────────────────────────────────────────────────

  function switchTab(tab) {
    ACTIVE_TAB = tab;
    document.querySelectorAll("#daily-log-tabs .tab").forEach(function (t) {
      t.classList.toggle("is-active", t.dataset.tab === tab);
    });
    document.querySelectorAll(".tab-panel").forEach(function (p) {
      p.style.display = p.id === "tab-" + tab ? "" : "none";
    });
    document.getElementById("run-briefing-btn").style.display = tab === "briefing" ? "" : "none";
    document.getElementById("run-review-btn").style.display = tab === "review" ? "" : "none";
  }

  document.getElementById("daily-log-tabs").addEventListener("click", function (e) {
    var tab = e.target.closest(".tab");
    if (!tab) return;
    switchTab(tab.dataset.tab);
  });

  // ── Data loading ───────────────────────────────────────────────────────

  function loadBriefing() {
    return apiFetch(API.briefingData()).then(function (r) {
      if (!r.ok) throw new Error(r.error || "加载失败");
      CACHE.briefing = r.data || {};
      renderBriefing(CACHE.briefing);
    });
  }

  function loadReview() {
    return apiFetch(API.reviewData()).then(function (r) {
      if (!r.ok) throw new Error(r.error || "加载失败");
      CACHE.review = r.data || {};
      renderReview(CACHE.review);
    });
  }

  function loadJournal() {
    var planP = apiFetch(API.journalPlans()).then(function (r) { return r.ok ? r.data || {} : {}; });
    var summaryP = apiFetch(API.journalSummaries()).then(function (r) { return r.ok ? r.data || {} : {}; });
    var latestPlanP = apiFetch(API.journalPlansLatest()).then(function (r) { return r.ok ? r.data || null : null; });
    var latestSummaryP = apiFetch(API.journalSummariesLatest()).then(function (r) { return r.ok ? r.data || null : null; });

    return Promise.all([planP, summaryP, latestPlanP, latestSummaryP]).then(function (res) {
      // list endpoints return dict-of-dict; normalize to array
      var plans = Object.values(res[0] || {});
      var summaries = Object.values(res[1] || {});
      CACHE.journal = { plans: plans, summaries: summaries, latestPlan: res[2], latestSummary: res[3] };
      renderJournal(CACHE.journal);
    });
  }

  function refreshAll() {
    var btn = document.getElementById("refresh-daily-log");
    btn.disabled = true;
    btn.textContent = "刷新中...";
    Promise.all([loadBriefing(), loadReview(), loadJournal()])
      .catch(function (err) { showToast("部分数据加载失败", "warn"); })
      .finally(function () { btn.disabled = false; btn.textContent = "刷新数据"; });
  }

  // ── Briefing rendering ─────────────────────────────────────────────────

  function renderBriefing(data) {
    var a = data.awareness_snapshot || {};
    var regimeClass = { bullish: "badge-ok", neutral: "badge-warn", caution: "badge-warn", risk_off: "badge-fail" }[a.overall_regime] || "";
    var regimeLabel = { bullish: "看涨", neutral: "中性", caution: "谨慎", risk_off: "避险" }[a.overall_regime] || a.overall_regime || "N/A";
    var riskClass = { aggressive: "badge-warn", moderate: "badge-info", conservative: "badge-ok", halted: "badge-fail" }[a.risk_posture] || "";
    var riskLabel = { aggressive: "激进", moderate: "稳健", conservative: "保守", halted: "停止" }[a.risk_posture] || a.risk_posture || "N/A";

    document.getElementById("briefing-overview").innerHTML = [
      metricTile("市场体制", '<span class="badge ' + regimeClass + '">' + regimeLabel + "</span>", a.overall_regime || ""),
      metricTile("风险姿态", '<span class="badge ' + riskClass + '">' + riskLabel + "</span>", a.risk_posture || ""),
      metricTile("置信度", a.confidence || "N/A", ""),
      metricTile("参与状态", data.skipped_reason ? "已跳过" : "已就绪", data.skipped_reason || ""),
    ].join("");

    // Support/resistance levels
    var levels = data.support_resistance || [];
    var levelsTbody = document.getElementById("briefing-levels");
    if (levels.length) {
      levelsTbody.innerHTML = levels.map(function (l) {
        return "<tr><td>" + escapeHtml(l.asset || l.symbol || "—") + "</td><td>" + escapeHtml(String(l.support || "—")) + "</td><td>" + escapeHtml(String(l.resistance || "—")) + "</td></tr>";
      }).join("");
    } else {
      levelsTbody.innerHTML = '<tr><td colspan="3" class="table-empty">暂无支撑阻力位数据</td></tr>';
    }

    // Sector rotation
    var sectorsEl = document.getElementById("briefing-sectors");
    var sectors = data.sector_rotation || [];
    if (sectors.length) {
      sectorsEl.innerHTML = sectors.map(function (s) {
        return '<article class="detail-card"><h4>' + escapeHtml(s.sector || s.name || "—") + '</h4><p>' + escapeHtml(s.observation || s.trend || "—") + "</p></article>";
      }).join("");
    } else {
      sectorsEl.innerHTML = '<p class="detail-empty">暂无板块轮动数据</p>';
    }

    // Recommendations
    var recs = data.recommendations || [];
    var recsEl = document.getElementById("briefing-recommendations");
    if (recs.length) {
      recsEl.innerHTML = recs.map(function (r) {
        return '<article class="detail-card"><h4>' + escapeHtml(r.title || r.action || "观察") + '</h4><p>' + escapeHtml(r.detail || r.rationale || "—") + "</p></article>";
      }).join("");
    } else {
      recsEl.innerHTML = '<p class="detail-empty">暂无市场观察</p>';
    }

    // AI analysis
    var aiEl = document.getElementById("briefing-ai");
    var aiText = data.briefing_text || "";
    if (aiText) {
      aiEl.innerHTML = '<div style="white-space:pre-wrap">' + escapeHtml(aiText) + "</div>";
    } else {
      aiEl.innerHTML = '<p class="detail-empty">AI 分析尚未生成，点击「运行简报」触发</p>';
    }

    // Awareness raw
    var awarenessEl = document.getElementById("briefing-awareness");
    awarenessEl.textContent = JSON.stringify(a, null, 2);
  }

  // ── Review rendering ───────────────────────────────────────────────────

  function renderReview(data) {
    var plan = data.plan || {};
    document.getElementById("review-plan-headline").textContent = plan.headline || "暂无计划";
    var statusLabel = { planned: "已计划", no_trade: "不交易", blocked: "阻塞" }[plan.status] || plan.status || "—";
    var counts = plan.counts || {};
    document.getElementById("review-plan-metrics").innerHTML =
      "<tr><td>" + statusLabel + "</td><td>" + (counts.signal_count || 0) + "</td><td>" + (counts.intent_count || 0) + "</td><td>" + (counts.manual_count || 0) + "</td></tr>";
    var planReasons = plan.reasons || [];
    document.getElementById("review-plan-reasons").innerHTML = planReasons.length
      ? planReasons.map(function (r) { return "<li>" + escapeHtml(r) + "</li>"; }).join("")
      : '<li class="detail-empty">暂无原因说明</li>';

    var summary = data.summary || {};
    document.getElementById("review-summary-headline").textContent = summary.headline || "暂无总结";
    document.getElementById("review-highlights").innerHTML = (summary.highlights || []).length
      ? summary.highlights.map(function (h) { return "<li>" + escapeHtml(h) + "</li>"; }).join("")
      : '<li class="detail-empty">暂无亮点</li>';
    document.getElementById("review-blockers").innerHTML = (summary.blockers || []).length
      ? summary.blockers.map(function (b) { return "<li>" + escapeHtml(b) + "</li>"; }).join("")
      : '<li class="detail-empty">无阻塞项</li>';
    document.getElementById("review-next-actions").innerHTML = (summary.next_actions || []).length
      ? summary.next_actions.map(function (a) { return "<li>" + escapeHtml(a) + "</li>"; }).join("")
      : '<li class="detail-empty">暂无</li>';

    // Deviations
    var devs = data.deviations || [];
    document.getElementById("review-deviations").innerHTML = devs.length
      ? devs.map(function (d) { return "<li>" + escapeHtml(d) + "</li>"; }).join("")
      : '<li class="detail-empty">无偏差</li>';

    // Trade scores
    var scores = data.trade_scores || [];
    var scoresTbody = document.getElementById("review-scores");
    if (scores.length) {
      scoresTbody.innerHTML = scores.map(function (s) {
        return "<tr><td>" + escapeHtml(s.symbol || "—") + "</td><td>" + (s.overall_score != null ? s.overall_score : "—") + "</td><td>" + (s.entry_score != null ? s.entry_score : "—") + "</td><td>" + (s.exit_score != null ? s.exit_score : "—") + "</td><td>" + (s.position_score != null ? s.position_score : "—") + "</td><td>" + escapeHtml(s.note || "—") + "</td></tr>";
      }).join("");
    } else {
      scoresTbody.innerHTML = '<tr><td colspan="6" class="table-empty">暂无评分数据</td></tr>';
    }

    // Lessons
    var lessons = data.lessons_learned || [];
    var lessonsEl = document.getElementById("review-lessons");
    if (lessons.length) {
      lessonsEl.innerHTML = lessons.map(function (l) {
        return '<article class="detail-card"><h4>' + escapeHtml(l.category || "经验") + '</h4><p>' + escapeHtml(l.lesson || l.text || "—") + "</p></article>";
      }).join("");
    } else {
      lessonsEl.innerHTML = '<p class="detail-empty">暂无经验教训</p>';
    }

    // Adjustments
    var adjustments = data.adjustments || [];
    var adjEl = document.getElementById("review-adjustments");
    if (adjustments.length) {
      adjEl.innerHTML = adjustments.map(function (a) {
        return '<article class="detail-card"><h4>' + escapeHtml(a.action || "调整") + '</h4><p>' + escapeHtml(a.rationale || a.detail || "—") + "</p></article>";
      }).join("");
    } else {
      adjEl.innerHTML = '<p class="detail-empty">暂无建议调整</p>';
    }

    // AI journal
    var journalEl = document.getElementById("review-ai-journal");
    var aiJournal = data.ai_journal_text || "";
    if (aiJournal) {
      journalEl.innerHTML = '<div style="white-space:pre-wrap">' + escapeHtml(aiJournal) + "</div>";
    } else {
      journalEl.innerHTML = '<p class="detail-empty">AI 日志尚未生成</p>';
    }
  }

  // ── Journal rendering ──────────────────────────────────────────────────

  function renderJournal(data) {
    var latestPlan = data.latestPlan || {};
    var latestSummary = data.latestSummary || {};
    var plans = data.plans || [];
    var summaries = data.summaries || [];

    // Today's summary metrics
    var planCount = (latestPlan.items || []).length || (latestPlan.counts || {}).intent_count || 0;
    var summaryOrderCount = (latestSummary.metrics || {}).order_count || 0;
    document.getElementById("journal-metrics").innerHTML = [
      metricTile("计划状态", latestPlan.status || "—", ""),
      metricTile("计划条目", planCount, "条"),
      metricTile("总结订单", summaryOrderCount, "笔"),
      metricTile("归档天数", plans.length > 0 ? plans.length : "—", "天"),
    ].join("");

    document.getElementById("journal-plan-headline").textContent = latestPlan.headline || "暂无今日计划";
    var planItems = latestPlan.items || [];
    document.getElementById("journal-plan-body").innerHTML = planItems.length
      ? planItems.map(function (i) { return "<li>" + escapeHtml(i.symbol || i.intent_id || JSON.stringify(i)) + "</li>"; }).join("")
      : '<li class="detail-empty">暂无计划条目</li>';

    document.getElementById("journal-summary-headline").textContent = latestSummary.headline || "暂无今日总结";
    var summaryHighlights = latestSummary.highlights || [];
    document.getElementById("journal-summary-body").innerHTML = summaryHighlights.length
      ? summaryHighlights.map(function (h) { return "<li>" + escapeHtml(h) + "</li>"; }).join("")
      : '<li class="detail-empty">暂无总结亮点</li>';

    document.getElementById("journal-updated").textContent = "最近更新: " + new Date().toLocaleString("zh-CN");

    // 7-day timeline
    var allDates = {};
    plans.forEach(function (p) { allDates[p.as_of || p.date || ""] = allDates[p.as_of || p.date || ""] || {}; (allDates[p.as_of || p.date || ""]).plan = p; });
    summaries.forEach(function (s) { allDates[s.as_of || s.date || ""] = allDates[s.as_of || s.date || ""] || {}; (allDates[s.as_of || s.date || ""]).summary = s; });
    var sortedDates = Object.keys(allDates).filter(Boolean).sort().reverse().slice(0, 7);

    // Coverage metrics
    var daysWithPlan = sortedDates.filter(function (d) { return allDates[d].plan; }).length;
    var daysWithSummary = sortedDates.filter(function (d) { return allDates[d].summary; }).length;
    document.getElementById("journal-coverage-metrics").innerHTML = [
      metricTile("归档窗口", sortedDates.length + " / 7", "天"),
      metricTile("有计划", daysWithPlan, "天"),
      metricTile("有总结", daysWithSummary, "天"),
      metricTile("完整度", daysWithPlan > 0 && daysWithSummary > 0 ? Math.round(Math.min(daysWithPlan, daysWithSummary) / Math.max(sortedDates.length, 1) * 100) + "%" : "0%", ""),
    ].join("");

    var timelineTbody = document.getElementById("journal-timeline");
    if (sortedDates.length) {
      timelineTbody.innerHTML = sortedDates.map(function (d) {
        var p = allDates[d].plan || {};
        var s = allDates[d].summary || {};
        return "<tr><td>" + d + "</td><td>" + escapeHtml(p.status || "—") + "</td><td>" + ((p.items || []).length || (p.counts || {}).intent_count || "—") + "</td><td>" + escapeHtml((s.blockers || [])[0] || "—") + "</td><td>" + escapeHtml((s.next_actions || [])[0] || "—") + "</td></tr>";
      }).join("");
    } else {
      timelineTbody.innerHTML = '<tr><td colspan="5" class="table-empty">暂无归档数据</td></tr>';
    }

    // Plans table
    var plansTbody = document.getElementById("journal-plans-table");
    if (plans.length) {
      plansTbody.innerHTML = plans.map(function (p) {
        return "<tr><td>" + (p.as_of || p.date || "—") + "</td><td>" + escapeHtml(p.status || "—") + "</td><td style='max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>" + escapeHtml(p.headline || "—") + "</td><td>" + ((p.items || []).length || (p.counts || {}).intent_count || "—") + "</td><td style='max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>" + escapeHtml((p.reasons || [])[0] || "—") + "</td></tr>";
      }).join("");
    } else {
      plansTbody.innerHTML = '<tr><td colspan="5" class="table-empty">暂无计划归档</td></tr>';
    }

    // Summaries table
    var summariesTbody = document.getElementById("journal-summaries-table");
    if (summaries.length) {
      summariesTbody.innerHTML = summaries.map(function (s) {
        return "<tr><td>" + (s.as_of || s.date || "—") + "</td><td style='max-width:150px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap'>" + escapeHtml(s.headline || "—") + "</td><td>" + escapeHtml((s.highlights || [])[0] || "—") + "</td><td>" + escapeHtml((s.blockers || [])[0] || "—") + "</td><td>" + escapeHtml((s.next_actions || [])[0] || "—") + "</td></tr>";
      }).join("");
    } else {
      summariesTbody.innerHTML = '<tr><td colspan="5" class="table-empty">暂无总结归档</td></tr>';
    }
  }

  // ── Action buttons ─────────────────────────────────────────────────────

  function runBriefing() {
    var btn = document.getElementById("run-briefing-btn");
    btn.disabled = true;
    btn.textContent = "运行中...";
    apiFetch(API.schedulerRun("pre_market_briefing"), { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "运行失败");
        showToast("简报已生成");
        return loadBriefing();
      })
      .catch(function (err) { showToast("运行失败: " + err.message, "error"); })
      .finally(function () { btn.disabled = false; btn.textContent = "运行简报"; });
  }

  function runReview() {
    var btn = document.getElementById("run-review-btn");
    btn.disabled = true;
    btn.textContent = "运行中...";
    apiFetch(API.schedulerRun("post_market_reflection"), { method: "POST" })
      .then(function (r) {
        if (!r.ok) throw new Error(r.error || "运行失败");
        showToast("复盘已完成");
        return loadReview();
      })
      .catch(function (err) { showToast("运行失败: " + err.message, "error"); })
      .finally(function () { btn.disabled = false; btn.textContent = "运行复盘"; });
  }

  document.getElementById("run-briefing-btn").addEventListener("click", runBriefing);
  document.getElementById("run-review-btn").addEventListener("click", runReview);
  document.getElementById("refresh-daily-log").addEventListener("click", refreshAll);

  // ── Init ───────────────────────────────────────────────────────────────

  // Show appropriate action button for initial tab
  document.getElementById("run-briefing-btn").style.display = "";

  // Load all data at startup so tabs switch instantly
  loadBriefing().catch(function () {});
  loadReview().catch(function () {});
  loadJournal().catch(function () {});
})();

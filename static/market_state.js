/* Market-state snapshot and timeline widgets. */
(function attachMarketState(global) {
  "use strict";

  const LOAD_TIMEOUT_MS = 10000;

  const MarketState = {
    market: "CN",
  };

  MarketState.initResearch = function initResearch() {
    const root = document.getElementById("market-state-widget");
    if (!root) return;
    bindMarketButtons(root);
    root.querySelector("[data-market-state-run]")?.addEventListener("click", () => runSnapshot(root));
    // Defer to avoid competing with research.js refreshResearch()
    requestAnimationFrame(() => loadSnapshot(root));
  };

  MarketState.initTimeline = function initTimeline() {
    const root = document.getElementById("market-state-timeline-widget");
    if (!root) return;
    bindMarketButtons(root);
    root.querySelector("[data-market-state-run]")?.addEventListener("click", () => runSnapshot(root, true));
    requestAnimationFrame(() => loadTimeline(root));
  };

  function bindMarketButtons(root) {
    root.querySelectorAll("[data-market-state-market]").forEach((button) => {
      button.addEventListener("click", () => {
        MarketState.market = button.getAttribute("data-market-state-market") || "CN";
        root.querySelectorAll("[data-market-state-market]").forEach((node) => node.classList.remove("is-active"));
        button.classList.add("is-active");
        if (root.id === "market-state-timeline-widget") {
          loadTimeline(root);
        } else {
          loadSnapshot(root);
        }
      });
    });
  }

  function loadSnapshot(root) {
    const metrics = root.querySelector("[data-market-state-metrics]");
    const body = root.querySelector("[data-market-state-body]");
    if (metrics) metrics.innerHTML = '<article class="metric-tile loading"><span>加载中...</span></article>';
    if (body) body.innerHTML = "";

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LOAD_TIMEOUT_MS);

    apiFetch(API.researchMarketState(MarketState.market, false), { signal: controller.signal })
      .then((resp) => {
        clearTimeout(timeoutId);
        if (!resp.ok) throw new Error(resp.error || "加载失败");
        renderSnapshot(root, resp.data || {});
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        const msg = err.name === "AbortError" ? "加载超时，请稍后重试" : err.message;
        if (body) body.innerHTML = `<p class="detail-empty">市场结构快照${msg}</p>`;
      });
  }

  function runSnapshot(root, timelineAfter = false) {
    const button = root.querySelector("[data-market-state-run]");
    if (button) {
      button.disabled = true;
      button.textContent = "刷新中...";
    }
    apiFetch(API.researchMarketStateRun(MarketState.market, false), { method: "POST", body: {} })
      .then((resp) => {
        if (!resp.ok) throw new Error(resp.error || "刷新失败");
        showToast("市场结构快照已刷新");
        if (timelineAfter) {
          loadTimeline(root);
        } else {
          renderSnapshot(root, resp.data || {});
        }
      })
      .catch((err) => showToast("市场结构刷新失败: " + err.message, "error"))
      .finally(() => {
        if (button) {
          button.disabled = false;
          button.textContent = "刷新快照";
        }
      });
  }

  function loadTimeline(root) {
    const list = root.querySelector("[data-market-state-timeline]");
    if (list) list.innerHTML = '<p class="detail-empty">加载时间线...</p>';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), LOAD_TIMEOUT_MS);

    apiFetch(API.researchMarketStateTimeline(MarketState.market), { signal: controller.signal })
      .then((resp) => {
        clearTimeout(timeoutId);
        if (!resp.ok) throw new Error(resp.error || "加载失败");
        renderTimeline(root, resp.data || {});
      })
      .catch((err) => {
        clearTimeout(timeoutId);
        const msg = err.name === "AbortError" ? "加载超时，请稍后重试" : err.message;
        if (list) list.innerHTML = `<p class="detail-empty">时间线${msg}</p>`;
      });
  }

  function renderSnapshot(root, data) {
    const metrics = root.querySelector("[data-market-state-metrics]");
    const body = root.querySelector("[data-market-state-body]");
    const explanation = data.research_explanation || {};
    const tone = biasTone(data.bias_label);
    if (metrics) {
      metrics.innerHTML = [
        metricTile("市场", labelMarket(data.market), data.session_date || "暂无", "empty"),
        metricTile("结构", biasLabel(data.bias_label), `风险 ${fmt(data.risk_score)}/10`, tone),
        metricTile("置信度", `${fmt(data.confidence)}%`, data.backend ? `存储 ${data.backend}` : "结构化证据", confidenceTone(data.confidence)),
        metricTile("更新时间", data.updated_at ? new Date(data.updated_at).toLocaleTimeString("zh-CN") : "暂无", sessionLabel(data.session_tag), "empty"),
      ].join("");
    }
    if (!body) return;
    body.innerHTML = `
      <div class="summary-grid">
        <article class="detail-card">
          <h3>绝对结构</h3>
          <ul class="detail-list">
            <li>中位涨跌: ${escapeHtml(fmtPct(data.absolute_view?.median_return_pct))}</li>
            <li>上涨比例: ${escapeHtml(fmtPct(data.absolute_view?.breadth_ratio))}</li>
            <li>基准涨跌: ${escapeHtml(fmtPct(data.absolute_view?.benchmark_return_pct))}</li>
            <li>可用样本: ${escapeHtml(fmt(data.absolute_view?.usable_instrument_count))}/${escapeHtml(fmt(data.absolute_view?.universe_count))}</li>
          </ul>
        </article>
        <article class="detail-card">
          <h3>相对结构</h3>
          <ul class="detail-list">
            <li>基准: ${escapeHtml(data.relative_view?.benchmark || "暂无")}</li>
            <li>相对强弱: ${escapeHtml(fmtPct(data.relative_view?.relative_strength_pct))}</li>
            <li>风格提示: ${escapeHtml(styleLabel(data.relative_view?.style_hint))}</li>
            <li>基准回撤: ${escapeHtml(fmtPct(data.relative_view?.benchmark_drawdown_20d))}</li>
          </ul>
        </article>
        <article class="detail-card">
          <h3>观察解释</h3>
          <p class="detail-paragraph">${escapeHtml(explanation.summary || "研究解释待生成。")}</p>
          <p class="meta-text">${escapeHtml(explanation.guardrail || "research_only")}</p>
        </article>
      </div>
      ${renderGroupSection("关注分组", data.focus_groups || [])}
      ${renderGroupSection("回避分组", data.avoid_groups || [])}
      ${renderEvidence(data.evidence || [])}
      ${renderBlockers(data.blockers || [])}
    `;
  }

  function renderTimeline(root, data) {
    const count = root.querySelector("[data-market-state-count]");
    const list = root.querySelector("[data-market-state-timeline]");
    if (count) count.textContent = `${fmt(data.count || 0)} 个快照`;
    const points = data.points || [];
    if (!list) return;
    if (!points.length) {
      list.innerHTML = '<p class="detail-empty">当前还没有盘中时间线。点击"刷新快照"后会记录一个研究快照。</p>';
      return;
    }
    list.innerHTML = points.map((point) => `
      <article class="insight-card">
        <div class="insight-card-header">
          <span class="badge status-${biasTone(point.bias_label)}">${escapeHtml(biasLabel(point.bias_label))}</span>
          <span class="insight-headline">${escapeHtml(sessionLabel(point.session_tag))} · ${escapeHtml(fmtTime(point.observed_at))}</span>
          <span class="meta-text" style="margin-left:auto;">风险 ${escapeHtml(fmt(point.risk_score))}/10 · 置信 ${escapeHtml(fmt(point.confidence))}%</span>
        </div>
        <div class="tag-row">
          ${(point.focus_groups || []).slice(0, 3).map((item) => `<span class="tag">关注 ${escapeHtml(item.name)}</span>`).join("")}
          ${(point.avoid_groups || []).slice(0, 3).map((item) => `<span class="tag">回避 ${escapeHtml(item.name)}</span>`).join("")}
          ${point.changed_from_previous ? '<span class="badge status-warning">状态变化</span>' : '<span class="badge status-empty">延续</span>'}
        </div>
        <ul class="detail-list">
          ${(point.changes || []).map((item) => `<li>${escapeHtml(item)}</li>`).join("") || '<li class="detail-empty">无显著跳变。</li>'}
          ${(point.evidence || []).slice(0, 3).map((item) => `<li>${escapeHtml(item.label)}: ${escapeHtml(formatEvidenceValue(item.value))} / ${escapeHtml(statusLabel(item.status))}</li>`).join("")}
        </ul>
      </article>
    `).join("");
  }

  function renderGroupSection(title, groups) {
    return `
      <div class="panel-header" style="padding-left:0;padding-right:0;"><h3>${escapeHtml(title)}</h3></div>
      <div class="cards-grid three compact">
        ${groups.length ? groups.slice(0, 6).map((item) => `
          <article class="detail-card">
            <h3>${escapeHtml(item.name)}</h3>
            <p class="detail-paragraph">${escapeHtml(item.reason)}</p>
            <div class="tag-row">${(item.members || []).slice(0, 4).map((symbol) => `<span class="tag">${escapeHtml(symbol)}</span>`).join("")}</div>
          </article>
        `).join("") : '<article class="detail-card"><span class="detail-empty">暂无分组。</span></article>'}
      </div>
    `;
  }

  function renderEvidence(evidence) {
    return `
      <div class="table-wrap">
        <table class="data-table compact-table">
          <thead><tr><th>来源</th><th>证据</th><th>状态</th><th>数值</th><th>解释</th></tr></thead>
          <tbody>
            ${evidence.length ? evidence.map((item) => `
              <tr>
                <td>${escapeHtml(item.source)}</td>
                <td>${escapeHtml(item.label)}</td>
                <td><span class="badge status-${statusTone(item.status)}">${escapeHtml(statusLabel(item.status))}</span></td>
                <td>${escapeHtml(formatEvidenceValue(item.value))}</td>
                <td>${escapeHtml(item.explanation || "")}</td>
              </tr>
            `).join("") : '<tr><td colspan="5" class="table-empty">暂无证据。</td></tr>'}
          </tbody>
        </table>
      </div>
    `;
  }

  function renderBlockers(blockers) {
    if (!blockers.length) return '<p class="meta-text">数据质量：当前没有阻塞项。</p>';
    return `<ul class="detail-list">${blockers.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`;
  }

  function biasLabel(value) {
    return {
      strong: "强结构",
      constructive: "偏建设性",
      mixed: "分化",
      defensive: "防御",
      risk_off: "风险收缩",
    }[value] || displayValue(value);
  }

  function biasTone(value) {
    if (value === "strong" || value === "constructive") return "ok";
    if (value === "defensive" || value === "risk_off") return "blocked";
    return "warning";
  }

  function confidenceTone(value) {
    if (Number(value || 0) >= 70) return "ok";
    if (Number(value || 0) >= 40) return "warning";
    return "blocked";
  }

  function sessionLabel(value) {
    return {
      pre_open: "开盘前",
      open: "开盘",
      morning: "上午",
      afternoon: "午后",
      close: "收盘",
      manual: "手动扫描",
    }[value] || displayValue(value);
  }

  function statusLabel(value) {
    return {
      supportive: "支撑",
      mixed: "分化",
      warning: "预警",
      blocked: "阻塞",
    }[value] || displayValue(value);
  }

  function statusTone(value) {
    if (value === "supportive") return "ok";
    if (value === "warning" || value === "blocked") return "blocked";
    return "warning";
  }

  function styleLabel(value) {
    return {
      broad_strength: "内部广度强于基准",
      index_led_or_weak_internal: "指数领先或内部偏弱",
      balanced: "均衡",
      unknown: "未知",
    }[value] || displayValue(value);
  }

  function formatEvidenceValue(value) {
    if (typeof value === "number") {
      if (Math.abs(value) <= 2) return fmtPct(value);
      return fmt(value);
    }
    return displayValue(value);
  }

  function fmtTime(value) {
    if (!value) return "暂无";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return displayValue(value);
    return date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    });
  }

  global.MarketState = MarketState;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => {
      MarketState.initResearch();
      MarketState.initTimeline();
    });
  } else {
    MarketState.initResearch();
    MarketState.initTimeline();
  }
})(window);

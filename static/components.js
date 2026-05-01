function statusTone(value) {
  if (value === "filled" || value === "approved" || value === "aligned") return "ok";
  if (value === "pending" || value === "warning" || value === "manual" || value === "submitted" || value === "working") return "warning";
  if (value === "rejected" || value === "expired" || value === "not_submitted" || value === "missing") return "blocked";
  return "empty";
}

function catmullRomPath(points, tension = 0.4) {
  if (points.length < 2) return "";
  const path = [`M ${points[0][0].toFixed(2)} ${points[0][1].toFixed(2)}`];
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];
    const cp1x = p1[0] + (p2[0] - p0[0]) * tension / 3;
    const cp1y = p1[1] + (p2[1] - p0[1]) * tension / 3;
    const cp2x = p2[0] - (p3[0] - p1[0]) * tension / 3;
    const cp2y = p2[1] - (p3[1] - p1[1]) * tension / 3;
    path.push(`C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`);
  }
  return path.join(" ");
}

function tableRows(rows, columns) {
  return (rows || []).map((row) => `<tr>${
    columns.map((column) => {
      const value = column.render ? column.render(row) : escapeHtml(row[column.key] ?? "");
      return `<td${column.align ? ` style="text-align:${column.align}"` : ""}>${value}</td>`;
    }).join("")
  }</tr>`).join("");
}

function renderCurve(svgId, points, options = {}) {
  const svg = document.getElementById(svgId);
  if (!svg) return;

  const {
    valueKey = "v",
    stroke = "#c8a24e",
    fill = "rgba(200,162,78,0.12)",
    smooth = false,
    interactive = false,
    overlays = [],
  } = options;

  if (!Array.isArray(points) || !points.length) {
    svg.innerHTML = "";
    svg.onmousemove = null;
    svg.onmouseleave = null;
    return;
  }

  const width = Number(svg.getAttribute("viewBox")?.split(" ")[2]) || 640;
  const height = Number(svg.getAttribute("viewBox")?.split(" ")[3]) || 240;
  const padding = 18;
  const values = points.map((item) => Number(item?.[valueKey])).filter((value) => Number.isFinite(value));
  if (!values.length) {
    svg.innerHTML = "";
    svg.onmousemove = null;
    svg.onmouseleave = null;
    return;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const spread = max - min || 1;
  const step = (width - padding * 2) / Math.max(points.length - 1, 1);
  const coords = points.map((item, index) => {
    const x = padding + step * index;
    const y = height - padding - ((Number(item?.[valueKey] || 0) - min) / spread) * (height - padding * 2);
    return [x, y];
  });

  const linePath = smooth
    ? catmullRomPath(coords, 0.4)
    : coords.map(([x, y], index) => `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`).join(" ");
  const areaPath = `${linePath} L ${coords.at(-1)[0].toFixed(2)} ${(height - padding).toFixed(2)} L ${coords[0][0].toFixed(2)} ${(height - padding).toFixed(2)} Z`;
  const gradientId = `${svgId}-curve-fill`;
  const areaStart = gradientColor(fill, 0.22);
  const areaEnd = gradientColor(fill, 0);
  const overlayMarkup = renderCurveOverlays(points, coords, overlays, height, padding);

  svg.innerHTML = `
    <defs>
      <linearGradient id="${gradientId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${areaStart}"/>
        <stop offset="75%" stop-color="${gradientColor(fill, 0.04)}"/>
        <stop offset="100%" stop-color="${areaEnd}"/>
      </linearGradient>
    </defs>
    <path d="${areaPath}" fill="url(#${gradientId})"></path>
    <path d="${linePath}" fill="none" stroke="${stroke}" stroke-width="${smooth ? 2 : 4}" stroke-linecap="round" stroke-linejoin="round"></path>
    <circle cx="${coords.at(-1)[0].toFixed(2)}" cy="${coords.at(-1)[1].toFixed(2)}" r="4" fill="#ddb85c" stroke="#08090d" stroke-width="2"></circle>
    ${overlayMarkup ? `<g class="curve-overlays">${overlayMarkup}</g>` : ""}
    ${interactive ? `
      <g class="curve-hover-group" style="opacity:0;transition:opacity 0.15s">
        <line class="curve-xhair" x1="0" y1="${padding}" x2="0" y2="${height - padding}" stroke="rgba(200,162,78,0.25)" stroke-width="1" stroke-dasharray="4 3"></line>
        <circle class="curve-hover-dot" cx="0" cy="0" r="4" fill="${stroke}" stroke="#08090d" stroke-width="2"></circle>
      </g>
    ` : ""}
  `;

  if (!interactive) {
    svg.onmousemove = null;
    svg.onmouseleave = null;
    return;
  }

  const tooltip = svg.parentElement?.querySelector(".curve-tooltip") || document.getElementById("curve-tooltip");
  const hoverGroup = svg.querySelector(".curve-hover-group");
  const xhair = svg.querySelector(".curve-xhair");
  const hoverDot = svg.querySelector(".curve-hover-dot");

  svg.onmousemove = (event) => {
    const rect = svg.getBoundingClientRect();
    const svgX = (event.clientX - rect.left) * (width / rect.width);
    let nearestIndex = 0;
    let nearestDistance = Infinity;
    coords.forEach(([cx], index) => {
      const distance = Math.abs(cx - svgX);
      if (distance < nearestDistance) {
        nearestDistance = distance;
        nearestIndex = index;
      }
    });

    const [cx, cy] = coords[nearestIndex];
    xhair?.setAttribute("x1", cx.toFixed(2));
    xhair?.setAttribute("x2", cx.toFixed(2));
    hoverDot?.setAttribute("cx", cx.toFixed(2));
    hoverDot?.setAttribute("cy", cy.toFixed(2));
    if (hoverGroup) hoverGroup.style.opacity = "1";
    if (tooltip) {
      const point = points[nearestIndex] || {};
      const dateText = point.t ? `${String(point.t).split("T")[0]}  ` : "";
      tooltip.textContent = `${dateText}${money(point[valueKey])}`;
      tooltip.removeAttribute("hidden");
    }
  };

  svg.onmouseleave = () => {
    if (hoverGroup) hoverGroup.style.opacity = "0";
    tooltip?.setAttribute("hidden", "");
  };
}

function renderCurveOverlays(points, coords, overlays, height, padding) {
  if (!Array.isArray(overlays) || !overlays.length) return "";
  return overlays
    .filter((item) => item?.impact === "High")
    .map((item) => {
      const eventSource = item.time || item.date;
      if (!eventSource) return "";
      const eventDate = new Date(eventSource).toISOString().split("T")[0];
      const pointIndex = points.findIndex((point) => String(point?.t || "").startsWith(eventDate));
      if (pointIndex < 0) return "";
      const x = coords[pointIndex][0];
      const label = item.event ? String(item.event).split(" ")[0] : "Event";
      return `
        <line x1="${x}" y1="${padding}" x2="${x}" y2="${height - padding}" stroke="rgba(255,255,255,0.15)" stroke-width="1" stroke-dasharray="2 2"></line>
        <text x="${x}" y="${padding - 4}" fill="rgba(255,255,255,0.4)" font-size="8" text-anchor="middle">${escapeHtml(label)}</text>
      `;
    })
    .join("");
}

function gradientColor(color, fallbackAlpha) {
  const rgba = parseColor(color);
  if (!rgba) return color;
  const alpha = rgba.a == null ? fallbackAlpha : (fallbackAlpha === 0 ? 0 : Math.max(rgba.a, fallbackAlpha));
  return `rgba(${rgba.r}, ${rgba.g}, ${rgba.b}, ${alpha})`;
}

function parseColor(color) {
  if (typeof color !== "string") return null;
  const trimmed = color.trim();

  if (trimmed.startsWith("#")) {
    const hex = trimmed.slice(1);
    if (hex.length === 3) {
      return {
        r: Number.parseInt(hex[0] + hex[0], 16),
        g: Number.parseInt(hex[1] + hex[1], 16),
        b: Number.parseInt(hex[2] + hex[2], 16),
        a: null,
      };
    }
    if (hex.length === 6) {
      return {
        r: Number.parseInt(hex.slice(0, 2), 16),
        g: Number.parseInt(hex.slice(2, 4), 16),
        b: Number.parseInt(hex.slice(4, 6), 16),
        a: null,
      };
    }
    return null;
  }

  const rgbaMatch = trimmed.match(/^rgba?\(([^)]+)\)$/i);
  if (!rgbaMatch) return null;
  const parts = rgbaMatch[1].split(",").map((part) => part.trim());
  if (parts.length < 3) return null;
  return {
    r: Number(parts[0]),
    g: Number(parts[1]),
    b: Number(parts[2]),
    a: parts[3] == null ? null : Number(parts[3]),
  };
}

// ── Lightweight Markdown → HTML ─────────────────────────────────────────

function renderMarkdown(text) {
  if (!text) return "";
  var lines = text.split("\n");
  var html = [];
  var inList = false;

  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    var trimmed = line.trim();

    // Blank line
    if (!trimmed) {
      if (inList) { html.push("</ul>"); inList = false; }
      continue;
    }

    // Headings
    if (trimmed.startsWith("### ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push("<h3>" + _inlineMarkdown(trimmed.slice(4)) + "</h3>");
      continue;
    }
    if (trimmed.startsWith("## ")) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push("<h2>" + _inlineMarkdown(trimmed.slice(3)) + "</h2>");
      continue;
    }

    // Unordered list
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      if (!inList) { html.push('<ul style="margin:4px 0;padding-left:18px;">'); inList = true; }
      html.push("<li>" + _inlineMarkdown(trimmed.slice(2)) + "</li>");
      continue;
    }

    // Ordered list
    var olMatch = trimmed.match(/^(\d+)[.)]\s/);
    if (olMatch) {
      if (inList) { html.push("</ul>"); inList = false; }
      html.push("<li style='margin-left:18px;'>" + _inlineMarkdown(trimmed.slice(olMatch[0].length)) + "</li>");
      continue;
    }

    if (inList) { html.push("</ul>"); inList = false; }

    // Color percentage values: +X.X% → green, -X.X% → red
    var colored = _colorPct(_inlineMarkdown(trimmed));
    html.push("<p style='margin:2px 0;'>" + colored + "</p>");
  }

  if (inList) { html.push("</ul>"); }
  return html.join("\n");
}

function _inlineMarkdown(text) {
  return escapeHtml(text)
    .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code style='background:var(--surface-2);padding:1px 4px;border-radius:3px;font-size:0.9em;'>$1</code>");
}

function _colorPct(text) {
  // Color percentage patterns: +X.XX%, -X.XX%
  return text.replace(/([+-]?\d+\.?\d*%)/g, function (match) {
    if (match.startsWith("+")) {
      return '<span style="color:var(--up-color,#e07050);">' + match + '</span>';
    }
    if (match.startsWith("-")) {
      return '<span style="color:var(--down-color,#50b070);">' + match + '</span>';
    }
    return match;
  });
}

// ── ECharts-based awareness visualization ────────────────────────────────

var _chartInstances = {}; // track instances to dispose on re-render

function _chartDom(containerId, heightPx) {
  var el = document.getElementById(containerId);
  if (!el) return null;
  // Dispose previous instance
  if (_chartInstances[containerId]) {
    _chartInstances[containerId].dispose();
  }
  el.style.width = "100%";
  el.style.height = heightPx + "px";
  el.innerHTML = "";
  var chart = echarts.init(el);
  _chartInstances[containerId] = chart;
  return chart;
}

// ── Dark theme palette ──
var _CHART_THEME = {
  bg: "#1a1714",
  text: "#b8b0a0",
  accent: "#c8a24e",
  upColor: "#e07050",
  downColor: "#50b070",
  neutral: "#7f8c8d",
  us: "#4a9eff",
  hk: "#ffb347",
  cn: "#e07050",
};

function _chartTextStyle(size) {
  return { color: _CHART_THEME.text, fontSize: size || 11, fontFamily: "'Noto Sans SC','JetBrains Mono',sans-serif" };
}

// ── 1. Market signal radar chart ─────────────────────────────────────────

function renderMarketRadar(containerId, awareness) {
  var chart = _chartDom(containerId, 320);
  if (!chart) return;
  var views = awareness.market_views || [];
  if (!views.length) { chart.dispose(); return; }

  var marketLabels = { US: "美股", HK: "港股", CN: "A股" };
  var marketColors = { US: _CHART_THEME.us, HK: _CHART_THEME.hk, CN: _CHART_THEME.cn };

  var indicators = [
    { name: "趋势", key: "trend_score", max: 1 },
    { name: "动量", key: "momentum_score", max: 1 },
    { name: "回撤", key: "drawdown_score", max: 1 },
    { name: "波动率", key: "volatility_score", max: 1 },
    { name: "广度", key: "breadth_score", max: 1 },
  ];

  // Extract evidence scores from market views
  var seriesData = [];
  for (var vi = 0; vi < views.length; vi++) {
    var view = views[vi];
    var market = view.market || "";
    var evidence = view.evidence || [];
    // Build score map from evidence: map label → status-derived score
    var scoreMap = {};
    var labelMap = {
      "Trend alignment": "trend_score",
      "Momentum": "momentum_score",
      "Drawdown stress": "drawdown_score",
      "Realized volatility": "volatility_score",
      "Breadth": "breadth_score",
    };
    for (var ei = 0; ei < evidence.length; ei++) {
      var ev = evidence[ei];
      var mappedKey = labelMap[ev.label];
      if (mappedKey) {
        var status = ev.status || "";
        // Convert status to numeric score
        if (status === "supportive") scoreMap[mappedKey] = 0.8;
        else if (status === "mixed") scoreMap[mappedKey] = 0.45;
        else if (status === "warning") scoreMap[mappedKey] = 0.15;
        else scoreMap[mappedKey] = 0.05;
      }
    }

    var data = [];
    for (var ii = 0; ii < indicators.length; ii++) {
      data.push(scoreMap[indicators[ii].key] != null ? scoreMap[indicators[ii].key] : 0);
    }
    seriesData.push({
      name: marketLabels[market] || market,
      type: "radar",
      data: [{ value: data, name: marketLabels[market] || market }],
      symbol: "circle",
      symbolSize: 4,
      lineStyle: { color: marketColors[market] || _CHART_THEME.accent, width: 1.5 },
      areaStyle: { color: marketColors[market] || _CHART_THEME.accent, opacity: 0.08 },
      itemStyle: { color: marketColors[market] || _CHART_THEME.accent },
    });
  }

  chart.setOption({
    backgroundColor: _CHART_THEME.bg,
    tooltip: { trigger: "item" },
    legend: {
      bottom: 0,
      textStyle: _chartTextStyle(11),
      data: seriesData.map(function (s) { return s.name; }),
    },
    radar: {
      center: ["50%", "48%"],
      radius: "65%",
      indicator: indicators,
      axisName: { color: _CHART_THEME.text, fontSize: 10 },
      axisLine: { lineStyle: { color: "rgba(200,162,78,0.2)" } },
      splitLine: { lineStyle: { color: "rgba(200,162,78,0.12)" } },
      splitArea: { areaStyle: { color: ["rgba(200,162,78,0.03)", "rgba(200,162,78,0.06)"] } },
    },
    series: seriesData,
  });
}

// ── 2. Market score bar chart ────────────────────────────────────────────

function renderMarketScores(containerId, awareness) {
  var chart = _chartDom(containerId, 200);
  if (!chart) return;
  var views = awareness.market_views || [];
  if (!views.length) { chart.dispose(); return; }

  var marketLabels = { US: "美股", HK: "港股", CN: "A股" };
  var names = [];
  var scores = [];
  var barColors = [];
  for (var i = 0; i < views.length; i++) {
    var v = views[i];
    names.push(marketLabels[v.market] || v.market || "?");
    scores.push(v.score != null ? v.score : 0);
    var c = v.score >= 0.25 ? _CHART_THEME.upColor : v.score <= -0.15 ? _CHART_THEME.downColor : _CHART_THEME.accent;
    barColors.push(c);
  }

  chart.setOption({
    backgroundColor: _CHART_THEME.bg,
    grid: { left: 50, right: 20, top: 10, bottom: 20 },
    xAxis: {
      type: "value",
      min: -1,
      max: 1,
      axisLine: { lineStyle: { color: _CHART_THEME.text } },
      axisLabel: _chartTextStyle(10),
      splitLine: { lineStyle: { color: "rgba(200,162,78,0.08)" } },
      name: "← 看空       评分       看多 →",
      nameTextStyle: { color: _CHART_THEME.text, fontSize: 9 },
    },
    yAxis: {
      type: "category",
      data: names,
      axisLine: { lineStyle: { color: _CHART_THEME.text } },
      axisLabel: _chartTextStyle(12),
      inverse: true,
    },
    series: [{
      type: "bar",
      data: scores.map(function (s, idx) {
        return {
          value: s,
          itemStyle: {
            color: barColors[idx],
            borderRadius: s >= 0 ? [0, 3, 3, 0] : [3, 0, 0, 3],
          },
        };
      }),
      barWidth: 16,
      label: {
        show: true,
        position: "right",
        formatter: function (p) { return (p.value >= 0 ? "+" : "") + p.value.toFixed(3); },
        color: _CHART_THEME.text,
        fontSize: 11,
      },
    }],
  });
}

// ── 3. Journal 7-day timeline chart ──────────────────────────────────────

function renderJournalTimeline(containerId, plans, summaries) {
  var chart = _chartDom(containerId, 220);
  if (!chart) return;

  var allDates = {};
  plans.forEach(function (p) {
    var d = p.as_of || p.date || "";
    allDates[d] = allDates[d] || {};
    allDates[d].plan = p;
  });
  summaries.forEach(function (s) {
    var d = s.as_of || s.date || "";
    allDates[d] = allDates[d] || {};
    allDates[d].summary = s;
  });
  var sortedDates = Object.keys(allDates).filter(Boolean).sort().slice(-7);

  var planCounts = [];
  var summaryCounts = [];
  var planStatuses = [];
  for (var i = 0; i < sortedDates.length; i++) {
    var d = sortedDates[i];
    var p = allDates[d].plan;
    var s = allDates[d].summary;
    planCounts.push(p ? (p.items || []).length || (p.counts || {}).intent_count || 0 : null);
    summaryCounts.push(s ? (s.metrics || {}).order_count || 0 : null);
    planStatuses.push(p ? p.status : "none");
  }

  chart.setOption({
    backgroundColor: _CHART_THEME.bg,
    tooltip: { trigger: "axis" },
    legend: {
      data: ["计划条目", "订单数"],
      bottom: 0,
      textStyle: _chartTextStyle(10),
    },
    grid: { left: 40, right: 20, top: 10, bottom: 30 },
    xAxis: {
      type: "category",
      data: sortedDates.map(function (d) { return d.slice(5); }),
      axisLabel: _chartTextStyle(10),
      axisLine: { lineStyle: { color: _CHART_THEME.text } },
    },
    yAxis: {
      type: "value",
      minInterval: 1,
      axisLabel: _chartTextStyle(10),
      splitLine: { lineStyle: { color: "rgba(200,162,78,0.08)" } },
    },
    series: [
      {
        name: "计划条目",
        type: "line",
        data: planCounts,
        smooth: true,
        lineStyle: { color: _CHART_THEME.upColor, width: 2 },
        itemStyle: { color: _CHART_THEME.upColor },
        symbol: "circle",
        symbolSize: 6,
      },
      {
        name: "订单数",
        type: "line",
        data: summaryCounts,
        smooth: true,
        lineStyle: { color: _CHART_THEME.cn, width: 2 },
        itemStyle: { color: _CHART_THEME.cn },
        symbol: "diamond",
        symbolSize: 6,
      },
    ],
  });
}

// ── 4. Trade scores bar chart ────────────────────────────────────────────

function renderTradeScoresChart(containerId, scores) {
  var chart = _chartDom(containerId, 200);
  if (!chart) return;
  if (!scores || !scores.length) {
    document.getElementById(containerId).innerHTML = '<p class="detail-empty">暂无评分数据</p>';
    return;
  }

  var symbols = [];
  var overallScores = [];
  for (var i = 0; i < scores.length; i++) {
    symbols.push(scores[i].symbol || "?");
    var s = scores[i].overall_score;
    overallScores.push(typeof s === "number" ? s : 0);
  }

  chart.setOption({
    backgroundColor: _CHART_THEME.bg,
    grid: { left: 45, right: 20, top: 10, bottom: 20 },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "value",
      max: 10,
      axisLabel: _chartTextStyle(10),
      splitLine: { lineStyle: { color: "rgba(200,162,78,0.08)" } },
    },
    yAxis: {
      type: "category",
      data: symbols,
      axisLabel: _chartTextStyle(12),
      inverse: true,
    },
    series: [{
      type: "bar",
      data: overallScores.map(function (s) {
        return {
          value: s,
          itemStyle: {
            color: s >= 7 ? _CHART_THEME.upColor : s >= 5 ? _CHART_THEME.accent : _CHART_THEME.downColor,
            borderRadius: [0, 3, 3, 0],
          },
        };
      }),
      barWidth: 14,
      label: { show: true, position: "right", color: _CHART_THEME.text, fontSize: 11 },
    }],
  });
}

// ── 5. Comprehensive awareness panel (charts + summary cards) ────────────

function renderAwarenessPanel(containerId, awareness) {
  var el = document.getElementById(containerId);
  if (!el) return;
  var views = awareness.market_views || [];
  if (!views.length) {
    el.innerHTML = '<p class="detail-empty">无市场视图数据</p>';
    return;
  }

  // Build HTML with chart containers and summary cards
  var regime = awareness.overall_regime || "";
  var regimeLabel = { bullish: "看涨", neutral: "中性", caution: "谨慎", risk_off: "避险" }[regime] || regime;
  var riskPosture = awareness.risk_posture || "";
  var riskLabel = { build_risk: "加仓", hold_pace: "稳健", reduce_risk: "减仓", pause_new_adds: "暂停" }[riskPosture] || riskPosture;
  var confidence = awareness.confidence || "";
  var confLabel = { high: "高", medium: "中", low: "低" }[confidence] || confidence;
  var ovScore = awareness.overall_score;

  var html = [
    // Summary cards row
    '<div style="display:flex;gap:10px;margin-bottom:12px;flex-wrap:wrap;">',
    '<div class="awareness-metric-card"><div style="font-size:10px;color:var(--text-muted);">综合评分</div><div style="font-size:18px;font-weight:700;color:' + (ovScore >= 0.25 ? 'var(--up-color)' : ovScore <= -0.15 ? 'var(--down-color)' : 'var(--accent)') + ';">' + (ovScore != null ? (ovScore >= 0 ? "+" : "") + ovScore.toFixed(4) : "N/A") + '</div></div>',
    '<div class="awareness-metric-card"><div style="font-size:10px;color:var(--text-muted);">市场体制</div><div style="font-size:18px;font-weight:700;">' + escapeHtml(regimeLabel) + '</div></div>',
    '<div class="awareness-metric-card"><div style="font-size:10px;color:var(--text-muted);">风险姿态</div><div style="font-size:18px;font-weight:700;">' + escapeHtml(riskLabel) + '</div></div>',
    '<div class="awareness-metric-card"><div style="font-size:10px;color:var(--text-muted);">置信度</div><div style="font-size:18px;font-weight:700;">' + escapeHtml(confLabel) + '</div></div>',
    '</div>',
    // Radar chart
    '<div id="' + containerId + '-radar"></div>',
    // Score bar chart
    '<div id="' + containerId + '-scores" style="margin-top:8px;"></div>',
    // Data quality note
  ];

  var dq = awareness.data_quality || {};
  if (dq.degraded || (dq.blockers || []).length) {
    html.push(
      '<div style="margin-top:8px;padding:4px 8px;background:rgba(200,162,78,0.08);border-left:3px solid var(--accent);border-radius:4px;font-size:11px;">',
      '<strong>数据质量:</strong> ' + (dq.status || "degraded"),
      (dq.missing_symbols || []).length ? ' · 缺失:' + dq.missing_symbols.length : '',
      (dq.blockers || []).length ? ' · 阻塞:' + dq.blockers.length : '',
      '</div>'
    );
  }

  el.innerHTML = html.join("");

  // Render sub-charts
  renderMarketRadar(containerId + "-radar", awareness);
  renderMarketScores(containerId + "-scores", awareness);
}

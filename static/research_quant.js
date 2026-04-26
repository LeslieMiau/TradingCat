(function attachResearchQuant(global) {
  'use strict';

  /* ── State ── */
  var state = {
    symbols: ['SPY', 'QQQ'],
    method: 'risk_parity',
    days: 60,
    data: {},
    loading: {},
    errors: {},
    activeSymbol: null,
  };
  var container = null;

  function qs(params) {
    return Object.keys(params).map(function(k) {
      return encodeURIComponent(k) + '=' + encodeURIComponent(params[k]);
    }).join('&');
  }

  function fetchJSON(url, opts) {
    opts = opts || {};
    return fetch(url, {
      method: opts.method || 'GET',
      headers: { 'Accept': 'application/json' },
    }).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }

  /* ── SVG Helpers ── */
  function createSVG(tag, attrs) {
    var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) Object.keys(attrs).forEach(function(k) { el.setAttribute(k, attrs[k]); });
    return el;
  }

  function drawDonut(svgEl, segments) {
    var w = 160, h = 160, cx = w / 2, cy = h / 2, r = 60, ir = 36;
    svgEl.innerHTML = '';
    svgEl.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    var total = segments.reduce(function(s, seg) { return s + seg.value; }, 0) || 1;
    var startAngle = -Math.PI / 2;
    var colors = ['#00e5a0','#00c4d9','#f59e0b','#ff3d71','#8b5cf6','#6b8299'];
    segments.forEach(function(seg, i) {
      var fraction = seg.value / total;
      var endAngle = startAngle + fraction * 2 * Math.PI;
      var largeArc = fraction > 0.5 ? 1 : 0;
      var d = 'M ' + (cx + r * Math.cos(startAngle)).toFixed(1) + ' ' + (cy + r * Math.sin(startAngle)).toFixed(1);
      d += ' A ' + r + ' ' + r + ' 0 ' + largeArc + ' 1 ' + (cx + r * Math.cos(endAngle)).toFixed(1) + ' ' + (cy + r * Math.sin(endAngle)).toFixed(1);
      d += ' L ' + (cx + ir * Math.cos(endAngle)).toFixed(1) + ' ' + (cy + ir * Math.sin(endAngle)).toFixed(1);
      d += ' A ' + ir + ' ' + ir + ' 0 ' + largeArc + ' 0 ' + (cx + ir * Math.cos(startAngle)).toFixed(1) + ' ' + (cy + ir * Math.sin(startAngle)).toFixed(1) + ' Z';
      var path = createSVG('path', { d: d, fill: colors[i % colors.length], opacity: '0.85' });
      svgEl.appendChild(path);
      startAngle = endAngle;
    });
    var txt = createSVG('text', { x: cx, y: cy, 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: '#c8d6e5', 'font-family': 'DM Mono,monospace', 'font-size': '12px' });
    txt.textContent = segments.length + ' 个资产';
    svgEl.appendChild(txt);
  }

  function drawRadar(svgEl, axes, values, maxVal) {
    svgEl.innerHTML = '';
    var w = 200, h = 200, cx = w / 2, cy = h / 2, r = 72;
    svgEl.setAttribute('viewBox', '0 0 ' + w + ' ' + h);
    maxVal = maxVal || 1;
    var n = axes.length;
    if (n < 3) return;
    [0.25, 0.5, 0.75, 1].forEach(function(level) {
      var pts = [];
      for (var i = 0; i < n; i++) {
        var a = -Math.PI / 2 + (2 * Math.PI * i / n);
        pts.push((cx + r * level * Math.cos(a)).toFixed(1) + ',' + (cy + r * level * Math.sin(a)).toFixed(1));
      }
      svgEl.appendChild(createSVG('polygon', { points: pts.join(' '), fill: 'none', stroke: '#1e2d3d', 'stroke-width': '0.5' }));
    });
    for (var i = 0; i < n; i++) {
      var a = -Math.PI / 2 + (2 * Math.PI * i / n);
      svgEl.appendChild(createSVG('line', { x1: cx, y1: cy, x2: cx + r * Math.cos(a), y2: cy + r * Math.sin(a), stroke: '#1e2d3d', 'stroke-width': '0.5' }));
      var lbl = createSVG('text', { x: cx + (r + 14) * Math.cos(a), y: cy + (r + 14) * Math.sin(a), 'text-anchor': 'middle', 'dominant-baseline': 'central', fill: '#6b8299', 'font-family': 'DM Mono,monospace', 'font-size': '8px' });
      lbl.textContent = axes[i];
      svgEl.appendChild(lbl);
    }
    var pts = [];
    for (var i = 0; i < n; i++) {
      var a = -Math.PI / 2 + (2 * Math.PI * i / n);
      var v = Math.min(values[i] / maxVal, 1);
      pts.push((cx + r * v * Math.cos(a)).toFixed(1) + ',' + (cy + r * v * Math.sin(a)).toFixed(1));
    }
    svgEl.appendChild(createSVG('polygon', { points: pts.join(' '), fill: 'rgba(0,229,160,0.15)', stroke: '#00e5a0', 'stroke-width': '1.5' }));
  }

  function drawBarChart(svgEl, items) {
    svgEl.innerHTML = '';
    var h = Math.max(items.length * 20 + 8, 40), barH = 14;
    svgEl.setAttribute('viewBox', '0 0 280 ' + h);
    svgEl.setAttribute('height', h);
    var maxW = Math.max.apply(null, items.map(function(i) { return Math.abs(i.value); })) || 1;
    items.forEach(function(item, i) {
      var y = i * 18 + 4;
      var w = Math.abs(item.value) / maxW * 200;
      var color = item.value >= 0 ? '#00e5a0' : '#ff3d71';
      svgEl.appendChild(createSVG('rect', { x: 40, y: y, width: Math.max(w, 1), height: barH, fill: color, opacity: '0.7', rx: '2' }));
      var lbl = createSVG('text', { x: 38, y: y + barH / 2, 'text-anchor': 'end', 'dominant-baseline': 'central', fill: '#6b8299', 'font-family': 'DM Mono,monospace', 'font-size': '8px' });
      lbl.textContent = item.label;
      svgEl.appendChild(lbl);
      var val = createSVG('text', { x: 44 + Math.max(w, 1), y: y + barH / 2, 'dominant-baseline': 'central', fill: '#c8d6e5', 'font-family': 'DM Mono,monospace', 'font-size': '8px' });
      val.textContent = (item.value >= 0 ? '+' : '') + item.value.toFixed(3);
      svgEl.appendChild(val);
    });
  }

  /* ── Card rendering helpers ── */
  function showSkeleton(id) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="quant-skeleton xl"></div><div class="quant-skeleton"></div><div class="quant-skeleton"></div>';
  }

  function showEmpty(id, msg) {
    var el = document.getElementById(id);
    if (el) el.innerHTML = '<div class="quant-empty">' + (msg || '暂无数据') + '</div>';
  }

  function showError(id, msg, retryFn) {
    var el = document.getElementById(id);
    if (!el) return;
    el.innerHTML = '<div class="quant-error">' + (msg || '加载失败') + '<br><button class="retry-btn" onclick="ResearchQuant.runAll()">重试</button></div>';
  }

  function renderKPI(el, value, label, cls) {
    el.innerHTML = '<span class="value ' + (cls || '') + '">' + value + '</span><span class="label">' + label + '</span>';
  }

  /* ── Data Fetching ── */
  function fetchAll() {
    var s = state.symbols.join(',');
    var calls = {
      features: fetchJSON('/research/features?symbols=' + encodeURIComponent(s) + '&days=' + state.days),
      factors: fetchJSON('/research/factors?symbols=' + encodeURIComponent(s) + '&days=' + state.days),
      optimize: fetchJSON('/research/optimize?symbols=' + encodeURIComponent(s) + '&method=' + state.method, { method: 'POST' }),
      ml: fetchJSON('/research/ml/predict?symbols=' + encodeURIComponent(s)),
      alternative: fetchJSON('/research/alternative?symbols=' + encodeURIComponent(s)),
      briefing: fetchJSON('/research/ai/briefing'),
    };
    state.loading = { features: true, factors: true, optimize: true, ml: true, alternative: true, briefing: true };
    ['features','factors','optimize','ml','alternative','briefing'].forEach(function(k) { showSkeleton('quant-' + k); });
    Object.keys(calls).forEach(function(key) {
      calls[key].then(function(d) {
        state.data[key] = d;
        state.loading[key] = false;
        state.errors[key] = null;
        renderAll(key);
      }).catch(function(err) {
        state.loading[key] = false;
        state.errors[key] = err.message;
        showError('quant-' + key, err.message);
      });
    });
  }

  /* ── Render Functions ── */
  function renderAll(section) {
    if (!section || section === 'features') renderFeatures();
    if (!section || section === 'factors') renderFactors();
    if (!section || section === 'optimize') renderOptimize();
    if (!section || section === 'ml') renderML();
    if (!section || section === 'alternative') renderAlternative();
    if (!section || section === 'briefing') renderBriefing();
  }

  /* ── 1. Feature Engineering ── */
  function renderFeatures() {
    var el = document.getElementById('quant-features');
    var data = state.data.features;
    if (!data || !data.features) { showError('quant-features', '暂无特征数据'); return; }
    var symbols = Object.keys(data.features);
    if (!symbols.length) { showEmpty('quant-features'); return; }
    var sym = state.activeSymbol || symbols[0];
    var feats = data.features[sym] || {};
    var groups = { price: ['close','open','high','low','hl_range','hl_pct','oc_pct'], return: ['return_1d','return_5d','return_10d'], momentum: ['momentum_5d','momentum_10d','sma_5'], volatility: ['return_std_20d','downside_std_20d'], volume: ['avg_volume_20d'], pattern: ['doji','hammer','engulfing'] };
    var radarAxes = ['价格','收益','动量','波动','量能','形态'];
    var radarVals = [0,0,0,0,0,0];
    var gKeys = Object.keys(groups);
    gKeys.forEach(function(gk, gi) {
      var vals = groups[gk].map(function(k) { return feats[k]; }).filter(function(v) { return v !== null && v !== undefined; });
      if (vals.length) radarVals[gi] = Math.min(Math.abs(vals.reduce(function(a,b){return a+b},0) / vals.length), 1);
    });
    var html = '<div style="display:flex;gap:12px;flex-wrap:wrap">';
    html += '<div style="flex-shrink:0"><svg id="quant-radar" class="quant-chart-svg" width="200" height="200"></svg></div>';
    html += '<div style="flex:1;min-width:180px"><table class="quant-table"><thead><tr><th>特征</th><th class="num">数值</th><th></th></tr></thead><tbody>';
    var count = 0;
    Object.keys(feats).forEach(function(k) {
      if (count++ >= 15) return;
      var v = feats[k];
      if (v === null || v === undefined) return;
      var dir = v > 0 ? '<span style="color:#00e5a0">&#9650;</span>' : (v < 0 ? '<span style="color:#ff3d71">&#9660;</span>' : '&#9644;');
      html += '<tr><td style="font-size:10px">' + k + '</td><td class="num">' + (typeof v === 'number' ? v.toFixed(4) : v) + '</td><td>' + dir + '</td></tr>';
    });
    html += '</tbody></table></div></div>';
    // symbol tabs
    html += '<div class="quant-symbol-tabs">';
    symbols.forEach(function(s) {
      html += '<span class="quant-tag ' + (s === sym ? 'is-active' : '') + '" onclick="ResearchQuant.switchSymbol(\'' + s + '\')">' + s + '</span>';
    });
    html += '</div>';
    el.innerHTML = html;
    drawRadar(document.getElementById('quant-radar'), radarAxes, radarVals);
  }

  /* ── 2. Factor Analysis ── */
  function renderFactors() {
    var el = document.getElementById('quant-factors');
    var data = state.data.factors;
    if (!data || !data.factors) { showEmpty('quant-factors', '暂无因子数据'); return; }
    var factors = Object.keys(data.factors);
    if (!factors.length) { showEmpty('quant-factors', '未发现显著因子'); return; }
    var items = factors.map(function(f) { return { label: f, value: data.factors[f].rank_ic || 0 }; });
    items.sort(function(a,b) { return Math.abs(b.value) - Math.abs(a.value); });
    var top = items.slice(0, 10);
    var html = '<div style="display:flex;gap:12px;flex-wrap:wrap">';
    html += '<div style="flex:1;min-width:140px"><svg id="quant-factors-chart" class="quant-chart-svg"></svg></div>';
    html += '<div style="flex:1;min-width:160px"><table class="quant-table"><thead><tr><th>#</th><th>因子</th><th class="num">Rank IC</th></tr></thead><tbody>';
    top.forEach(function(item, i) {
      var c = item.value >= 0 ? '#00e5a0' : '#ff3d71';
      html += '<tr><td>' + (i+1) + '</td><td style="font-size:10px">' + item.label + '</td><td class="num" style="color:' + c + '">' + item.value.toFixed(4) + '</td></tr>';
    });
    html += '</tbody></table></div></div>';
    el.innerHTML = html;
    drawBarChart(document.getElementById('quant-factors-chart'), top);
  }

  /* ── 3. Portfolio Optimization ── */
  function renderOptimize() {
    var el = document.getElementById('quant-optimize');
    var data = state.data.optimize;
    if (!data || !data.weights) { showEmpty('quant-optimize', "请先运行优化"); return; }
    var weights = data.weights;
    var segs = Object.keys(weights).map(function(s) { return { label: s, value: weights[s] }; });
    var kpi = [
      { v: (data.expected_return * 100).toFixed(2) + '%', l: '预期收益' },
      { v: (data.expected_volatility * 100).toFixed(2) + '%', l: '波动率' },
      { v: data.sharpe_ratio.toFixed(2), l: '夏普' },
      { v: data.concentration.toFixed(2), l: '集中度' },
    ];
    var html = '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">';
    html += '<div style="flex-shrink:0"><svg id="quant-donut" class="quant-chart-svg" width="150" height="150"></svg></div>';
    html += '<div style="flex:1;min-width:100px"><div class="quant-kpi-row">';
    kpi.forEach(function(k) {
      html += '<div class="quant-kpi"><span class="value">' + k.v + '</span><span class="label">' + k.l + '</span></div>';
    });
    html += '</div>';
    if (!data.success) html += '<div style="margin-top:8px;font-family:DM Mono,monospace;font-size:9px;color:#f59e0b;padding:4px 8px;background:rgba(245,158,11,0.1);border-radius:4px">备选方案：等权分配（无协方差数据）</div>';
    html += '</div></div>';
    el.innerHTML = html;
    drawDonut(document.getElementById('quant-donut'), segs);
  }

  /* ── 4. ML Pipeline ── */
  function renderML() {
    var el = document.getElementById('quant-ml');
    var data = state.data.ml;
    if (!data) { showEmpty('quant-ml', '模型数据不可用'); return; }
    var models = data.models_available || [];
    if (!models.length) {
      el.innerHTML = '<div class="quant-empty">暂无已训练模型。<br><span style="font-size:9px;color:#6b8299">可通过 POST /research/ml/train 训练</span></div>';
      return;
    }
    var html = '<div style="font-family:DM Mono,monospace;font-size:11px">';
    html += '<div style="margin-bottom:8px;color:#6b8299;font-size:9px;text-transform:uppercase;letter-spacing:0.5px">可用模型</div>';
    models.forEach(function(m) {
      html += '<div style="padding:6px 8px;margin-bottom:4px;background:#0a0e14;border-radius:4px;border:1px solid #1e2d3d;color:#c8d6e5">' + m + '</div>';
    });
    html += '</div>';
    el.innerHTML = html;
  }

  /* ── 5. Alternative Data ── */
  function renderAlternative() {
    var el = document.getElementById('quant-alternative');
    var data = state.data.alternative;
    if (!data) { showEmpty('quant-alternative'); return; }
    var social = data.social_media || {};
    var html = '<div style="font-family:DM Mono,monospace;font-size:10px">';
    html += '<div style="margin-bottom:8px;display:flex;gap:8px;flex-wrap:wrap">';
    Object.keys(social).forEach(function(sym) {
      var m = social[sym];
      html += '<div style="flex:1;min-width:80px;padding:8px;background:#0a0e14;border-radius:4px;border:1px solid #1e2d3d;text-align:center">';
      html += '<div style="color:#c8d6e5;font-size:11px;margin-bottom:4px">' + sym + '</div>';
      html += '<div style="display:flex;gap:2px;justify-content:center">';
      var pw = (m.positive_ratio || 0.33) * 100;
      html += '<span style="color:#00e5a0">&#9608;</span>'.repeat(Math.round(pw / 10));
      html += '</div></div>';
    });
    html += '</div>';
    html += '<div style="display:flex;gap:12px;color:#6b8299">';
    html += '<span>资金流: ' + (data.capital_flow_count || 0) + ' 天</span>';
    html += '<span>宏观事件: ' + (data.macro_event_count || 0) + ' 个</span>';
    html += '</div>';
    html += '<div style="display:flex;gap:8px;margin-top:8px">';
    (data.sources_healthy || []).forEach(function(s) {
      html += '<span style="color:#00e5a0;font-size:8px;padding:2px 6px;border:1px solid #00e5a0;border-radius:3px">&#9679; ' + s + '</span>';
    });
    (data.sources_degraded || []).forEach(function(s) {
      html += '<span style="color:#f59e0b;font-size:8px;padding:2px 6px;border:1px solid #f59e0b;border-radius:3px">&#9679; ' + s + '</span>';
    });
    html += '</div></div>';
    el.innerHTML = html;
  }

  /* ── 6. AI Briefing ── */
  function renderBriefing() {
    var el = document.getElementById('quant-briefing');
    var data = state.data.briefing;
    if (!data) { showEmpty('quant-briefing', 'AI 简报不可用'); return; }
    var content = data.content || '';
    var summary = data.summary || '';
    var html = '<div class="quant-briefing">';
    if (content) {
      html += '<div class="typing">' + content.replace(/\n/g, '<br>') + '</div>';
    } else {
      html += '<div style="color:#6b8299;font-family:DM Mono,monospace;font-size:11px">' + summary + '</div>';
    }
    html += '<div class="quant-briefing-meta">';
    html += '生成时间: ' + (data.generated_at || '') + ' &middot; 模型: ' + (data.model || '') + ' &middot; 置信度: ' + (data.confidence || '');
    html += '</div></div>';
    el.innerHTML = html;
  }

  /* ── 7. Auto Research ── */
  function fetchAutoResearch() {
    showSkeleton('quant-auto');
    fetchJSON('/research/auto-research/run', { method: 'POST' }).then(function(data) {
      renderAutoResearch(data);
    }).catch(function(err) {
      showError('quant-auto', err.message);
    });
  }

  function renderAutoResearch(data) {
    var el = document.getElementById('quant-auto');
    if (!data || !data.report) { showEmpty('quant-auto'); return; }
    var r = data.report;
    var html = '<div style="font-family:DM Mono,monospace;font-size:10px">';
    html += '<div style="display:flex;gap:12px;margin-bottom:8px;padding:8px;background:#0a0e14;border-radius:4px">';
    html += '<span style="color:#6b8299">' + (r.period_start || '') + ' &rarr; ' + (r.period_end || '') + '</span>';
    html += '<span style="color:#c8d6e5">' + (r.summary || '') + '</span>';
    html += '</div>';
    if (r.factor_decay_warnings && r.factor_decay_warnings.length) {
      html += '<div class="quant-report-section"><h4>因子衰减警告</h4>';
      r.factor_decay_warnings.forEach(function(w) {
        html += '<div style="color:#ff3d71;font-size:10px;padding:2px 0">&#9888; ' + w + '</div>';
      });
      html += '</div>';
    }
    if (r.strategy_signals && r.strategy_signals.length) {
      html += '<div class="quant-report-section"><h4>策略信号</h4><table class="quant-table"><thead><tr><th>策略</th><th class="num">夏普</th><th class="num">收益</th><th class="num">最大回撤</th></tr></thead><tbody>';
      r.strategy_signals.forEach(function(s) {
        html += '<tr><td style="font-size:10px">' + s.strategy + '</td><td class="num">' + (s.sharpe || 0).toFixed(2) + '</td><td class="num">' + ((s.total_return || 0) * 100).toFixed(1) + '%</td><td class="num">' + ((s.max_drawdown || 0) * 100).toFixed(1) + '%</td></tr>';
      });
      html += '</tbody></table></div>';
    }
    if (r.candidate_suggestions && r.candidate_suggestions.length) {
      html += '<div class="quant-report-section"><h4>候选建议</h4>';
      r.candidate_suggestions.forEach(function(c) {
        html += '<span class="quant-tag warn" style="margin:2px">' + c + '</span> ';
      });
      html += '</div>';
    }
    html += '<div style="margin-top:8px"><button class="quant-btn" onclick="ResearchQuant.fetchAutoResearch()">重新运行</button></div>';
    html += '</div>';
    el.innerHTML = html;
  }

  /* ── Public API ── */
  global.ResearchQuant = {
    init: function(elId) {
      container = document.getElementById(elId);
      if (!container) return;
      fetchAll();
    },
    runAll: fetchAll,
    fetchAutoResearch: fetchAutoResearch,
    switchSymbol: function(sym) {
      state.activeSymbol = sym;
      renderFeatures();
    },
    state: state,
  };
})(window);

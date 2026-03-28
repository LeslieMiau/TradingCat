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
    stroke = "#5cc4ff",
    fill = "rgba(92,196,255,0.12)",
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
    <circle cx="${coords.at(-1)[0].toFixed(2)}" cy="${coords.at(-1)[1].toFixed(2)}" r="4" fill="#34d399" stroke="#0b0e13" stroke-width="2"></circle>
    ${overlayMarkup ? `<g class="curve-overlays">${overlayMarkup}</g>` : ""}
    ${interactive ? `
      <g class="curve-hover-group" style="opacity:0;transition:opacity 0.15s">
        <line class="curve-xhair" x1="0" y1="${padding}" x2="0" y2="${height - padding}" stroke="rgba(255,255,255,0.18)" stroke-width="1" stroke-dasharray="4 3"></line>
        <circle class="curve-hover-dot" cx="0" cy="0" r="4" fill="${stroke}" stroke="#0b0e13" stroke-width="2"></circle>
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

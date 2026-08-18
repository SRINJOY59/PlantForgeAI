import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

/* ═══════════════════════════════════════════════════════════════════════════
   TENNESSEE EASTMAN PROCESS — Professional P&ID Canvas
   ISA-5.1 compliant equipment shapes · orthogonal piping · live telemetry
   Theme-aware: reads CSS variables at render time
   ═══════════════════════════════════════════════════════════════════════════ */

// ── Layout constants ──────────────────────────────────────────────────────
const W = 1100, H = 720;

// ── Process unit definitions ──────────────────────────────────────────────
const NODES = [
  { id: "FEED-A",  label: "A",       type: "Feed", x: 70,  y: 170 },
  { id: "FEED-D",  label: "D",       type: "Feed", x: 70,  y: 265 },
  { id: "FEED-E",  label: "E",       type: "Feed", x: 70,  y: 360 },
  { id: "FEED-AC", label: "A/C",     type: "Feed", x: 70,  y: 455 },
  {
    id: "REACTOR", label: "REACTOR", type: "Reactor",
    x: 280, y: 290, w: 120, h: 170,
    isa: "T-101",
  },
  {
    id: "CONDENSER", label: "CONDENSER", type: "Condenser",
    x: 520, y: 110, w: 130, h: 80,
    isa: "E-204",
  },
  {
    id: "SEPARATOR", label: "SEPARATOR", type: "Separator",
    x: 790, y: 185, w: 100, h: 155,
    isa: "V-203",
  },
  {
    id: "COMPRESSOR", label: "COMPRESSOR", type: "Compressor",
    x: 790, y: 490, w: 95, h: 95,
    isa: "K-301",
  },
  {
    id: "STRIPPER", label: "STRIPPER", type: "Stripper",
    x: 520, y: 400, w: 95, h: 170,
    isa: "C-220",
  },
  {
    id: "PRODUCT-SPLIT", label: "PRODUCT", type: "Splitter",
    x: 520, y: 640, w: 105, h: 55,
    isa: "V-210",
  },
];

// ── Pipe routing (orthogonal segments) ────────────────────────────────────
const LINKS = [
  { source: "FEED-A",  target: "REACTOR",      label: "S1", stream: "feed" },
  { source: "FEED-D",  target: "REACTOR",      label: "S2", stream: "feed" },
  { source: "FEED-E",  target: "REACTOR",      label: "S3", stream: "feed" },
  { source: "FEED-AC", target: "REACTOR",      label: "S4", stream: "feed" },
  { source: "REACTOR", target: "CONDENSER",    label: "S8: Vapour",     stream: "vapour" },
  { source: "CONDENSER", target: "SEPARATOR",  label: "S8c: Condensate", stream: "liquid" },
  { source: "SEPARATOR", target: "COMPRESSOR", label: "S9: Vapour",     stream: "vapour" },
  { source: "SEPARATOR", target: "STRIPPER",   label: "S10: Liquid",    stream: "liquid" },
  { source: "COMPRESSOR", target: "REACTOR",   label: "S5: Recycle",    stream: "recycle" },
  { source: "STRIPPER", target: "PRODUCT-SPLIT", label: "S11: Product", stream: "product" },
];

// ── Per-node telemetry tags ───────────────────────────────────────────────
const NODE_TAGS = {
  "REACTOR":       ["REACTOR.T", "REACTOR.P", "REACTOR.Level"],
  "CONDENSER":     ["CONDENSER.T", "CONDENSER.P"],
  "SEPARATOR":     ["SEPARATOR.T", "SEPARATOR.Level"],
  "COMPRESSOR":    ["COMPRESSOR.Speed", "COMPRESSOR.Power"],
  "STRIPPER":      ["STRIPPER.T", "STRIPPER.Level"],
  "PRODUCT-SPLIT": ["PRODUCT-SPLIT.xG", "PRODUCT-SPLIT.xH"],
};

const TAG_LABELS = {
  "REACTOR.T": "Temp", "REACTOR.P": "Press", "REACTOR.Level": "Level",
  "CONDENSER.T": "Temp", "CONDENSER.P": "Press",
  "SEPARATOR.T": "Temp", "SEPARATOR.Level": "Level",
  "COMPRESSOR.Speed": "Speed", "COMPRESSOR.Power": "Power",
  "STRIPPER.T": "Temp", "STRIPPER.Level": "Level",
  "PRODUCT-SPLIT.xG": "xG", "PRODUCT-SPLIT.xH": "xH",
};

const TAG_UNITS = {
  "REACTOR.T": "°C", "REACTOR.P": "kPa", "REACTOR.Level": "%",
  "CONDENSER.T": "°C", "CONDENSER.P": "kPa",
  "SEPARATOR.T": "°C", "SEPARATOR.Level": "%",
  "COMPRESSOR.Speed": "rpm", "COMPRESSOR.Power": "kW",
  "STRIPPER.T": "°C", "STRIPPER.Level": "%",
  "PRODUCT-SPLIT.xG": "mol%", "PRODUCT-SPLIT.xH": "mol%",
};

// ── Equipment accent palette (works on any background) ────────────────────
const PALETTE = {
  Reactor:    { border: "#3b82f6", accent: "#3b82f6", tint: "rgba(59,130,246,0.08)",  tintStrong: "rgba(59,130,246,0.15)" },
  Condenser:  { border: "#06b6d4", accent: "#06b6d4", tint: "rgba(6,182,212,0.08)",   tintStrong: "rgba(6,182,212,0.15)" },
  Separator:  { border: "#8b5cf6", accent: "#8b5cf6", tint: "rgba(139,92,246,0.08)",  tintStrong: "rgba(139,92,246,0.15)" },
  Compressor: { border: "#22c55e", accent: "#22c55e", tint: "rgba(34,197,94,0.08)",   tintStrong: "rgba(34,197,94,0.15)" },
  Stripper:   { border: "#f97316", accent: "#f97316", tint: "rgba(249,115,22,0.08)",  tintStrong: "rgba(249,115,22,0.15)" },
  Splitter:   { border: "#eab308", accent: "#ca8a04", tint: "rgba(234,179,8,0.08)",   tintStrong: "rgba(234,179,8,0.15)" },
  Feed:       { border: "#64748b", accent: "#64748b", tint: "rgba(100,116,139,0.06)", tintStrong: "rgba(100,116,139,0.12)" },
};

// Stream colours for pipe differentiation
const STREAM_COLORS = {
  feed:    "#94a3b8",
  vapour:  "#3b82f6",
  liquid:  "#06b6d4",
  recycle: "#8b5cf6",
  product: "#ca8a04",
};

const PIPE_ALARM = "#ef4444";

/* ── Read CSS custom-property values from the document ──────────────── */
function readTheme(el) {
  const s = getComputedStyle(el);
  const v = (name) => s.getPropertyValue(name).trim();
  return {
    bgPanel:   v("--bg-panel")   || "#ffffff",
    bgSurface: v("--bg-surface") || "#f8fafc",
    bgSubtle:  v("--bg-subtle")  || "#f1f5f9",
    border:    v("--border")     || "#e2e8f0",
    borderMd:  v("--border-md")  || "#cbd5e1",
    text:      v("--text")       || "#1e293b",
    textMd:    v("--text-md")    || "#334155",
    muted:     v("--muted")      || "#64748b",
    mutedLt:   v("--muted-lt")   || "#94a3b8",
    brand:     v("--brand")      || "#7a54a0",
  };
}

/* ── Helpers ──────────────────────────────────────────────────────────── */
function getLatestValue(telemetry, tag) {
  const arr = telemetry[tag];
  if (!arr || arr.length === 0) return null;
  return arr[arr.length - 1].y;
}

function formatVal(v, tag) {
  if (v === null || v === undefined) return "—";
  if (tag.includes(".xG") || tag.includes(".xH")) return v.toFixed(1);
  if (tag.includes(".T")) return v.toFixed(1);
  if (tag.includes(".P")) return (v / 1000).toFixed(2);
  if (tag.includes("Level")) return v.toFixed(0);
  if (tag.includes("Speed")) return v.toFixed(1);
  if (tag.includes("Power")) return v.toFixed(0);
  return v.toFixed(2);
}

function nodeById(id) { return NODES.find(n => n.id === id); }

/* ── Orthogonal pipe path builder ─────────────────────────────────────── */
function buildPipePath(src, tgt, link) {
  const sw = src.w || 30, sh = src.h || 20;
  const tw = tgt.w || 30, th = tgt.h || 20;

  if (src.type === "Feed") {
    const sx = src.x + 22, sy = src.y;
    const tx = tgt.x - tw / 2, ty = Math.min(Math.max(src.y, tgt.y - th / 2 + 10), tgt.y + th / 2 - 10);
    const midX = (sx + tx) / 2;
    return `M${sx},${sy} L${midX},${sy} L${midX},${ty} L${tx},${ty}`;
  }
  if (link.source === "REACTOR" && link.target === "CONDENSER") {
    const sx = src.x, sy = src.y - sh / 2;
    const tx = tgt.x - tw / 2, ty = tgt.y;
    return `M${sx},${sy} L${sx},${ty} L${tx},${ty}`;
  }
  if (link.source === "CONDENSER" && link.target === "SEPARATOR") {
    const sx = src.x + sw / 2, sy = src.y;
    const tx = tgt.x, ty = tgt.y - th / 2;
    return `M${sx},${sy} L${tx},${sy} L${tx},${ty}`;
  }
  if (link.source === "SEPARATOR" && link.target === "COMPRESSOR") {
    const sx = src.x, sy = src.y + sh / 2;
    const tx = tgt.x, ty = tgt.y - th / 2;
    const midY = (sy + ty) / 2;
    return `M${sx},${sy} L${sx},${midY} L${tx},${midY} L${tx},${ty}`;
  }
  if (link.source === "SEPARATOR" && link.target === "STRIPPER") {
    const sx = src.x - sw / 2, sy = src.y + 20;
    const tx = tgt.x + tw / 2, ty = tgt.y - 20;
    const midX = (sx + tx) / 2 + 20;
    return `M${sx},${sy} L${midX},${sy} L${midX},${ty} L${tx},${ty}`;
  }
  if (link.source === "COMPRESSOR" && link.target === "REACTOR") {
    const sx = src.x - sw / 2, sy = src.y;
    const tx = tgt.x, ty = tgt.y + th / 2;
    const dropY = Math.max(sy, ty) + 40;
    const leftX = tx - sw / 2 - 40;
    return `M${sx},${sy} L${leftX},${sy} L${leftX},${dropY} L${tx},${dropY} L${tx},${ty}`;
  }
  if (link.source === "STRIPPER" && link.target === "PRODUCT-SPLIT") {
    const sx = src.x, sy = src.y + sh / 2;
    const tx = tgt.x, ty = tgt.y - th / 2;
    return `M${sx},${sy} L${sx},${ty} L${tx},${ty}`;
  }
  const sx = src.x + sw / 2, sy = src.y;
  const tx = tgt.x - (tw || 30) / 2, ty = tgt.y;
  return `M${sx},${sy} L${tx},${sy} L${tx},${ty}`;
}

/* ── Equipment shape drawers ──────────────────────────────────────────── */
function drawReactor(g, node, pal, state, theme) {
  const { w, h } = node;
  const hw = w / 2, hh = h / 2;

  g.append("rect")
    .attr("x", -hw).attr("y", -hh)
    .attr("width", w).attr("height", h)
    .attr("rx", 14).attr("ry", 14)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  // Tinted interior fill
  g.append("rect")
    .attr("x", -hw + 2).attr("y", -hh + 2)
    .attr("width", w - 4).attr("height", h - 4)
    .attr("rx", 12).attr("ry", 12)
    .attr("fill", pal.tint);

  // Hemispherical top cap
  g.append("path")
    .attr("d", `M${-hw},${-hh + 14} Q${-hw},${-hh - 6} 0,${-hh - 10} Q${hw},${-hh - 6} ${hw},${-hh + 14}`)
    .attr("fill", "none")
    .attr("stroke", state.borderColor)
    .attr("stroke-width", 1.2)
    .attr("opacity", 0.5);

  // Agitator shaft
  g.append("line")
    .attr("x1", 0).attr("y1", -hh + 20)
    .attr("x2", 0).attr("y2", hh - 20)
    .attr("stroke", pal.accent).attr("stroke-width", 1.5).attr("opacity", 0.35);

  // Agitator blades
  [-15, 15].forEach(dy => {
    g.append("line")
      .attr("x1", -14).attr("y1", dy)
      .attr("x2", 14).attr("y2", dy)
      .attr("stroke", pal.accent).attr("stroke-width", 2).attr("opacity", 0.4)
      .attr("stroke-linecap", "round");
  });

  // Nozzle stubs
  [[-hw, -20], [-hw, 20], [hw, 0]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx < 0 ? nx - 6 : nx)
      .attr("y", ny - 3)
      .attr("width", 6).attr("height", 6)
      .attr("fill", pal.accent).attr("opacity", 0.4);
  });
}

function drawCondenser(g, node, pal, state, theme) {
  const { w, h } = node;
  const hw = w / 2, hh = h / 2;

  g.append("rect")
    .attr("x", -hw).attr("y", -hh)
    .attr("width", w).attr("height", h)
    .attr("rx", hh).attr("ry", hh)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  g.append("rect")
    .attr("x", -hw + 2).attr("y", -hh + 2)
    .attr("width", w - 4).attr("height", h - 4)
    .attr("rx", hh - 2).attr("ry", hh - 2)
    .attr("fill", pal.tint);

  // Baffles
  const baffleY = [-hh + 14, -4, hh - 14];
  baffleY.forEach(by => {
    g.append("line")
      .attr("x1", -hw + 16).attr("y1", by)
      .attr("x2", hw - 16).attr("y2", by)
      .attr("stroke", pal.accent).attr("stroke-width", 0.8).attr("opacity", 0.3)
      .attr("stroke-dasharray", "4 3");
  });

  // Tube passages
  for (let i = -2; i <= 2; i++) {
    const ty = i * 8;
    g.append("line")
      .attr("x1", -hw + 20).attr("y1", ty)
      .attr("x2", hw - 20).attr("y2", ty)
      .attr("stroke", pal.accent).attr("stroke-width", 0.6).attr("opacity", 0.2);
  }

  // Nozzle stubs
  [[-hw, 0], [hw, 0], [0, -hh], [0, hh]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx === -hw ? nx - 5 : nx === hw ? nx : nx - 3)
      .attr("y", ny === -hh ? ny - 5 : ny === hh ? ny : ny - 3)
      .attr("width", nx === 0 ? 6 : 5)
      .attr("height", ny === 0 ? 6 : 5)
      .attr("fill", pal.accent).attr("opacity", 0.35);
  });
}

function drawSeparator(g, node, pal, state, theme) {
  const { w, h } = node;
  const hw = w / 2, hh = h / 2;

  g.append("rect")
    .attr("x", -hw).attr("y", -hh)
    .attr("width", w).attr("height", h)
    .attr("rx", 10).attr("ry", 10)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  g.append("rect")
    .attr("x", -hw + 2).attr("y", -hh + 2)
    .attr("width", w - 4).attr("height", h - 4)
    .attr("rx", 8).attr("ry", 8)
    .attr("fill", pal.tint);

  // Dish top cap
  g.append("path")
    .attr("d", `M${-hw},${-hh + 10} Q${-hw},${-hh - 4} 0,${-hh - 7} Q${hw},${-hh - 4} ${hw},${-hh + 10}`)
    .attr("fill", "none")
    .attr("stroke", state.borderColor).attr("stroke-width", 1).attr("opacity", 0.4);

  // Liquid level fill
  const levelPct = 0.45;
  const levelY = hh - (h * levelPct);
  g.append("rect")
    .attr("x", -hw + 4).attr("y", levelY)
    .attr("width", w - 8).attr("height", hh - levelY + hh - 8)
    .attr("rx", 6)
    .attr("fill", pal.accent).attr("opacity", 0.1);

  // Level line
  g.append("line")
    .attr("x1", -hw + 4).attr("y1", levelY)
    .attr("x2", hw - 4).attr("y2", levelY)
    .attr("stroke", pal.accent).attr("stroke-width", 1)
    .attr("stroke-dasharray", "5 3").attr("opacity", 0.5);

  // Mesh pad indicator
  g.append("line")
    .attr("x1", -hw + 6).attr("y1", -hh + 24)
    .attr("x2", hw - 6).attr("y2", -hh + 24)
    .attr("stroke", pal.accent).attr("stroke-width", 1.5).attr("opacity", 0.25)
    .attr("stroke-dasharray", "2 2");

  // Nozzles
  [[hw, -hh + 18], [hw, hh - 18], [-hw, 0]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx === hw ? nx : nx - 5)
      .attr("y", ny - 3)
      .attr("width", 5).attr("height", 6)
      .attr("fill", pal.accent).attr("opacity", 0.35);
  });
}

function drawCompressor(g, node, pal, state, theme) {
  const r = node.w / 2;

  g.append("circle")
    .attr("r", r)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  g.append("circle")
    .attr("r", r - 2)
    .attr("fill", pal.tint);

  // Fan blades
  for (let i = 0; i < 6; i++) {
    const angle = (i * 60) * Math.PI / 180;
    const x1 = Math.cos(angle) * 8;
    const y1 = Math.sin(angle) * 8;
    const x2 = Math.cos(angle) * (r - 8);
    const y2 = Math.sin(angle) * (r - 8);
    g.append("line")
      .attr("x1", x1).attr("y1", y1)
      .attr("x2", x2).attr("y2", y2)
      .attr("stroke", pal.accent).attr("stroke-width", 2)
      .attr("stroke-linecap", "round").attr("opacity", 0.4);
  }

  // Central hub
  g.append("circle")
    .attr("r", 7)
    .attr("fill", theme.bgPanel).attr("stroke", pal.accent)
    .attr("stroke-width", 1.5).attr("opacity", 0.6);

  // Nozzle stubs
  [[-r, 0], [r, 0]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx < 0 ? nx - 5 : nx)
      .attr("y", ny - 3)
      .attr("width", 5).attr("height", 6)
      .attr("fill", pal.accent).attr("opacity", 0.35);
  });
}

function drawStripper(g, node, pal, state, theme) {
  const { w, h } = node;
  const hw = w / 2, hh = h / 2;

  g.append("rect")
    .attr("x", -hw).attr("y", -hh)
    .attr("width", w).attr("height", h)
    .attr("rx", 8).attr("ry", 8)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  g.append("rect")
    .attr("x", -hw + 2).attr("y", -hh + 2)
    .attr("width", w - 4).attr("height", h - 4)
    .attr("rx", 6).attr("ry", 6)
    .attr("fill", pal.tint);

  // Dome top
  g.append("path")
    .attr("d", `M${-hw},${-hh + 8} Q${-hw},${-hh - 4} 0,${-hh - 6} Q${hw},${-hh - 4} ${hw},${-hh + 8}`)
    .attr("fill", "none")
    .attr("stroke", state.borderColor).attr("stroke-width", 1).attr("opacity", 0.4);

  // Internal trays
  const trayCount = 6;
  for (let i = 1; i <= trayCount; i++) {
    const ty = -hh + (h / (trayCount + 1)) * i;
    g.append("line")
      .attr("x1", -hw + 6).attr("y1", ty)
      .attr("x2", hw - 6).attr("y2", ty)
      .attr("stroke", pal.accent).attr("stroke-width", 0.9)
      .attr("opacity", 0.25)
      .attr("stroke-dasharray", "3 2");
  }

  // Downcomer hints
  for (let i = 1; i <= trayCount; i++) {
    const ty = -hh + (h / (trayCount + 1)) * i;
    const side = i % 2 === 0 ? hw - 6 : -hw + 6;
    const dx = i % 2 === 0 ? -8 : 8;
    g.append("line")
      .attr("x1", side).attr("y1", ty)
      .attr("x2", side + dx).attr("y2", ty + 10)
      .attr("stroke", pal.accent).attr("stroke-width", 0.7).attr("opacity", 0.2);
  }

  // Nozzles
  [[-hw, -hh + 20], [-hw, hh - 20], [hw, 0]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx === hw ? nx : nx - 5)
      .attr("y", ny - 3)
      .attr("width", 5).attr("height", 6)
      .attr("fill", pal.accent).attr("opacity", 0.35);
  });
}

function drawSplitter(g, node, pal, state, theme) {
  const { w, h } = node;
  const hw = w / 2, hh = h / 2;

  g.append("rect")
    .attr("x", -hw).attr("y", -hh)
    .attr("width", w).attr("height", h)
    .attr("rx", 8).attr("ry", 8)
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);

  g.append("rect")
    .attr("x", -hw + 2).attr("y", -hh + 2)
    .attr("width", w - 4).attr("height", h - 4)
    .attr("rx", 6).attr("ry", 6)
    .attr("fill", pal.tint);

  // Split arrows inside
  g.append("path")
    .attr("d", `M${-10},${-4} L${0},${-4} L${12},${-12} M${0},${-4} L${12},${4}`)
    .attr("fill", "none")
    .attr("stroke", pal.accent).attr("stroke-width", 1.5)
    .attr("stroke-linecap", "round").attr("opacity", 0.4);

  // Nozzle stubs
  [[hw, -8], [hw, 8], [-hw, 0]].forEach(([nx, ny]) => {
    g.append("rect")
      .attr("x", nx === hw ? nx : nx - 5)
      .attr("y", ny - 3)
      .attr("width", 5).attr("height", 6)
      .attr("fill", pal.accent).attr("opacity", 0.35);
  });
}

function drawFeed(g, node, pal, state, theme) {
  g.append("polygon")
    .attr("points", "-18,-14 10,-14 18,0 10,14 -18,14 -10,0")
    .attr("fill", theme.bgPanel)
    .attr("stroke", state.borderColor)
    .attr("stroke-width", state.borderWidth);
}

const SHAPE_DRAWERS = {
  Reactor: drawReactor, Condenser: drawCondenser, Separator: drawSeparator,
  Compressor: drawCompressor, Stripper: drawStripper, Splitter: drawSplitter, Feed: drawFeed,
};

/* ══════════════════════════════════════════════════════════════════════════
   Main Component
   ══════════════════════════════════════════════════════════════════════════ */
export default function TepPnidCanvas({ activeNode, onNodeClick, telemetry, alerts }) {
  const svgRef = useRef(null);
  const containerRef = useRef(null);
  const [hoverId, setHoverId] = useState(null);

  // ── Detect dark/light theme toggle to force re-render ──────────────
  const [isDark, setIsDark] = useState(() =>
    document.documentElement.classList.contains("dark")
  );

  useEffect(() => {
    const observer = new MutationObserver(() => {
      setIsDark(document.documentElement.classList.contains("dark"));
    });
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["class"],
    });
    return () => observer.disconnect();
  }, []);

  const alarmSet = new Set(
    (alerts || []).flatMap(a => {
      const area = a.unit || (a.tag_id ? a.tag_id.split(".")[0] : null);
      return area && NODES.some(n => n.id === area) ? [area] : [];
    })
  );

  useEffect(() => {
    if (!svgRef.current || !containerRef.current) return;
    const el = svgRef.current;

    // ── Read theme colours from CSS variables ─────────────────────────
    const theme = readTheme(containerRef.current);

    d3.select(el).selectAll("*").remove();

    const svg = d3.select(el)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr("width", "100%")
      .attr("height", "100%");

    const defs = svg.append("defs");

    // ── SVG Filters ────────────────────────────────────────────────────
    const glowFilter = defs.append("filter").attr("id", "glow")
      .attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
    glowFilter.append("feGaussianBlur").attr("stdDeviation", "3").attr("result", "blur");
    glowFilter.append("feComposite").attr("in", "SourceGraphic").attr("in2", "blur").attr("operator", "over");

    const alarmGlow = defs.append("filter").attr("id", "alarm-glow")
      .attr("x", "-50%").attr("y", "-50%").attr("width", "200%").attr("height", "200%");
    alarmGlow.append("feGaussianBlur").attr("stdDeviation", "5").attr("result", "blur");
    alarmGlow.append("feComposite").attr("in", "SourceGraphic").attr("in2", "blur").attr("operator", "over");

    const shadowFilter = defs.append("filter").attr("id", "equip-shadow")
      .attr("x", "-20%").attr("y", "-20%").attr("width", "140%").attr("height", "140%");
    shadowFilter.append("feDropShadow")
      .attr("dx", 0).attr("dy", 1).attr("stdDeviation", 3)
      .attr("flood-color", "rgba(0,0,0,0.1)").attr("flood-opacity", 0.15);

    // ── Arrow markers per stream type ──────────────────────────────────
    Object.entries(STREAM_COLORS).forEach(([key, color]) => {
      defs.append("marker")
        .attr("id", `arrow-${key}`)
        .attr("viewBox", "0 -5 10 10")
        .attr("refX", 8).attr("refY", 0)
        .attr("markerWidth", 7).attr("markerHeight", 7)
        .attr("orient", "auto")
        .append("path").attr("d", "M0,-5L10,0L0,5Z").attr("fill", color);
    });
    defs.append("marker")
      .attr("id", "arrow-active")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 8).attr("refY", 0)
      .attr("markerWidth", 7).attr("markerHeight", 7)
      .attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5Z").attr("fill", theme.brand);

    // ── Background grid ────────────────────────────────────────────────
    const grid = svg.append("g").attr("opacity", 0.25);
    for (let x = 0; x < W; x += 30)
      grid.append("line").attr("x1", x).attr("y1", 0).attr("x2", x).attr("y2", H)
        .attr("stroke", theme.border).attr("stroke-width", 0.5);
    for (let y = 0; y < H; y += 30)
      grid.append("line").attr("x1", 0).attr("y1", y).attr("x2", W).attr("y2", y)
        .attr("stroke", theme.border).attr("stroke-width", 0.5);

    // ── Draw pipes ─────────────────────────────────────────────────────
    const pipeGroup = svg.append("g");
    LINKS.forEach(link => {
      const src = nodeById(link.source);
      const tgt = nodeById(link.target);
      if (!src || !tgt) return;

      const isActive = (activeNode === link.source || activeNode === link.target);
      const streamColor = STREAM_COLORS[link.stream] || theme.mutedLt;
      const pathD = buildPipePath(src, tgt, link);

      // Glow underlay for active pipes
      if (isActive) {
        pipeGroup.append("path")
          .attr("d", pathD)
          .attr("fill", "none")
          .attr("stroke", theme.brand)
          .attr("stroke-width", 8)
          .attr("opacity", 0.12)
          .attr("stroke-linecap", "round")
          .attr("stroke-linejoin", "round");
      }

      // Main pipe line
      pipeGroup.append("path")
        .attr("d", pathD)
        .attr("fill", "none")
        .attr("stroke", isActive ? theme.brand : streamColor)
        .attr("stroke-width", isActive ? 3.5 : 2.2)
        .attr("stroke-linecap", "round")
        .attr("stroke-linejoin", "round")
        .attr("marker-end", `url(#arrow-${isActive ? "active" : link.stream})`)
        .attr("opacity", isActive ? 1 : 0.65);

      // Animated flow dashes
      if (isActive) {
        pipeGroup.append("path")
          .attr("d", pathD)
          .attr("fill", "none")
          .attr("stroke", theme.brand)
          .attr("stroke-width", 2)
          .attr("stroke-dasharray", "6 8")
          .attr("stroke-linecap", "round")
          .attr("stroke-linejoin", "round")
          .attr("opacity", 0.6)
          .append("animate")
            .attr("attributeName", "stroke-dashoffset")
            .attr("from", "0").attr("to", "-28")
            .attr("dur", "1.2s")
            .attr("repeatCount", "indefinite");
      }

      // Stream label
      const pathEl = pipeGroup.append("path").attr("d", pathD).attr("fill", "none").attr("stroke", "none");
      const pathNode = pathEl.node();
      if (pathNode) {
        const totalLen = pathNode.getTotalLength();
        const mid = pathNode.getPointAtLength(totalLen * 0.45);
        pathEl.remove();

        const labelText = link.label;
        const lblW = labelText.length * 6.2 + 14;
        pipeGroup.append("rect")
          .attr("x", mid.x - lblW / 2).attr("y", mid.y - 10)
          .attr("width", lblW).attr("height", 18)
          .attr("rx", 3)
          .attr("fill", theme.bgPanel).attr("stroke", theme.border).attr("stroke-width", 0.6)
          .attr("opacity", 0.92);
        pipeGroup.append("text")
          .attr("x", mid.x).attr("y", mid.y + 3)
          .attr("text-anchor", "middle")
          .attr("font-size", "9px")
          .attr("fill", isActive ? theme.brand : theme.muted)
          .attr("font-family", "'JetBrains Mono', monospace")
          .attr("font-weight", "500")
          .text(labelText);
      } else {
        pathEl.remove();
      }
    });

    // ── Draw equipment nodes ───────────────────────────────────────────
    NODES.forEach(node => {
      const pal = PALETTE[node.type] || PALETTE.Feed;
      const isActive = activeNode === node.id;
      const hasAlarm = alarmSet.has(node.id);
      const isFeed = node.type === "Feed";

      const borderColor = hasAlarm ? PIPE_ALARM : isActive ? pal.border : theme.borderMd;
      const borderWidth = isActive || hasAlarm ? 2.8 : 1.6;
      const state = { borderColor, borderWidth, isActive, hasAlarm };

      const g = svg.append("g")
        .attr("transform", `translate(${node.x},${node.y})`)
        .attr("cursor", "pointer")
        .attr("filter", isActive ? "url(#glow)" : hasAlarm ? "url(#alarm-glow)" : "url(#equip-shadow)")
        .on("click", () => onNodeClick(node.id))
        .on("mouseenter", () => setHoverId(node.id))
        .on("mouseleave", () => setHoverId(null));

      // Alarm glow ring
      if (hasAlarm) {
        const glowR = Math.max(node.w || 30, node.h || 30) / 2 + 18;
        g.append("circle")
          .attr("r", glowR)
          .attr("fill", "none")
          .attr("stroke", PIPE_ALARM)
          .attr("stroke-width", 3)
          .attr("opacity", 0.5)
          .append("animate")
            .attr("attributeName", "opacity")
            .attr("values", "0.5;0.15;0.5")
            .attr("dur", "1.5s")
            .attr("repeatCount", "indefinite");
      }

      // Active selection ring
      if (isActive && !hasAlarm) {
        const glowR = Math.max(node.w || 30, node.h || 30) / 2 + 14;
        g.append("circle")
          .attr("r", glowR)
          .attr("fill", "none")
          .attr("stroke", pal.border)
          .attr("stroke-width", 1.5)
          .attr("stroke-dasharray", "4 3")
          .attr("opacity", 0.45)
          .append("animate")
            .attr("attributeName", "stroke-dashoffset")
            .attr("from", "0").attr("to", "-14")
            .attr("dur", "2s")
            .attr("repeatCount", "indefinite");
      }

      // Draw the equipment shape
      const drawer = SHAPE_DRAWERS[node.type];
      if (drawer) drawer(g, node, pal, state, theme);

      // ── Labels ───────────────────────────────────────────────────────
      if (!isFeed) {
        const hw = (node.w || 80) / 2;
        const hh = (node.h || 80) / 2;

        // Equipment name label (above)
        g.append("text")
          .attr("y", -hh - 18)
          .attr("text-anchor", "middle")
          .attr("font-size", "11px")
          .attr("font-weight", "700")
          .attr("fill", isActive ? pal.accent : theme.textMd)
          .attr("font-family", "'JetBrains Mono', monospace")
          .attr("letter-spacing", "0.5px")
          .text(node.label);

        // ISA tag badge (below)
        if (node.isa) {
          const badgeY = hh + 8;
          const badgeW = node.isa.length * 8.5 + 16;
          g.append("rect")
            .attr("x", -badgeW / 2).attr("y", badgeY)
            .attr("width", badgeW).attr("height", 20)
            .attr("rx", 4)
            .attr("fill", theme.bgSubtle)
            .attr("stroke", pal.border)
            .attr("stroke-width", 1)
            .attr("opacity", 0.9);
          g.append("text")
            .attr("y", badgeY + 14)
            .attr("text-anchor", "middle")
            .attr("font-size", "10.5px")
            .attr("font-weight", "700")
            .attr("fill", pal.accent)
            .attr("font-family", "'JetBrains Mono', monospace")
            .text(node.isa);
        }

        // ── Telemetry readout card (ONLY on active node) ────────────────
        const nodeTags = NODE_TAGS[node.id];
        if (nodeTags && isActive) {
          const cardX = hw + 20;
          const cardY = -((nodeTags.length * 22 + 12) / 2);
          const cardW = 110;
          const cardH = nodeTags.length * 22 + 12;

          g.append("rect")
            .attr("x", cardX).attr("y", cardY)
            .attr("width", cardW).attr("height", cardH)
            .attr("rx", 6)
            .attr("fill", theme.bgPanel)
            .attr("stroke", pal.border)
            .attr("stroke-width", 1.5)
            .attr("opacity", 0.97);

          // Connector line
          g.append("line")
            .attr("x1", hw + 2).attr("y1", 0)
            .attr("x2", cardX).attr("y2", 0)
            .attr("stroke", pal.border)
            .attr("stroke-width", 1)
            .attr("stroke-dasharray", "3 3")
            .attr("opacity", 0.6);

          nodeTags.forEach((tag, i) => {
            const val = getLatestValue(telemetry, tag);
            const formatted = formatVal(val, tag);
            const unit = TAG_UNITS[tag] || "";
            const ty = cardY + 18 + i * 22;

            g.append("text")
              .attr("x", cardX + 8).attr("y", ty)
              .attr("font-size", "10px")
              .attr("fill", theme.muted)
              .attr("font-family", "'JetBrains Mono', monospace")
              .text(TAG_LABELS[tag]);

            g.append("text")
              .attr("x", cardX + cardW - 8).attr("y", ty)
              .attr("text-anchor", "end")
              .attr("font-size", "11px")
              .attr("font-weight", "600")
              .attr("fill", val === null ? theme.mutedLt : pal.accent)
              .attr("font-family", "'JetBrains Mono', monospace")
              .text(`${formatted} ${unit}`);
          });
        }
      } else {
        // Feed label — short, beside the chevron
        g.append("text")
          .attr("x", 24)
          .attr("text-anchor", "start")
          .attr("dy", "0.35em")
          .attr("font-size", "11px")
          .attr("fill", isActive ? pal.accent : theme.textMd)
          .attr("font-family", "'JetBrains Mono', monospace")
          .attr("font-weight", "600")
          .text(node.label);
      }
    });

    // ── Title block (top-left corner to avoid overlap) ──────────────────
    svg.append("text")
      .attr("x", 18).attr("y", 24)
      .attr("font-size", "14px")
      .attr("font-weight", "700")
      .attr("fill", theme.textMd)
      .attr("font-family", "'JetBrains Mono', monospace")
      .attr("letter-spacing", "1.5px")
      .text("TENNESSEE EASTMAN PROCESS");
    svg.append("text")
      .attr("x", 18).attr("y", 40)
      .attr("font-size", "9px")
      .attr("fill", theme.muted)
      .attr("font-family", "'JetBrains Mono', monospace")
      .text("P&ID OVERVIEW · DWG-TEP-001 REV.B");

    // ── Stream legend (bottom right) ───────────────────────────────────
    const legX = W - 170, legY = H - 110;
    const legItems = [
      { color: STREAM_COLORS.feed,    label: "Feed Stream" },
      { color: STREAM_COLORS.vapour,  label: "Vapour Line" },
      { color: STREAM_COLORS.liquid,  label: "Liquid Line" },
      { color: STREAM_COLORS.recycle, label: "Recycle Loop" },
      { color: STREAM_COLORS.product, label: "Product Stream" },
    ];

    svg.append("rect")
      .attr("x", legX - 10).attr("y", legY - 14)
      .attr("width", 165).attr("height", legItems.length * 19 + 14)
      .attr("rx", 6)
      .attr("fill", theme.bgPanel)
      .attr("stroke", theme.border)
      .attr("stroke-width", 1)
      .attr("opacity", 0.95);

    legItems.forEach(({ color, label }, i) => {
      const ly = legY + i * 19;
      svg.append("line")
        .attr("x1", legX).attr("y1", ly)
        .attr("x2", legX + 22).attr("y2", ly)
        .attr("stroke", color).attr("stroke-width", 2.5)
        .attr("stroke-linecap", "round");
      svg.append("text")
        .attr("x", legX + 28).attr("y", ly + 3)
        .attr("font-size", "9.5px")
        .attr("fill", theme.muted)
        .attr("font-family", "'JetBrains Mono', monospace")
        .attr("dominant-baseline", "middle")
        .text(label);
    });

  }, [activeNode, telemetry, alerts, hoverId, isDark]);

  return (
    <div ref={containerRef} className="relative w-full h-full" style={{ minHeight: 600 }}>
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ background: "var(--bg-panel)", borderRadius: 10, border: "1px solid var(--border)" }}
      />
      {/* Overlay legend */}
      <div
        className="absolute bottom-3 left-3 flex flex-col gap-1.5 text-xs px-3 py-2 rounded-lg"
        style={{ color: "var(--muted)", background: "var(--bg-panel)", border: "1px solid var(--border)", opacity: 0.92 }}
      >
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full border-2 inline-block" style={{ borderColor: "var(--brand)" }} />
          <span style={{ fontSize: 11 }}>Selected unit</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="h-3 w-3 rounded-full border-2 inline-block" style={{ borderColor: "#ef4444" }} />
          <span style={{ fontSize: 11 }}>Active alarm</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: "#8b5cf6" }} />
          <span style={{ fontSize: 11 }}>Recycle loop</span>
        </div>
      </div>
    </div>
  );
}

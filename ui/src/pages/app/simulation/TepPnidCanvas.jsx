import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

// TEP process unit node definitions with P&ID positions
// Each node carries its simulation area id, display label, ISA-5.1 field tags,
// and associated instruments for P&ID badge rendering.
const NODES = [
  { id: "FEED-A",       label: "Feed A",      type: "Feed",       x: 60,  y: 60,  isa: null },
  { id: "FEED-D",       label: "Feed D",      type: "Feed",       x: 60,  y: 160, isa: null },
  { id: "FEED-E",       label: "Feed E",      type: "Feed",       x: 60,  y: 260, isa: null },
  { id: "FEED-AC",      label: "Feed A/B/C",  type: "Feed",       x: 60,  y: 360, isa: null },
  {
    id: "REACTOR",
    label: "REACTOR",
    type: "Reactor",
    x: 240, y: 200,
    isa: "T-101",                     // Feed tank / reactor vessel tag
    equip: ["T-101", "P-101A", "P-101B"],
    instruments: ["PI-102", "FT-103"],
  },
  {
    id: "CONDENSER",
    label: "CONDENSER",
    type: "Condenser",
    x: 420, y: 120,
    isa: "E-204",                     // Feed heater / condenser exchanger
    equip: ["E-204"],
    instruments: ["TI-205"],
  },
  {
    id: "SEPARATOR",
    label: "SEPARATOR",
    type: "Separator",
    x: 580, y: 200,
    isa: "V-203",                     // Separator vessel
    equip: ["V-203"],
    instruments: ["PSV-204"],
  },
  {
    id: "COMPRESSOR",
    label: "COMPRESSOR",
    type: "Compressor",
    x: 580, y: 340,
    isa: "K-301",                     // Vapour compressor
    equip: ["K-301"],
    instruments: [],
  },
  {
    id: "STRIPPER",
    label: "STRIPPER",
    type: "Stripper",
    x: 420, y: 340,
    isa: "C-220",                     // Stripper / absorber column
    equip: ["C-220"],
    instruments: ["PDI-221"],
  },
  {
    id: "PRODUCT-SPLIT",
    label: "PRODUCT",
    type: "Splitter",
    x: 580, y: 470,
    isa: "V-210",                     // Product splitter / KO drum
    equip: ["V-210"],
    instruments: ["LT-212"],
  },
];

const LINKS = [
  { source: "FEED-A",       target: "REACTOR",       label: "S1: A" },
  { source: "FEED-D",       target: "REACTOR",       label: "S2: D" },
  { source: "FEED-E",       target: "REACTOR",       label: "S3: E" },
  { source: "FEED-AC",      target: "REACTOR",       label: "S4: A/B/C" },
  { source: "REACTOR",      target: "CONDENSER",     label: "S8: Vap" },
  { source: "CONDENSER",    target: "SEPARATOR",     label: "S8c" },
  { source: "SEPARATOR",    target: "COMPRESSOR",    label: "S9: Vap" },
  { source: "SEPARATOR",    target: "STRIPPER",      label: "S10: Liq" },
  { source: "COMPRESSOR",   target: "REACTOR",       label: "S5: Recycle", curved: true },
  { source: "STRIPPER",     target: "PRODUCT-SPLIT", label: "S11: Prod" },
];

// Per-node live telemetry tags
const NODE_TAGS = {
  "REACTOR":       ["REACTOR.T", "REACTOR.P", "REACTOR.Level"],
  "CONDENSER":     ["CONDENSER.T", "CONDENSER.P"],
  "SEPARATOR":     ["SEPARATOR.T", "SEPARATOR.Level"],
  "COMPRESSOR":    ["COMPRESSOR.Speed", "COMPRESSOR.Power"],
  "STRIPPER":      ["STRIPPER.T", "STRIPPER.Level"],
  "PRODUCT-SPLIT": ["PRODUCT-SPLIT.xG", "PRODUCT-SPLIT.xH"],
};

const TAG_LABELS = {
  "REACTOR.T": "T", "REACTOR.P": "P", "REACTOR.Level": "Lvl",
  "CONDENSER.T": "T", "CONDENSER.P": "P",
  "SEPARATOR.T": "T", "SEPARATOR.Level": "Lvl",
  "COMPRESSOR.Speed": "Spd", "COMPRESSOR.Power": "kW",
  "STRIPPER.T": "T", "STRIPPER.Level": "Lvl",
  "PRODUCT-SPLIT.xG": "xG", "PRODUCT-SPLIT.xH": "xH",
};

const NODE_COLORS = {
  Reactor:   { fill: "#1e3a5f", stroke: "#3b82f6", icon: "⚗" },
  Condenser: { fill: "#1a3040", stroke: "#06b6d4", icon: "❄" },
  Separator: { fill: "#1e2d40", stroke: "#8b5cf6", icon: "⬡" },
  Compressor:{ fill: "#1e2a1e", stroke: "#22c55e", icon: "⟳" },
  Stripper:  { fill: "#2a1e1e", stroke: "#f97316", icon: "♨" },
  Splitter:  { fill: "#2a2a1e", stroke: "#eab308", icon: "⑂" },
  Feed:      { fill: "#1e1e2a", stroke: "#64748b", icon: "→" },
};

// ISA badge colour — darker tint of the unit colour, distinct from telemetry pills
const ISA_BADGE = { fill: "#0c1220", stroke: "#334155", text: "#94a3b8" };
const INST_BADGE = { fill: "#0f1a10", stroke: "#1f4d2a", text: "#4ade80" };

function getLatestValue(telemetry, tag) {
  const arr = telemetry[tag];
  if (!arr || arr.length === 0) return null;
  return arr[arr.length - 1].y;
}

function formatVal(v, tag) {
  if (v === null || v === undefined) return "—";
  if (tag.includes(".xG") || tag.includes(".xH")) return `${v.toFixed(1)}%`;
  if (tag.includes(".T")) return `${v.toFixed(1)}°`;
  if (tag.includes(".P")) return `${(v / 1000).toFixed(2)}MPa`;
  if (tag.includes("Level")) return `${v.toFixed(0)}%`;
  if (tag.includes("Speed")) return `${v.toFixed(1)}%`;
  if (tag.includes("Power")) return `${v.toFixed(0)}`;
  return v.toFixed(2);
}

export default function TepPnidCanvas({ activeNode, onNodeClick, telemetry, alerts }) {
  const svgRef = useRef(null);
  const [hoverId, setHoverId] = useState(null);

  // Compute alarm state per unit area
  const alarmSet = new Set(
    alerts.flatMap(a => {
      const area = a.tag_id ? a.tag_id.split(".")[0] : a.unit;
      return area ? [area] : [];
    })
  );

  useEffect(() => {
    if (!svgRef.current) return;
    const el = svgRef.current;
    const W = 740, H = 580;

    d3.select(el).selectAll("*").remove();

    const svg = d3.select(el)
      .attr("viewBox", `0 0 ${W} ${H}`)
      .attr("width", "100%")
      .attr("height", "100%");

    const defs = svg.append("defs");

    // Arrow marker
    defs.append("marker")
      .attr("id", "arrowTEP")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 22).attr("refY", 0)
      .attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#475569");

    defs.append("marker")
      .attr("id", "arrowActive")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 22).attr("refY", 0)
      .attr("markerWidth", 5).attr("markerHeight", 5)
      .attr("orient", "auto")
      .append("path").attr("d", "M0,-5L10,0L0,5").attr("fill", "#3b82f6");

    // Grid lines for P&ID aesthetic
    const grid = svg.append("g").attr("opacity", 0.05);
    for (let x = 0; x < W; x += 40)
      grid.append("line").attr("x1", x).attr("y1", 0).attr("x2", x).attr("y2", H)
        .attr("stroke", "#94a3b8").attr("stroke-width", 0.5);
    for (let y = 0; y < H; y += 40)
      grid.append("line").attr("x1", 0).attr("y1", y).attr("x2", W).attr("y2", y)
        .attr("stroke", "#94a3b8").attr("stroke-width", 0.5);

    // ── Draw pipeline links ──────────────────────────────────────────────────
    LINKS.forEach(link => {
      const src = NODES.find(n => n.id === link.source);
      const tgt = NODES.find(n => n.id === link.target);
      if (!src || !tgt) return;

      const isActive = (activeNode === link.source || activeNode === link.target);

      let d;
      if (link.curved) {
        d = `M${src.x},${src.y + 20} C${src.x},${src.y + 110} ${tgt.x},${tgt.y + 90} ${tgt.x + 10},${tgt.y + 20}`;
      } else {
        d = `M${src.x},${src.y} L${tgt.x},${tgt.y}`;
      }

      svg.append("path")
        .attr("d", d)
        .attr("fill", "none")
        .attr("stroke", isActive ? "#3b82f6" : "#334155")
        .attr("stroke-width", isActive ? 2.5 : 1.5)
        .attr("marker-end", `url(#${isActive ? "arrowActive" : "arrowTEP"})`)
        .attr("stroke-dasharray", link.curved ? "6 3" : "none")
        .attr("opacity", 0.8);

      // Stream label on midpoint
      const mx = (src.x + tgt.x) / 2;
      const my = (src.y + tgt.y) / 2;
      svg.append("text")
        .attr("x", mx).attr("y", my - 6)
        .attr("text-anchor", "middle")
        .attr("font-size", "8px")
        .attr("fill", "#64748b")
        .attr("font-family", "monospace")
        .text(link.label);
    });

    // ── Draw nodes ───────────────────────────────────────────────────────────
    NODES.forEach(node => {
      const colors = NODE_COLORS[node.type] || NODE_COLORS.Feed;
      const isActive = activeNode === node.id;
      const hasAlarm = alarmSet.has(node.id);
      const isHover = hoverId === node.id;

      const g = svg.append("g")
        .attr("transform", `translate(${node.x},${node.y})`)
        .attr("cursor", "pointer")
        .on("click", () => onNodeClick(node.id))
        .on("mouseenter", () => setHoverId(node.id))
        .on("mouseleave", () => setHoverId(null));

      const isFeed = node.type === "Feed";
      const rx = isFeed ? 14 : 38;
      const ry = isFeed ? 10 : 26;

      // Alarm glow ring
      if (hasAlarm) {
        g.append("ellipse")
          .attr("rx", rx + 9).attr("ry", ry + 9)
          .attr("fill", "none")
          .attr("stroke", "#ef4444")
          .attr("stroke-width", 2)
          .attr("opacity", 0.45);
      }

      // Active selection glow ring
      if (isActive) {
        g.append("ellipse")
          .attr("rx", rx + 7).attr("ry", ry + 7)
          .attr("fill", "none")
          .attr("stroke", colors.stroke)
          .attr("stroke-width", 2)
          .attr("opacity", 0.55);
      }

      // Main unit body
      g.append("ellipse")
        .attr("rx", rx).attr("ry", ry)
        .attr("fill", isHover ? d3.color(colors.fill).brighter(0.4) : colors.fill)
        .attr("stroke", hasAlarm ? "#ef4444" : isActive ? colors.stroke : "#475569")
        .attr("stroke-width", isActive || hasAlarm ? 2 : 1);

      if (!isFeed) {
        // Unit icon
        g.append("text")
          .attr("y", -6)
          .attr("text-anchor", "middle")
          .attr("font-size", "14px")
          .text(colors.icon);

        // Unit area label
        g.append("text")
          .attr("y", 10)
          .attr("text-anchor", "middle")
          .attr("font-size", "7.5px")
          .attr("font-weight", "600")
          .attr("fill", isActive ? colors.stroke : "#94a3b8")
          .attr("font-family", "monospace")
          .text(node.label);

        // ── ISA equipment tag badge (primary vessel/machine tag) ──────────
        if (node.isa) {
          const badgeY = ry + 8;
          g.append("rect")
            .attr("x", -24).attr("y", badgeY)
            .attr("width", 48).attr("height", 13)
            .attr("rx", 3)
            .attr("fill", ISA_BADGE.fill)
            .attr("stroke", colors.stroke)
            .attr("stroke-width", 0.8)
            .attr("opacity", 0.9);

          g.append("text")
            .attr("y", badgeY + 9)
            .attr("text-anchor", "middle")
            .attr("font-size", "7.5px")
            .attr("font-weight", "700")
            .attr("fill", colors.stroke)
            .attr("font-family", "monospace")
            .text(node.isa);
        }

        // ── Additional equipment tags (pumps, valves on the same unit) ────
        if (node.equip && node.equip.length > 1) {
          const extraTags = node.equip.slice(1); // skip the first — already shown as ISA badge
          extraTags.forEach((tag, i) => {
            const ex = -28 + i * 58;
            const ey = ry + 24;
            g.append("rect")
              .attr("x", ex).attr("y", ey)
              .attr("width", 52).attr("height", 12)
              .attr("rx", 2)
              .attr("fill", "#0a1525")
              .attr("stroke", "#334155")
              .attr("stroke-width", 0.6);
            g.append("text")
              .attr("x", ex + 26).attr("y", ey + 8.5)
              .attr("text-anchor", "middle")
              .attr("font-size", "6.5px")
              .attr("fill", "#7dd3fc")
              .attr("font-family", "monospace")
              .text(tag);
          });
        }

        // ── Instrument / controller badges ────────────────────────────────
        if (node.instruments && node.instruments.length > 0) {
          node.instruments.forEach((inst, i) => {
            const hasExtra = node.equip && node.equip.length > 1;
            const baseY = ry + (hasExtra ? 40 : 25);
            const ix = -26 + i * 55;
            const iy = baseY;

            g.append("rect")
              .attr("x", ix).attr("y", iy)
              .attr("width", 48).attr("height", 12)
              .attr("rx", 2)
              .attr("fill", INST_BADGE.fill)
              .attr("stroke", INST_BADGE.stroke)
              .attr("stroke-width", 0.7);
            g.append("text")
              .attr("x", ix + 24).attr("y", iy + 8.5)
              .attr("text-anchor", "middle")
              .attr("font-size", "6.5px")
              .attr("fill", INST_BADGE.text)
              .attr("font-family", "monospace")
              .text(inst);
          });
        }

        // ── Live telemetry value pills ────────────────────────────────────
        const nodeTags = NODE_TAGS[node.id];
        if (nodeTags) {
          const hasExtra = node.equip && node.equip.length > 1;
          const hasInst  = node.instruments && node.instruments.length > 0;
          const baseTelY = ry + 8
            + (node.isa ? 16 : 0)
            + (hasExtra ? 15 : 0)
            + (hasInst  ? 15 : 0);

          nodeTags.forEach((tag, i) => {
            const val = getLatestValue(telemetry, tag);
            const yOff = baseTelY + i * 14;
            const formatted = formatVal(val, tag);

            g.append("rect")
              .attr("x", -30).attr("y", yOff - 9)
              .attr("width", 60).attr("height", 12)
              .attr("rx", 3)
              .attr("fill", "#0f172a")
              .attr("stroke", "#1e293b")
              .attr("stroke-width", 1);

            g.append("text")
              .attr("y", yOff)
              .attr("text-anchor", "middle")
              .attr("font-size", "7px")
              .attr("fill", val === null ? "#4b5563" : "#a5f3fc")
              .attr("font-family", "monospace")
              .text(`${TAG_LABELS[tag]}: ${formatted}`);
          });
        }

      } else {
        // Feed node label only
        g.append("text")
          .attr("text-anchor", "middle")
          .attr("dy", "0.35em")
          .attr("font-size", "7.5px")
          .attr("fill", "#64748b")
          .attr("font-family", "monospace")
          .text(node.label);
      }
    });

    // ── P&ID title ────────────────────────────────────────────────────────────
    svg.append("text")
      .attr("x", W / 2).attr("y", 18)
      .attr("text-anchor", "middle")
      .attr("font-size", "10px")
      .attr("fill", "#475569")
      .attr("font-family", "monospace")
      .attr("font-weight", "600")
      .text("TENNESSEE EASTMAN PROCESS — P&ID OVERVIEW");

    // ── ISA tag colour legend ─────────────────────────────────────────────────
    const legX = W - 148, legY = H - 72;
    svg.append("rect")
      .attr("x", legX - 6).attr("y", legY - 14)
      .attr("width", 148).attr("height", 68)
      .attr("rx", 4)
      .attr("fill", "#0c1220").attr("stroke", "#1e293b").attr("stroke-width", 1)
      .attr("opacity", 0.85);

    const legItems = [
      { color: "#3b82f6", label: "Primary vessel/machine tag" },
      { color: "#7dd3fc", label: "Associated equipment tag" },
      { color: "#4ade80", label: "Instrument / controller" },
      { color: "#a5f3fc", label: "Live process variable" },
    ];
    legItems.forEach(({ color, label }, i) => {
      const ly = legY + i * 13;
      svg.append("rect")
        .attr("x", legX).attr("y", ly - 6)
        .attr("width", 8).attr("height", 8)
        .attr("rx", 1).attr("fill", color);
      svg.append("text")
        .attr("x", legX + 12).attr("y", ly + 0.5)
        .attr("font-size", "7px")
        .attr("fill", "#94a3b8")
        .attr("font-family", "monospace")
        .attr("dominant-baseline", "middle")
        .text(label);
    });

  }, [activeNode, telemetry, alerts, hoverId]);

  return (
    <div className="relative w-full h-full" style={{ minHeight: 520 }}>
      <svg
        ref={svgRef}
        className="w-full h-full"
        style={{ background: "var(--bg-panel)", borderRadius: 8 }}
      />
      {/* Legend */}
      <div
        className="absolute bottom-3 left-3 flex flex-col gap-1 text-xs"
        style={{ color: "var(--muted)" }}
      >
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full border-2 inline-block" style={{ borderColor: "#3b82f6" }} />
          Selected unit
        </div>
        <div className="flex items-center gap-1.5">
          <span className="h-3 w-3 rounded-full border-2 inline-block" style={{ borderColor: "#ef4444" }} />
          Active alarm
        </div>
        <div className="flex items-center gap-1.5">
          <span className="inline-block w-5 border-t-2 border-dashed" style={{ borderColor: "#3b82f6" }} />
          Recycle loop
        </div>
      </div>
    </div>
  );
}

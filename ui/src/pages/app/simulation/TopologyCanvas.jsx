import React, { useEffect, useRef, useState } from "react";
import * as d3 from "d3";

export default function TopologyCanvas({ activeNode, onNodeClick, telemetry, alerts }) {
  const svgRef = useRef(null);
  const [hoverData, setHoverData] = useState(null);

  // Set up nodes
  const nodes = [
    { id: "FEED",      label: "FEED",       type: "Line",        x: 50,  y: 150 },
    { id: "CSTR-101",  label: "CSTR-101",   type: "CSTR",        x: 160, y: 150 },
    { id: "CSTR-102A", label: "CSTR-102A",  type: "CSTR",        x: 280, y: 70  },
    { id: "CSTR-102B", label: "CSTR-102B",  type: "CSTR",        x: 280, y: 230 },
    { id: "CSTR-104",  label: "CSTR-104",   type: "CSTR",        x: 400, y: 150 },
    { id: "COLUMN-1",  label: "COLUMN-1",   type: "Column",      x: 520, y: 150 },
  ];

  // Set up links
  const links = [
    // CONNECTED_TO
    { source: "FEED",      target: "CSTR-101",  relation: "CONNECTED_TO" },
    { source: "CSTR-101",  target: "CSTR-102A", relation: "CONNECTED_TO" },
    { source: "CSTR-101",  target: "CSTR-102B", relation: "CONNECTED_TO" },
    { source: "CSTR-102A", target: "CSTR-104",  relation: "CONNECTED_TO" },
    { source: "CSTR-102B", target: "CSTR-104",  relation: "CONNECTED_TO" },
    // SHARES_HEADER
    { source: "CSTR-102A", target: "CSTR-102B", relation: "SHARES_HEADER" },
    // FEEDS
    { source: "CSTR-104",  target: "COLUMN-1",  relation: "FEEDS" },
  ];

  useEffect(() => {
    if (!svgRef.current) return;
    const el = svgRef.current;
    const width = el.clientWidth || 600;
    const height = el.clientHeight || 300;

    d3.select(el).selectAll("*").remove();

    const svg = d3.select(el)
      .attr("width", "100%")
      .attr("height", "100%")
      .attr("viewBox", `0 0 ${width} ${height}`);

    const defs = svg.append("defs");

    // Standard arrow marker
    defs.append("marker")
      .attr("id", "arrow")
      .attr("viewBox", "0 -5 10 10")
      .attr("refX", 18)
      .attr("refY", 0)
      .attr("markerWidth", 6)
      .attr("markerHeight", 6)
      .attr("orient", "auto")
      .append("path")
      .attr("d", "M0,-5L10,0L0,5")
      .attr("fill", "var(--border-md)");

    // Draw links
    svg.selectAll(".link")
      .data(links)
      .enter()
      .append("path")
      .attr("class", "link")
      .attr("d", d => {
        const sourceNode = nodes.find(n => n.id === d.source);
        const targetNode = nodes.find(n => n.id === d.target);
        if (d.relation === "SHARES_HEADER") {
          // Curved path for sharing header to differentiate it
          const dx = targetNode.x - sourceNode.x;
          const dy = targetNode.y - sourceNode.y;
          const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
          return `M${sourceNode.x},${sourceNode.y}A${dr},${dr} 0 0,1 ${targetNode.x},${targetNode.y}`;
        }
        return `M${sourceNode.x},${sourceNode.y}L${targetNode.x},${targetNode.y}`;
      })
      .attr("fill", "none")
      .attr("stroke", d => {
        if (d.relation === "SHARES_HEADER") return "#f59e0b"; // Amber utility link
        if (d.relation === "FEEDS") return "#7c3aed";         // Purple cross-unit feed link
        return "var(--border-md)";
      })
      .attr("stroke-width", d => (d.relation === "SHARES_HEADER" ? 1.5 : 2))
      .attr("stroke-dasharray", d => {
        if (d.relation === "SHARES_HEADER") return "4,4";      // Dashed for headers
        if (d.relation === "FEEDS") return "2,2";              // Dotted for cross-unit
        return "none";
      })
      .attr("marker-end", d => (d.relation === "SHARES_HEADER" ? "none" : "url(#arrow)"));

    // Draw nodes
    const nodeGroups = svg.selectAll(".node")
      .data(nodes)
      .enter()
      .append("g")
      .attr("class", "node")
      .attr("transform", d => `translate(${d.x}, ${d.y})`)
      .style("cursor", "pointer")
      .on("click", (event, d) => onNodeClick(d.id))
      .on("mouseover", (event, d) => {
        setHoverData({
          id: d.id,
          label: d.label,
          type: d.type,
          x: event.clientX,
          y: event.clientY
        });
      })
      .on("mousemove", (event) => {
        setHoverData(prev => prev ? { ...prev, x: event.clientX, y: event.clientY } : null);
      })
      .on("mouseout", () => {
        setHoverData(null);
      });

    // Render node shapes: rect for vessels/columns, circle for feed line
    nodeGroups.each(function(d) {
      const g = d3.select(this);

      // Check if this node has an active alert
      const hasAlert = alerts && alerts.some(a => a.equipment === d.id);
      const isActive = activeNode === d.id;

      if (d.type === "Line") {
        g.append("circle")
          .attr("r", 20)
          .attr("fill", isActive ? "var(--blue-lt)" : "var(--bg-panel)")
          .attr("stroke", "var(--border-md)")
          .attr("stroke-width", isActive ? 2.5 : 1.5);
      } else {
        const rect = g.append("rect")
          .attr("x", -40)
          .attr("y", -20)
          .attr("width", 80)
          .attr("height", 40)
          .attr("rx", 8)
          .attr("fill", () => {
            if (isActive) return "rgba(37,99,235,0.08)";
            return "var(--bg-panel)";
          })
          .attr("stroke", () => {
            if (hasAlert) return "#dc2626"; // Alert Red
            if (isActive) return "var(--blue)";
            return "var(--border-md)";
          })
          .attr("stroke-width", isActive ? 2.5 : 1.5);

        // Alert pulse animation
        if (hasAlert) {
          rect.append("animate")
            .attr("attributeName", "stroke-width")
            .attr("values", "1.5;3.5;1.5")
            .attr("dur", "1.2s")
            .attr("repeatCount", "indefinite");
          rect.append("animate")
            .attr("attributeName", "stroke")
            .attr("values", "#dc2626;#fca5a5;#dc2626")
            .attr("dur", "1.2s")
            .attr("repeatCount", "indefinite");
        }
      }

      // Primary tags and formatters for live overlay
      const primaryTags = {
        "CSTR-101": { tag: "CSTR-101.T", format: (v) => `${v.toFixed(1)} K` },
        "CSTR-102A": { tag: "CSTR-102A.T", format: (v) => `${v.toFixed(1)} K` },
        "CSTR-102B": { tag: "CSTR-102B.T", format: (v) => `${v.toFixed(1)} K` },
        "CSTR-104": { tag: "CSTR-104.T", format: (v) => `${v.toFixed(1)} K` },
        "COLUMN-1": { tag: "COLUMN-1.DISTILLATE.x", format: (v) => `xD: ${v.toFixed(3)}` }
      };

      const getLatestValue = (tag_id) => {
        const points = telemetry[tag_id];
        if (!points || points.length === 0) return null;
        return points[points.length - 1].y;
      };

      const spec = primaryTags[d.id];

      // Add labels
      g.append("text")
        .attr("text-anchor", "middle")
        .attr("dy", spec ? -2 : 4)
        .attr("font-size", "10px")
        .attr("font-weight", "600")
        .attr("fill", "var(--text-md)")
        .text(d.label);

      if (spec) {
        const val = getLatestValue(spec.tag);
        if (val !== null) {
          g.append("text")
            .attr("text-anchor", "middle")
            .attr("dy", 10)
            .attr("font-size", "8px")
            .attr("font-weight", "500")
            .attr("fill", hasAlert ? "#dc2626" : "var(--muted)")
            .text(spec.format(val));
        }
      }
    });

  }, [activeNode, alerts, telemetry]);

  const renderTooltip = (data) => {
    if (data.id === "FEED") return null;

    const getLatestValue = (tag_id) => {
      const points = telemetry[tag_id];
      if (!points || points.length === 0) return null;
      return points[points.length - 1].y;
    };

    let rows = [];
    if (data.type === "CSTR" || data.id.startsWith("CSTR")) {
      const t = getLatestValue(`${data.id}.T`);
      const ca = getLatestValue(`${data.id}.Ca`);
      const tc = getLatestValue(`${data.id}.Tc`);
      const valve = getLatestValue(`${data.id}.CoolantValve`);
      
      rows = [
        { label: "Reactor Temp (T)", value: t !== null ? `${t.toFixed(1)} K` : "Offline", color: "#10b981" },
        { label: "Reactant Conc (Ca)", value: ca !== null ? `${ca.toFixed(3)} mol/L` : "Offline", color: "#3b82f6" },
        { label: "Coolant Temp (Tc)", value: tc !== null ? `${tc.toFixed(1)} K` : "Offline", color: "#94a3b8" },
        { label: "Coolant Valve", value: valve !== null ? `${valve.toFixed(1)} %` : "Offline", color: "#f59e0b" },
      ];
    } else if (data.id === "COLUMN-1") {
      const xd = getLatestValue("COLUMN-1.DISTILLATE.x");
      const xb = getLatestValue("COLUMN-1.BOTTOMS.x");
      const rebT = getLatestValue("COLUMN-1.REBOILER.T");
      const flood = getLatestValue("COLUMN-1.FLOODING");

      rows = [
        { label: "Distillate Comp (xD)", value: xd !== null ? xd.toFixed(3) : "Offline", color: "#3b82f6" },
        { label: "Bottoms Comp (xB)", value: xb !== null ? xb.toFixed(3) : "Offline", color: "#ef4444" },
        { label: "Reboiler Temp (T)", value: rebT !== null ? `${rebT.toFixed(1)} K` : "Offline", color: "#10b981" },
        { label: "Flooding Index", value: flood !== null ? flood.toFixed(2) : "Offline", color: "#f59e0b" },
      ];
    }

    if (rows.length === 0) return null;

    return (
      <div
        className="fixed z-50 rounded-lg p-2.5 shadow-lg border text-[11px] space-y-1.5 pointer-events-none"
        style={{
          left: `${data.x + 15}px`,
          top: `${data.y + 15}px`,
          background: "rgba(15, 23, 42, 0.95)",
          color: "#fff",
          borderColor: "rgba(255,255,255,0.15)",
        }}
      >
        <div className="font-bold text-[9px] uppercase tracking-wider text-slate-400 border-b pb-1 mb-1 border-slate-700">
          {data.label} Faceplate
        </div>
        <div className="space-y-1">
          {rows.map((row, idx) => (
            <div key={idx} className="flex items-center justify-between gap-4">
              <span className="text-slate-300 font-medium text-[10px]">{row.label}</span>
              <span className="font-bold font-mono text-[10px]" style={{ color: row.color }}>
                {row.value}
              </span>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <div className="flex h-full flex-col relative">
      <div className="mb-2 flex items-center justify-between text-xs" style={{ color: "var(--muted)" }}>
        <span className="font-semibold">Demo Process Train Flow</span>
        <div className="flex items-center gap-4">
          <span className="flex items-center gap-1"><span className="h-1 w-4 border-t-2 border-slate-300" /> Process</span>
          <span className="flex items-center gap-1"><span className="h-1 w-4 border-t-2 border-dashed border-amber-500" /> Utility Header</span>
          <span className="flex items-center gap-1"><span className="h-1 w-4 border-t-2 border-dotted border-violet-500" /> Cross-Unit Link</span>
        </div>
      </div>
      <div className="flex-1 rounded-xl p-2" style={{ background: "rgba(248,250,252,0.6)", border: "1px solid var(--border)" }}>
        <svg ref={svgRef} className="h-full w-full" style={{ minHeight: "260px" }} />
      </div>
      {hoverData && renderTooltip(hoverData)}
    </div>
  );
}

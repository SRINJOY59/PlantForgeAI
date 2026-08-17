/**
 * EventHistorian.jsx — Horizontal alarm timeline (swimlane chart).
 *
 * Renders a compact timeline where each tag with at least one alert gets its
 * own swimlane. Alert segments are drawn as horizontal bars coloured by
 * severity (red = critical, amber = warning). Acknowledged alerts get a
 * hatched/dimmed style.
 *
 * Uses D3 for layout and SVG for rendering.
 */
import React, { useEffect, useRef } from "react";
import * as d3 from "d3";

const LANE_HEIGHT = 28;
const MARGIN = { top: 12, right: 16, bottom: 30, left: 160 };

function colorForSeverity(severity, acked) {
  if (acked) return "#94a3b8";
  return severity === "critical" ? "#dc2626" : "#f59e0b";
}

function opacityForSeverity(severity, acked) {
  return acked ? 0.35 : severity === "critical" ? 0.8 : 0.65;
}

function parseTimestamp(ts) {
  if (!ts) return Date.now();
  if (typeof ts === "number") {
    return ts < 1e11 ? ts * 1000 : ts;
  }
  const num = Number(ts);
  if (!isNaN(num) && num > 0) {
    return num < 1e11 ? num * 1000 : num;
  }
  const parsed = new Date(ts).getTime();
  return isNaN(parsed) ? Date.now() : parsed;
}

export default function EventHistorian({ alerts = [], acknowledgedIds = new Set() }) {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current) return;

    // Group alerts by tag_id
    const byTag = d3.group(alerts, d => d.tag_id || d.unit || d.equipment || "Unknown");
    const tags = Array.from(byTag.keys());

    if (tags.length === 0) {
      d3.select(svgRef.current).selectAll("*").remove();
      return;
    }

    // Time domain: from oldest alert to now
    const allTimes = alerts.map(a => parseTimestamp(a.timestamp));
    const tMin = allTimes.length ? Math.min(...allTimes) : Date.now() - 60000;
    const tNow = Date.now();

    const width = svgRef.current.parentElement?.clientWidth || 600;
    const height = MARGIN.top + tags.length * LANE_HEIGHT + MARGIN.bottom;

    const svg = d3.select(svgRef.current)
      .attr("width", width)
      .attr("height", height);

    svg.selectAll("*").remove();

    const xScale = d3.scaleTime()
      .domain([new Date(Math.min(tMin - 2000, tNow - 10000)), new Date(tNow)])
      .range([MARGIN.left, width - MARGIN.right]);

    const xAxis = d3.axisBottom(xScale)
      .ticks(6)
      .tickFormat(d => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));

    svg.append("g")
      .attr("transform", `translate(0,${height - MARGIN.bottom})`)
      .call(xAxis)
      .selectAll("text")
      .attr("font-size", "9px")
      .attr("fill", "var(--muted, #64748b)");

    svg.selectAll(".x-grid-line")
      .data(xScale.ticks(6))
      .enter()
      .append("line")
      .attr("class", "x-grid-line")
      .attr("x1", d => xScale(d))
      .attr("x2", d => xScale(d))
      .attr("y1", MARGIN.top)
      .attr("y2", height - MARGIN.bottom)
      .attr("stroke", "var(--border, #e2e8f0)")
      .attr("stroke-width", 1)
      .attr("stroke-dasharray", "2,2")
      .attr("opacity", 0.6);

    // Draw swimlanes
    tags.forEach((tag, laneIdx) => {
      const y = MARGIN.top + laneIdx * LANE_HEIGHT;

      // Lane background
      svg.append("rect")
        .attr("x", MARGIN.left)
        .attr("y", y)
        .attr("width", width - MARGIN.left - MARGIN.right)
        .attr("height", LANE_HEIGHT - 2)
        .attr("fill", laneIdx % 2 === 0 ? "rgba(148,163,184,0.06)" : "transparent")
        .attr("rx", 3);

      // Lane label
      svg.append("text")
        .attr("x", MARGIN.left - 8)
        .attr("y", y + LANE_HEIGHT / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", "end")
        .attr("font-size", "10px")
        .attr("font-weight", "600")
        .attr("fill", "var(--text-md, #475569)")
        .attr("font-family", "monospace")
        .text(tag.length > 20 ? tag.slice(0, 20) + "…" : tag);

      // Draw alert bars
      const tagAlerts = byTag.get(tag) || [];
      tagAlerts.forEach(alert => {
        const ts = parseTimestamp(alert.timestamp);
        const acked = acknowledgedIds.has(alert.id);
        const barWidth = Math.max(8, (tNow - ts) * 0.002);
        const startX = xScale(new Date(ts));
        const clampedWidth = Math.max(6, Math.min(barWidth, (width - MARGIN.right) - startX));

        svg.append("rect")
          .attr("x", startX)
          .attr("y", y + 4)
          .attr("width", clampedWidth)
          .attr("height", LANE_HEIGHT - 8)
          .attr("fill", colorForSeverity(alert.severity, acked))
          .attr("opacity", opacityForSeverity(alert.severity, acked))
          .attr("rx", 3)
          .append("title")
          .text(`${alert.message || alert.tag_id}\nTime: ${new Date(ts).toLocaleTimeString()}\nSeverity: ${alert.severity || "warning"}`);

        // Severity indicator dot at start
        svg.append("circle")
          .attr("cx", startX)
          .attr("cy", y + LANE_HEIGHT / 2)
          .attr("r", 3.5)
          .attr("fill", colorForSeverity(alert.severity, acked))
          .attr("opacity", acked ? 0.4 : 1);
      });
    });

    // "Now" cursor line
    svg.append("line")
      .attr("x1", xScale(new Date(tNow)))
      .attr("x2", xScale(new Date(tNow)))
      .attr("y1", MARGIN.top)
      .attr("y2", height - MARGIN.bottom)
      .attr("stroke", "var(--brand, #7a54a0)")
      .attr("stroke-width", 1.5)
      .attr("stroke-dasharray", "4,3");

  }, [alerts, acknowledgedIds]);

  return (
    <div
      className="rounded-xl p-4 shadow-sm overflow-x-auto"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between border-b pb-2 mb-3" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-md)" }}>
          Event Historian — Alarm Timeline
        </h3>
        <span className="text-[10px] text-slate-400">
          Red = critical · Amber = warning · Grey = acknowledged
        </span>
      </div>
      {alerts.length === 0 ? (
        <div className="flex h-20 items-center justify-center text-xs text-slate-400">
          No alarms in history. All tags within limits.
        </div>
      ) : (
        <svg ref={svgRef} className="w-full" />
      )}
    </div>
  );
}

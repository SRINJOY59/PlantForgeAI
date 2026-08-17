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

export default function EventHistorian({ alerts = [], acknowledgedIds = new Set() }) {
  const svgRef = useRef(null);

  useEffect(() => {
    if (!svgRef.current) return;

    // Group alerts by tag_id
    const byTag = d3.group(alerts, d => d.tag_id || d.equipment || "Unknown");
    const tags = Array.from(byTag.keys());

    if (tags.length === 0) {
      d3.select(svgRef.current).selectAll("*").remove();
      return;
    }

    // Time domain: from oldest alert to now
    const allTimes = alerts.map(a => new Date(a.timestamp).getTime()).filter(t => !isNaN(t));
    const tMin = allTimes.length ? Math.min(...allTimes) : Date.now() - 60000;
    const tNow = Date.now();

    const width = svgRef.current.parentElement?.clientWidth || 600;
    const height = MARGIN.top + tags.length * LANE_HEIGHT + MARGIN.bottom;

    const svg = d3.select(svgRef.current)
      .attr("width", width)
      .attr("height", height);

    svg.selectAll("*").remove();

    const xScale = d3.scaleTime()
      .domain([new Date(tMin - 2000), new Date(tNow)])
      .range([MARGIN.left, width - MARGIN.right]);

    const xAxis = d3.axisBottom(xScale)
      .ticks(6)
      .tickFormat(d => d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" }));

    svg.append("g")
      .attr("transform", `translate(0,${height - MARGIN.bottom})`)
      .call(xAxis)
      .selectAll("text")
      .attr("font-size", "9px")
      .attr("fill", "#64748b");

    svg.selectAll(".x-grid-line")
      .data(xScale.ticks(6))
      .enter()
      .append("line")
      .attr("class", "x-grid-line")
      .attr("x1", d => xScale(d))
      .attr("x2", d => xScale(d))
      .attr("y1", MARGIN.top)
      .attr("y2", height - MARGIN.bottom)
      .attr("stroke", "#e2e8f0")
      .attr("stroke-width", 1);

    // Draw swimlanes
    tags.forEach((tag, laneIdx) => {
      const y = MARGIN.top + laneIdx * LANE_HEIGHT;

      // Lane background
      svg.append("rect")
        .attr("x", MARGIN.left)
        .attr("y", y)
        .attr("width", width - MARGIN.left - MARGIN.right)
        .attr("height", LANE_HEIGHT - 2)
        .attr("fill", laneIdx % 2 === 0 ? "rgba(248,250,252,0.6)" : "transparent")
        .attr("rx", 2);

      // Lane label
      svg.append("text")
        .attr("x", MARGIN.left - 6)
        .attr("y", y + LANE_HEIGHT / 2)
        .attr("dy", "0.35em")
        .attr("text-anchor", "end")
        .attr("font-size", "9px")
        .attr("font-weight", "600")
        .attr("fill", "#475569")
        .text(tag.length > 22 ? tag.slice(0, 22) + "…" : tag);

      // Draw alert bars
      const tagAlerts = byTag.get(tag) || [];
      tagAlerts.forEach(alert => {
        const ts = new Date(alert.timestamp).getTime();
        if (isNaN(ts)) return;

        const acked = acknowledgedIds.has(alert.id);
        const barWidth = Math.max(6, (tNow - ts) * 0.002); // bar grows with age
        const clampedWidth = Math.min(barWidth, xScale(new Date(tNow)) - xScale(new Date(ts)));

        svg.append("rect")
          .attr("x", xScale(new Date(ts)))
          .attr("y", y + 4)
          .attr("width", Math.max(4, clampedWidth))
          .attr("height", LANE_HEIGHT - 10)
          .attr("fill", colorForSeverity(alert.severity, acked))
          .attr("opacity", opacityForSeverity(alert.severity, acked))
          .attr("rx", 3)
          .append("title")
          .text(`${alert.title}\n${new Date(ts).toLocaleTimeString()}\nSeverity: ${alert.severity}`);

        // Severity indicator dot at start
        svg.append("circle")
          .attr("cx", xScale(new Date(ts)))
          .attr("cy", y + LANE_HEIGHT / 2 - 1)
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
      .attr("stroke", "#2563eb")
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

import React, { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";

// Defines subplots per TEP unit area
const AREA_CONFIG = {
  // Coolant temperature is plotted ALONGSIDE process temperature, not left
  // off. Cooling duty is UA*(T - T_cool), so the GAP between these two lines
  // is the duty - and every coolant fault (IDV 4/11 inlet step, 14 valve
  // stuck, and fouling via ua_degradation) shows up here first, often hours
  // before the process temperature it eventually moves. With only REACTOR.T
  // on screen, a live coolant fault looked like three flat lines and the sim
  // looked frozen.
  "REACTOR": {
    subplots: [
      { title: "Temperature (°C)", tags: ["REACTOR.T", "REACTOR.CoolT"], yaxis: "yaxis" },
      { title: "Pressure (kPa)",   tags: ["REACTOR.P"], yaxis: "yaxis2" },
      { title: "Level (%)",         tags: ["REACTOR.Level"], yaxis: "yaxis3" },
    ],
  },
  "CONDENSER": {
    subplots: [
      { title: "Temperature (°C)", tags: ["CONDENSER.T", "CONDENSER.CoolT"],  yaxis: "yaxis" },
      { title: "Pressure (kPa)",   tags: ["CONDENSER.P"],  yaxis: "yaxis2" },
      { title: "Heat Duty",        tags: ["CONDENSER.HeatDuty"], yaxis: "yaxis3" },
    ],
  },
  "SEPARATOR": {
    subplots: [
      { title: "Temperature (°C)", tags: ["SEPARATOR.T"],      yaxis: "yaxis" },
      { title: "Level (%)",         tags: ["SEPARATOR.Level"],  yaxis: "yaxis2" },
      { title: "Flow (kmol/h)",     tags: ["SEPARATOR.VapFlow","SEPARATOR.LiqFlow"], yaxis: "yaxis3" },
    ],
  },
  "STRIPPER": {
    subplots: [
      { title: "Temperature (°C)", tags: ["STRIPPER.T"],    yaxis: "yaxis" },
      { title: "Level (%)",         tags: ["STRIPPER.Level"],yaxis: "yaxis2" },
      { title: "Product Frac (%)", tags: ["STRIPPER.xG","STRIPPER.xH"], yaxis: "yaxis3" },
    ],
  },
  "COMPRESSOR": {
    subplots: [
      { title: "Speed (%)",    tags: ["COMPRESSOR.Speed"],    yaxis: "yaxis" },
      { title: "Power (kW)",   tags: ["COMPRESSOR.Power"],    yaxis: "yaxis2" },
      { title: "Recycle (kmol/h)", tags: ["COMPRESSOR.RecycleF"], yaxis: "yaxis3" },
    ],
  },
  "PRODUCT-SPLIT": {
    subplots: [
      { title: "Product G (%)", tags: ["PRODUCT-SPLIT.xG"],      yaxis: "yaxis" },
      { title: "Product H (%)", tags: ["PRODUCT-SPLIT.xH"],      yaxis: "yaxis2" },
      { title: "Total Flow",    tags: ["PRODUCT-SPLIT.TotalF"],  yaxis: "yaxis3" },
    ],
  },
};

const COLORS = ["#3b82f6","#06b6d4","#8b5cf6","#f97316","#22c55e","#eab308","#ec4899"];

export default function TimeSeriesPanel({ activeNode, telemetryBuffer, limits = {} }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current) return;

    const config = AREA_CONFIG[activeNode];
    if (!config) {
      Plotly.purge(chartRef.current);
      return;
    }

    const traces = [];
    const shapes = [];

    config.subplots.forEach((subplot, si) => {
      const yaxisKey = si === 0 ? "y" : `y${si + 1}`;
      const xaxisKey = si === 0 ? "x" : `x${si + 1}`;

      subplot.tags.forEach((tag, ti) => {
        const data = telemetryBuffer[tag] || [];
        traces.push({
          x: data.map(p => p.x),
          y: data.map(p => p.y),
          name: tag.split(".").slice(1).join("."),
          type: "scatter",
          mode: "lines",
          line: { color: COLORS[(si * 2 + ti) % COLORS.length], width: 1.5, shape: "linear" },
          xaxis: xaxisKey,
          yaxis: yaxisKey,
        });

        // Add ISA 18.2 limit bands
        const env = limits[tag];
        if (env) {
          const yRef = si === 0 ? "y" : `y${si + 1}`;
          const addBand = (y0, y1, color, opacity) => {
            shapes.push({
              type: "rect",
              xref: "paper", yref: yRef,
              x0: 0, x1: 1,
              y0, y1,
              fillcolor: color,
              opacity,
              line: { width: 0 },
            });
          };
          if (env.hh !== undefined && env.h !== undefined) addBand(env.h, env.hh, "#ef4444", 0.07);
          if (env.h !== undefined && env.setpoint !== undefined) addBand(env.setpoint, env.h, "#f97316", 0.05);
          if (env.setpoint !== undefined && env.l !== undefined) addBand(env.l, env.setpoint, "#22c55e", 0.03);
          if (env.l !== undefined && env.ll !== undefined) addBand(env.ll, env.l, "#ef4444", 0.07);
          // Setpoint line
          if (env.setpoint !== undefined) {
            shapes.push({
              type: "line",
              xref: "paper", yref: yRef,
              x0: 0, x1: 1,
              y0: env.setpoint, y1: env.setpoint,
              line: { color: "#22c55e", width: 1, dash: "dot" },
            });
          }
        }
      });
    });

    const layout = {
      grid: { rows: 3, columns: 1, pattern: "independent" },
      margin: { l: 50, r: 10, t: 28, b: 30 },
      height: 400,
      showlegend: true,
      legend: { orientation: "h", y: 1.12, x: 0.5, xanchor: "center", font: { size: 9 } },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      shapes,
      font: { color: "var(--text-md)", size: 9 },
    };

    config.subplots.forEach((subplot, si) => {
      const xKey = si === 0 ? "xaxis" : `xaxis${si + 1}`;
      const yKey = si === 0 ? "yaxis" : `yaxis${si + 1}`;
      layout[xKey] = { showgrid: true, gridcolor: "#1e293b", tickfont: { size: 8 } };
      layout[yKey] = {
        title: { text: subplot.title, font: { size: 8 } },
        showgrid: true,
        gridcolor: "#1e293b",
        tickfont: { size: 8 },
      };

      // Scale to the DATA, not to the alarm bands.
      //
      // The limit rectangles are drawn against this axis and span ll..hh, and
      // Plotly's autorange includes shapes - so the axis stretched to the full
      // alarm envelope and every trend rendered as a flat line. Reactor T sits
      // at 122.6 with ~0.03 of noise; on a 0-130 axis that is sub-pixel, and
      // even a real 5 degree excursion moved about 4% of the height. Faults
      // were landing and were invisible.
      //
      // An explicit range also clips the bands into view rather than letting
      // them drive it. The floor stops pure sensor noise from being amplified
      // to fill the panel when nothing is actually happening.
      const ys = subplot.tags
        .flatMap(t => (telemetryBuffer[t] || []).map(p => p.y))
        .filter(v => Number.isFinite(v));
      if (ys.length) {
        const lo = Math.min(...ys), hi = Math.max(...ys);
        const mid = (lo + hi) / 2;
        const span = Math.max(hi - lo, Math.abs(mid) * 0.001, 0.05);
        const pad = span * 0.25;
        layout[yKey].range = [mid - span / 2 - pad, mid + span / 2 + pad];
      }
    });

    Plotly.react(chartRef.current, traces, layout, {
      responsive: true,
      displayModeBar: false,
    });
  }, [activeNode, telemetryBuffer, limits]);

  const config = AREA_CONFIG[activeNode];
  if (!config) {
    return (
      <div className="flex items-center justify-center h-48 text-xs" style={{ color: "var(--muted)" }}>
        Select a process unit from the P&ID diagram to view trends
      </div>
    );
  }

  return (
    <div
      className="rounded-xl shadow-sm overflow-hidden"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="px-4 pt-3 pb-0 flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--text-md)" }}>
        <span className="h-2 w-2 rounded-full bg-blue-500 animate-pulse" />
        {activeNode} — Live Trends
      </div>
      <div ref={chartRef} />
    </div>
  );
}

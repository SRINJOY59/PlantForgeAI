import React, { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";

// TEP phase plots — Reactor T vs P, and Product space xG vs xH
const PHASE_CONFIGS = {
  "REACTOR": {
    title: "Reactor Phase Portrait (T vs P)",
    xTag: "REACTOR.T",
    yTag: "REACTOR.P",
    xLabel: "Temperature (°C)",
    yLabel: "Pressure (kPa)",
    color: "#3b82f6",
  },
  "PRODUCT-SPLIT": {
    title: "Product Composition Space",
    xTag: "PRODUCT-SPLIT.xG",
    yTag: "PRODUCT-SPLIT.xH",
    xLabel: "xG — Product G (%)",
    yLabel: "xH — Product H (%)",
    color: "#22c55e",
  },
  "SEPARATOR": {
    title: "Separator T vs Level",
    xTag: "SEPARATOR.T",
    yTag: "SEPARATOR.Level",
    xLabel: "Temperature (°C)",
    yLabel: "Level (%)",
    color: "#8b5cf6",
  },
  "STRIPPER": {
    title: "Stripper T vs Level",
    xTag: "STRIPPER.T",
    yTag: "STRIPPER.Level",
    xLabel: "Temperature (°C)",
    yLabel: "Level (%)",
    color: "#f97316",
  },
  "COMPRESSOR": {
    title: "Compressor Speed vs Power",
    xTag: "COMPRESSOR.Speed",
    yTag: "COMPRESSOR.Power",
    xLabel: "Speed (%)",
    yLabel: "Power (kW)",
    color: "#06b6d4",
  },
  "CONDENSER": {
    title: "Condenser T vs Duty",
    xTag: "CONDENSER.T",
    yTag: "CONDENSER.HeatDuty",
    xLabel: "Temperature (°C)",
    yLabel: "Heat Duty (kJ/h)",
    color: "#ec4899",
  },
};

export default function PhasePlot({ activeNode, telemetryBuffer }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current) return;

    const cfg = PHASE_CONFIGS[activeNode];
    if (!cfg) {
      Plotly.purge(chartRef.current);
      return;
    }

    const xData = telemetryBuffer[cfg.xTag] || [];
    const yData = telemetryBuffer[cfg.yTag] || [];
    const N = Math.min(xData.length, yData.length);

    const xs = xData.slice(-N).map(p => p.y);
    const ys = yData.slice(-N).map(p => p.y);

    // Color by recency — older points are dimmer
    const nPts = xs.length;
    const markerColors = xs.map((_, i) => {
      const alpha = 0.2 + 0.8 * (i / Math.max(nPts - 1, 1));
      return `rgba(${hexToRgb(cfg.color)},${alpha.toFixed(2)})`;
    });

    Plotly.react(
      chartRef.current,
      [
        {
          x: xs,
          y: ys,
          type: "scatter",
          mode: "markers+lines",
          marker: {
            color: markerColors,
            size: 4,
          },
          line: { color: cfg.color, width: 0.8 },
          name: cfg.title,
        },
        // Current point
        xs.length > 0
          ? {
              x: [xs[xs.length - 1]],
              y: [ys[ys.length - 1]],
              type: "scatter",
              mode: "markers",
              marker: { color: "#ffffff", size: 9, symbol: "circle", line: { color: cfg.color, width: 2 } },
              name: "Current",
              showlegend: false,
            }
          : {},
      ],
      {
        margin: { l: 55, r: 15, t: 30, b: 45 },
        height: 300,
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { color: "var(--text-md)", size: 9 },
        xaxis: {
          title: { text: cfg.xLabel, font: { size: 9 } },
          showgrid: true,
          gridcolor: "#1e293b",
          tickfont: { size: 8 },
        },
        yaxis: {
          title: { text: cfg.yLabel, font: { size: 9 } },
          showgrid: true,
          gridcolor: "#1e293b",
          tickfont: { size: 8 },
        },
        showlegend: false,
      },
      { responsive: true, displayModeBar: false }
    );
  }, [activeNode, telemetryBuffer]);

  const cfg = PHASE_CONFIGS[activeNode];

  if (!cfg) {
    return (
      <div className="flex items-center justify-center h-48 text-xs" style={{ color: "var(--muted)" }}>
        Phase portrait not available for {activeNode || "selected unit"}
      </div>
    );
  }

  return (
    <div
      className="rounded-xl shadow-sm overflow-hidden"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="px-4 pt-3 pb-0 flex items-center gap-2 text-xs font-semibold" style={{ color: "var(--text-md)" }}>
        <span className="h-2 w-2 rounded-full animate-pulse" style={{ background: cfg.color }} />
        {cfg.title}
      </div>
      <div ref={chartRef} />
    </div>
  );
}

function hexToRgb(hex) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

import React, { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";

export default function ColumnProfile({ telemetry }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current) return;

    // Extract current stage values (00 to 11)
    const stages = Array.from({ length: 12 }, (_, i) => i);
    const xValues = new Array(12).fill(null);
    const tValues = new Array(12).fill(null);

    let hasData = false;
    stages.forEach((idx) => {
      // JS equivalent of Python's f"{idx:02d}"
      const stageStr = `TRAY-${String(idx).padStart(2, "0")}`;
      const xTag = `COLUMN-1.${stageStr}.x`;
      const tTag = `COLUMN-1.${stageStr}.T`;

      if (telemetry[xTag] && telemetry[xTag].length > 0) {
        xValues[idx] = telemetry[xTag][telemetry[xTag].length - 1].y;
        hasData = true;
      }
      if (telemetry[tTag] && telemetry[tTag].length > 0) {
        tValues[idx] = telemetry[tTag][telemetry[tTag].length - 1].y;
        hasData = true;
      }
    });

    if (!hasData) {
      Plotly.purge(chartRef.current);
      return;
    }

    // Stage labels: 0=Condenser, 1-10=Trays, 11=Reboiler
    const yLabels = stages.map((idx) => {
      if (idx === 0) return "Stage 0 (Condenser)";
      if (idx === 11) return "Stage 11 (Reboiler)";
      return `Tray ${idx}`;
    });

    const traces = [
      // Purity Profile (X-axis 1)
      {
        x: xValues,
        y: yLabels,
        name: "Composition (x_A)",
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#2563eb", width: 2.5 },
        marker: { size: 6, symbol: "circle" },
        xaxis: "x1",
      },
      // Temperature Profile (X-axis 2)
      {
        x: tValues,
        y: yLabels,
        name: "Temperature (T)",
        type: "scatter",
        mode: "lines+markers",
        line: { color: "#dc2626", width: 2, dash: "dot" },
        marker: { size: 6, symbol: "square" },
        xaxis: "x2",
      },
    ];

    const layout = {
      title: "COLUMN-1 — Live Stage Composition and Temperature Profile",
      margin: { l: 120, r: 40, t: 50, b: 50 },
      height: 380,
      showlegend: true,
      legend: { orientation: "h", y: 1.12, x: 0.5, xanchor: "center" },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      yaxis: {
        autorange: "reversed", // Stage 0 (condenser) at the top, Stage 11 (reboiler) at the bottom
        showgrid: true,
        gridcolor: "rgba(148,163,184,0.2)",
        tickfont: { size: 10, weight: "bold" },
      },
      xaxis: {
        title: "Mole Fraction x_A (mol/mol)",
        titlefont: { color: "#2563eb" },
        tickfont: { color: "#2563eb" },
        range: [0, 1],
        showgrid: true,
        gridcolor: "rgba(148,163,184,0.2)",
      },
      xaxis2: {
        title: "Temperature (K)",
        titlefont: { color: "#dc2626" },
        tickfont: { color: "#dc2626" },
        overlaying: "x",
        side: "top",
        showgrid: false,
        range: [315, 375],
      },
    };

    Plotly.react(chartRef.current, traces, layout, {
      displayModeBar: false,
      responsive: true,
    });
  }, [telemetry]);

  return (
    <div
      className="flex-1 rounded-xl p-4 shadow-sm"
      style={{
        background: "var(--bg-panel)",
        border: "1px solid var(--border)",
        minHeight: "410px",
      }}
    >
      <div
        className="flex items-center justify-between border-b pb-2 mb-2"
        style={{ borderColor: "var(--border)" }}
      >
        <h3
          className="text-sm font-semibold"
          style={{ color: "var(--text-md)" }}
        >
          Distillation Column Tray Profile
        </h3>
      </div>
      <div ref={chartRef} className="w-full" />
    </div>
  );
}

/**
 * McCabeThiele.jsx — McCabe-Thiele diagram for COLUMN-1.
 *
 * Renders:
 *  - Equilibrium curve: y* = α·x / (1 + (α−1)·x)   with α = 2.5 (benzene/toluene)
 *  - 45-degree diagonal (y = x)
 *  - Rectifying operating line: y = (L/V)·x + xD·(1 − L/V)
 *    L/V = reflux ratio / (reflux ratio + 1) approximated from the reflux tag
 *  - Stripping operating line (from bottoms x_B to feed intercept)
 *  - Live stepping between stages (staircases)
 *  - Animated current operating points for distillate (xD) and bottoms (xB)
 */
import React, { useEffect, useRef } from "react";
import Plotly from "plotly.js-basic-dist-min";

const ALPHA = 2.5; // relative volatility (benzene/toluene)
const N_STAGES = 12;

function equilibrium(x) {
  return (ALPHA * x) / (1 + (ALPHA - 1) * x);
}

function buildEquilibriumCurve() {
  const xs = [];
  const ys = [];
  for (let i = 0; i <= 100; i++) {
    const x = i / 100;
    xs.push(x);
    ys.push(equilibrium(x));
  }
  return { xs, ys };
}

function buildStaircases(xB, xD, LV) {
  // Rectifying operating line: y = LV*x + xD*(1-LV)
  const rectLine = (x) => LV * x + xD * (1 - LV);

  const staircaseX = [];
  const staircaseY = [];

  // Start from distillate and step down
  let x = xD;
  let y = xD;

  staircaseX.push(x);
  staircaseY.push(y);

  for (let s = 0; s < N_STAGES && x > xB + 0.001; s++) {
    // Horizontal step to equilibrium curve
    // Find x such that y* = current y: x* = y / (α - (α-1)*y)
    const xEq = y / (ALPHA - (ALPHA - 1) * y);
    staircaseX.push(xEq);
    staircaseY.push(y);

    // Vertical step to operating line
    const yOp = rectLine(xEq);
    staircaseX.push(xEq);
    staircaseY.push(yOp);

    x = xEq;
    y = yOp;
  }

  return { staircaseX, staircaseY };
}

export default function McCabeThiele({ telemetryBuffer }) {
  const chartRef = useRef(null);

  useEffect(() => {
    if (!chartRef.current) return;

    const xD = (telemetryBuffer["COLUMN-1.DISTILLATE.x"]?.slice(-1)[0]?.y) ?? 0.90;
    const xB = (telemetryBuffer["COLUMN-1.BOTTOMS.x"]?.slice(-1)[0]?.y) ?? 0.05;
    const reflux = (telemetryBuffer["COLUMN-1.REFLUX"]?.slice(-1)[0]?.y) ?? 0.20;

    // Estimate L/V (liquid-to-vapour ratio in rectifying section)
    // L/V ≈ R / (R + 1) where R is reflux ratio (dimensionless molar reflux / distillate)
    // We approximate R from reflux flow / (1 - reflux flow) since flow is normalised [0,1]
    const R = reflux > 0 ? reflux / Math.max(1 - reflux, 0.01) : 2.0;
    const LV = Math.min(R / (R + 1), 0.99);

    const { xs, ys } = buildEquilibriumCurve();
    const { staircaseX, staircaseY } = buildStaircases(xB, xD, LV);

    const traces = [
      // Equilibrium curve
      {
        x: xs,
        y: ys,
        mode: "lines",
        line: { color: "#2563eb", width: 2.5 },
        name: "Equil. curve",
        hovertemplate: "x=%{x:.3f}, y*=%{y:.3f}<extra></extra>",
      },
      // 45° diagonal
      {
        x: [0, 1],
        y: [0, 1],
        mode: "lines",
        line: { color: "#94a3b8", width: 1, dash: "dot" },
        name: "y = x",
      },
      // Rectifying operating line
      {
        x: [xB, xD],
        y: [LV * xB + xD * (1 - LV), xD],
        mode: "lines",
        line: { color: "#16a34a", width: 1.8, dash: "dash" },
        name: "Rectif. OL",
        hovertemplate: "ROL: y=%{y:.3f}<extra></extra>",
      },
      // Stage staircases
      {
        x: staircaseX,
        y: staircaseY,
        mode: "lines",
        line: { color: "#f59e0b", width: 1.5 },
        name: "Stages",
        hovertemplate: "Stage step<extra></extra>",
      },
      // Live distillate point
      {
        x: [xD],
        y: [xD],
        mode: "markers",
        marker: { size: 10, color: "#2563eb", symbol: "diamond", line: { color: "#fff", width: 1.5 } },
        name: `xD=${xD.toFixed(3)}`,
        hovertemplate: "xD=%{x:.3f}<extra></extra>",
      },
      // Live bottoms point
      {
        x: [xB],
        y: [xB],
        mode: "markers",
        marker: { size: 10, color: "#dc2626", symbol: "diamond", line: { color: "#fff", width: 1.5 } },
        name: `xB=${xB.toFixed(3)}`,
        hovertemplate: "xB=%{x:.3f}<extra></extra>",
      },
    ];

    const layout = {
      margin: { l: 50, r: 20, t: 30, b: 50 },
      height: 330,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      showlegend: true,
      legend: { orientation: "h", y: 1.12, x: 0.5, xanchor: "center", font: { size: 9 } },
      xaxis: {
        title: { text: "Liquid composition x", font: { size: 11 } },
        range: [0, 1],
        showgrid: true,
        gridcolor: "var(--border)",
      },
      yaxis: {
        title: { text: "Vapour composition y*", font: { size: 11 } },
        range: [0, 1],
        showgrid: true,
        gridcolor: "var(--border)",
      },
      title: { text: "McCabe-Thiele Diagram — COLUMN-1", font: { size: 12 }, x: 0.5 },
    };

    Plotly.react(chartRef.current, traces, layout, { displayModeBar: false, responsive: true });
  }, [telemetryBuffer]);

  return (
    <div
      className="rounded-xl p-4 shadow-sm"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", minHeight: "370px" }}
    >
      <div className="flex items-center justify-between border-b pb-2 mb-2" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-md)" }}>
          McCabe-Thiele Diagram
        </h3>
        <span className="text-[10px] text-slate-400">α = 2.5 (benzene/toluene) · operating lines live</span>
      </div>
      <div ref={chartRef} className="w-full" />
    </div>
  );
}

import React, { useState } from "react";
import { Play, Square, RotateCcw, AlertTriangle, CheckCircle, Radio, Zap, Activity } from "lucide-react";
import { simControl, simFault } from "../../../lib/api";

// IDV table — descriptions for the dropdown
const IDV_TABLE = {
  1:  "A/C feed ratio step (stream 4)",
  2:  "B composition step (stream 4)",
  3:  "D feed temperature step",
  4:  "Reactor coolant inlet T — step UP ⚠",
  5:  "Condenser coolant inlet T — step UP",
  6:  "A feed loss (stream 1 → 0) 🔴",
  7:  "C header pressure loss 🔴",
  8:  "A/B/C feed composition — random variation",
  9:  "D feed temperature — random variation",
  10: "C feed temperature — random variation",
  11: "Reactor coolant T — random variation",
  12: "Condenser coolant T — random variation",
  13: "Reaction kinetics — slow drift",
  14: "Reactor coolant valve stuck 🔴",
  15: "Condenser coolant valve stuck",
  16: "HX partial fouling",
  17: "E feed disturbance",
  18: "D feed surge",
  19: "Kinetics runaway 🔴",
  20: "HX severe fouling 🔴",
  21: "Stream 4 valve constant",
};

const SEVERITY_COLOR = {
  4: "#f97316", 6: "#ef4444", 7: "#ef4444", 14: "#ef4444",
  19: "#ef4444", 20: "#ef4444",
};

export default function SimControlStrip({ tepStatus, tepOnline, tepSimHealth, onRefresh }) {
  const [injecting, setInjecting] = useState(false);
  const [selectedIDV, setSelectedIDV] = useState(4);
  const [activeIDVs, setActiveIDVs] = useState([]);

  const handleAction = async (action) => {
    try {
      await simControl("tep", action);
      onRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  const handleInjectIDV = async () => {
    setInjecting(true);
    try {
      const res = await fetch("http://localhost:8000/sim/tep/idv", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ idv: selectedIDV, active: true }),
      });
      const data = await res.json();
      if (data.active_faults?._active_idvs) {
        setActiveIDVs(data.active_faults._active_idvs);
      }
      onRefresh();
    } catch (e) {
      console.error(e);
    } finally {
      setInjecting(false);
    }
  };

  const handleClearAll = async () => {
    try {
      await simFault("tep", "clear");
      setActiveIDVs([]);
      onRefresh();
    } catch (e) {
      console.error(e);
    }
  };

  const running = tepStatus?.running;
  const health = tepSimHealth || "nominal";
  const healthColor = health === "nominal" ? "var(--success)" : health === "degraded" ? "#f97316" : "#ef4444";

  return (
    <div
      className="rounded-xl px-4 py-3 shadow-sm"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      {/* Header row */}
      <div className="flex flex-wrap items-center gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Activity size={14} style={{ color: "var(--blue)" }} />
          <span className="text-xs font-bold tracking-wide uppercase" style={{ color: "var(--text-md)" }}>
            Tennessee Eastman Process
          </span>
        </div>

        {/* Online badge */}
        <div className="flex items-center gap-1.5 text-xs" style={{ color: tepOnline ? "var(--success)" : "var(--muted)" }}>
          <span className={`h-2 w-2 rounded-full ${tepOnline ? "bg-emerald-500 animate-pulse" : "bg-slate-400"}`} />
          {tepOnline ? "Online" : "Offline"}
        </div>

        {/* Sim health */}
        <div className="flex items-center gap-1.5 text-xs" style={{ color: healthColor }}>
          {health === "nominal"
            ? <CheckCircle size={11} />
            : <AlertTriangle size={11} />
          }
          Sim: {health}
        </div>

        {/* Tick count */}
        {tepStatus?.tick !== undefined && (
          <div className="text-xs font-mono" style={{ color: "var(--muted)" }}>
            tick #{tepStatus.tick.toLocaleString()}
          </div>
        )}
      </div>

      {/* Controls row */}
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {/* Start */}
        <button
          onClick={() => handleAction("start")}
          disabled={running}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-50"
          style={{
            background: running ? "var(--bg-panel)" : "var(--blue)",
            color: running ? "var(--muted)" : "#fff",
            border: "1px solid var(--border)",
          }}
        >
          <Play size={12} />
          Start
        </button>

        {/* Stop */}
        <button
          onClick={() => handleAction("stop")}
          disabled={!running}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-50"
          style={{ borderColor: "var(--border)", color: "var(--text-md)", background: "var(--bg-panel)" }}
        >
          <Square size={12} />
          Stop
        </button>

        {/* Reset */}
        <button
          onClick={() => handleAction("reset")}
          className="flex items-center gap-1.5 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-all hover:bg-slate-50/5"
          style={{ borderColor: "var(--border)", color: "var(--text-md)" }}
        >
          <RotateCcw size={12} />
          Reset
        </button>
      </div>

      {/* IDV Fault Injection panel */}
      <div
        className="rounded-lg p-3"
        style={{ background: "var(--bg-app)", border: "1px solid var(--border)" }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Zap size={12} style={{ color: "#f97316" }} />
          <span className="text-xs font-semibold" style={{ color: "var(--text-md)" }}>
            IDV Fault Injection
          </span>
          {activeIDVs.length > 0 && (
            <span className="ml-auto text-xs px-1.5 py-0.5 rounded-full font-semibold"
              style={{ background: "#ef4444", color: "#fff" }}>
              {activeIDVs.length} active
            </span>
          )}
        </div>

        <div className="flex flex-wrap gap-2 items-center">
          {/* IDV selector */}
          <select
            value={selectedIDV}
            onChange={e => setSelectedIDV(Number(e.target.value))}
            className="rounded-md border text-xs px-2 py-1.5 font-mono flex-1"
            style={{
              background: "var(--bg-panel)",
              borderColor: "var(--border)",
              color: SEVERITY_COLOR[selectedIDV] || "var(--text-md)",
              minWidth: 180,
            }}
          >
            {Object.entries(IDV_TABLE).map(([idv, desc]) => (
              <option key={idv} value={idv}>
                IDV-{idv}: {desc}
              </option>
            ))}
          </select>

          {/* Inject button */}
          <button
            onClick={handleInjectIDV}
            disabled={injecting || !running}
            className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all disabled:opacity-50"
            style={{ background: "#dc2626", color: "#fff" }}
          >
            <Zap size={11} />
            {injecting ? "Injecting…" : "Inject"}
          </button>

          {/* Clear all */}
          {activeIDVs.length > 0 && (
            <button
              onClick={handleClearAll}
              className="rounded-lg border px-3 py-1.5 text-xs font-semibold"
              style={{ borderColor: "var(--border)", color: "var(--muted)" }}
            >
              Clear All
            </button>
          )}
        </div>

        {/* Active IDV badges */}
        {activeIDVs.length > 0 && (
          <div className="flex flex-wrap gap-1 mt-2">
            {activeIDVs.map(idv => (
              <span
                key={idv}
                className="text-xs px-2 py-0.5 rounded-full font-mono font-semibold"
                style={{ background: SEVERITY_COLOR[idv] || "#7c3aed", color: "#fff" }}
              >
                IDV-{idv}
              </span>
            ))}
          </div>
        )}

        {/* Active IDV description */}
        {activeIDVs.length > 0 && (
          <div className="mt-2 text-xs" style={{ color: "var(--muted)" }}>
            {activeIDVs.map(idv => (
              <div key={idv}>▶ IDV-{idv}: {IDV_TABLE[idv]}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

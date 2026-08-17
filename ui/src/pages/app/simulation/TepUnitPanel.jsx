import React from "react";
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from "lucide-react";

// Tags per unit area
const AREA_TAGS = {
  "REACTOR": [
    { tag: "REACTOR.T",        label: "Temperature",     unit: "°C",       fmt: v => v.toFixed(1) },
    { tag: "REACTOR.P",        label: "Pressure",        unit: "kPa",      fmt: v => v.toFixed(0) },
    { tag: "REACTOR.Level",    label: "Level",           unit: "%",        fmt: v => v.toFixed(1) },
    { tag: "REACTOR.CoolT",    label: "Coolant Temp",    unit: "°C",       fmt: v => v.toFixed(1) },
    { tag: "REACTOR.HeatDuty", label: "Heat Duty",       unit: "kJ/h",     fmt: v => v.toFixed(0) },
    { tag: "REACTOR.xA",       label: "Comp A",          unit: "mol%",     fmt: v => v.toFixed(2) },
    { tag: "REACTOR.xB",       label: "Comp B (Inert)",  unit: "mol%",     fmt: v => v.toFixed(2) },
    { tag: "REACTOR.xC",       label: "Comp C",          unit: "mol%",     fmt: v => v.toFixed(2) },
    { tag: "REACTOR.xD",       label: "Comp D",          unit: "mol%",     fmt: v => v.toFixed(3) },
    { tag: "REACTOR.xE",       label: "Comp E",          unit: "mol%",     fmt: v => v.toFixed(3) },
    { tag: "REACTOR.xF",       label: "Comp F (Byprod)", unit: "mol%",     fmt: v => v.toFixed(3) },
    { tag: "REACTOR.xG",       label: "Comp G (Prod 1)", unit: "mol%",     fmt: v => v.toFixed(3) },
    { tag: "REACTOR.xH",       label: "Comp H (Prod 2)", unit: "mol%",     fmt: v => v.toFixed(3) },
  ],
  "CONDENSER": [
    { tag: "CONDENSER.T",        label: "Temperature",  unit: "°C",   fmt: v => v.toFixed(1) },
    { tag: "CONDENSER.P",        label: "Pressure",     unit: "kPa",  fmt: v => v.toFixed(0) },
    { tag: "CONDENSER.CoolT",    label: "Coolant Temp", unit: "°C",   fmt: v => v.toFixed(1) },
    { tag: "CONDENSER.HeatDuty", label: "Heat Duty",   unit: "kJ/h",  fmt: v => v.toFixed(0) },
  ],
  "SEPARATOR": [
    { tag: "SEPARATOR.T",       label: "Temperature",  unit: "°C",      fmt: v => v.toFixed(1) },
    { tag: "SEPARATOR.P",       label: "Pressure",     unit: "kPa",     fmt: v => v.toFixed(0) },
    { tag: "SEPARATOR.Level",   label: "Level",        unit: "%",       fmt: v => v.toFixed(1) },
    { tag: "SEPARATOR.xG",      label: "Liq G Frac",  unit: "mol%",    fmt: v => v.toFixed(2) },
    { tag: "SEPARATOR.xH",      label: "Liq H Frac",  unit: "mol%",    fmt: v => v.toFixed(2) },
    { tag: "SEPARATOR.VapFlow", label: "Vapour Out",  unit: "kmol/h",  fmt: v => v.toFixed(1) },
    { tag: "SEPARATOR.LiqFlow", label: "Liquid Out",  unit: "kmol/h",  fmt: v => v.toFixed(1) },
  ],
  "STRIPPER": [
    { tag: "STRIPPER.T",     label: "Temperature",  unit: "°C",     fmt: v => v.toFixed(1) },
    { tag: "STRIPPER.P",     label: "Pressure",     unit: "kPa",    fmt: v => v.toFixed(0) },
    { tag: "STRIPPER.Level", label: "Level",        unit: "%",      fmt: v => v.toFixed(1) },
    { tag: "STRIPPER.xG",    label: "Product G",   unit: "mol%",   fmt: v => v.toFixed(2) },
    { tag: "STRIPPER.xH",    label: "Product H",   unit: "mol%",   fmt: v => v.toFixed(2) },
    { tag: "STRIPPER.Flow",  label: "Product Flow",unit: "kmol/h", fmt: v => v.toFixed(1) },
  ],
  "COMPRESSOR": [
    { tag: "COMPRESSOR.Speed",   label: "Speed",       unit: "%",      fmt: v => v.toFixed(1) },
    { tag: "COMPRESSOR.Power",   label: "Power",       unit: "kW",     fmt: v => v.toFixed(1) },
    { tag: "COMPRESSOR.RecycleF",label: "Recycle Flow",unit: "kmol/h",fmt: v => v.toFixed(1) },
  ],
  "PRODUCT-SPLIT": [
    { tag: "PRODUCT-SPLIT.xG",    label: "Product G",   unit: "mol%",   fmt: v => v.toFixed(2) },
    { tag: "PRODUCT-SPLIT.xH",    label: "Product H",   unit: "mol%",   fmt: v => v.toFixed(2) },
    { tag: "PRODUCT-SPLIT.TotalF",label: "Total Flow",  unit: "kmol/h", fmt: v => v.toFixed(1) },
    { tag: "PRODUCT-SPLIT.Purity",label: "Purity (G+H)",unit: "mol%",  fmt: v => v.toFixed(2) },
  ],
};

function getLatest(telemetry, tag) {
  const arr = telemetry[tag];
  if (!arr || arr.length === 0) return null;
  return arr[arr.length - 1].y;
}

function getTrend(telemetry, tag) {
  const arr = telemetry[tag];
  if (!arr || arr.length < 3) return "flat";
  const last = arr[arr.length - 1].y;
  const prev = arr[arr.length - 3].y;
  const delta = last - prev;
  if (Math.abs(delta) < 0.001) return "flat";
  return delta > 0 ? "up" : "down";
}

function getAlarmLevel(value, limits, tag) {
  const env = limits[tag];
  if (!env || value === null) return null;
  if (env.hh !== undefined && value >= env.hh) return "HH";
  if (env.h !== undefined && value >= env.h)   return "H";
  if (env.ll !== undefined && value <= env.ll) return "LL";
  if (env.l  !== undefined && value <= env.l)  return "L";
  return null;
}

const ALARM_COLORS = {
  HH: { bg: "#7f1d1d", border: "#ef4444", text: "#fca5a5" },
  LL: { bg: "#7f1d1d", border: "#ef4444", text: "#fca5a5" },
  H:  { bg: "#431407", border: "#f97316", text: "#fdba74" },
  L:  { bg: "#431407", border: "#f97316", text: "#fdba74" },
};

export default function TepUnitPanel({ activeNode, telemetry, limits = {} }) {
  const tags = AREA_TAGS[activeNode];

  if (!tags) {
    return (
      <div className="text-xs text-center py-6" style={{ color: "var(--muted)" }}>
        Select a unit area from the P&ID to see live readings
      </div>
    );
  }

  return (
    <div
      className="rounded-xl shadow-sm p-4"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span className="h-2 w-2 rounded-full bg-emerald-500 animate-pulse" />
        <span className="text-xs font-bold uppercase tracking-wide" style={{ color: "var(--text-md)" }}>
          {activeNode} — Live Readings
        </span>
        <span className="ml-auto text-xs" style={{ color: "var(--muted)" }}>
          {tags.length} tags
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {tags.map(({ tag, label, unit, fmt }) => {
          const val = getLatest(telemetry, tag);
          const trend = getTrend(telemetry, tag);
          const alarm = getAlarmLevel(val, limits, tag);
          const ac = alarm ? ALARM_COLORS[alarm] : null;

          return (
            <div
              key={tag}
              className="rounded-lg p-2.5 transition-all"
              style={{
                background: ac ? ac.bg : "var(--bg-app)",
                border: `1px solid ${ac ? ac.border : "var(--border)"}`,
              }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs font-medium" style={{ color: ac ? ac.text : "var(--muted)" }}>
                  {label}
                </span>
                <div className="flex items-center gap-1">
                  {alarm && <AlertTriangle size={10} style={{ color: ac.border }} />}
                  {trend === "up"   && <TrendingUp  size={10} style={{ color: "#22c55e" }} />}
                  {trend === "down" && <TrendingDown size={10} style={{ color: "#ef4444" }} />}
                  {trend === "flat" && <Minus size={10} style={{ color: "var(--muted)" }} />}
                </div>
              </div>
              <div className="font-mono font-bold text-sm" style={{ color: ac ? ac.text : "var(--text-hi)" }}>
                {val !== null ? fmt(val) : "—"}
                <span className="text-xs font-normal ml-1" style={{ color: "var(--muted)" }}>
                  {unit}
                </span>
              </div>
              {alarm && (
                <div className="text-xs mt-0.5 font-bold" style={{ color: ac.border }}>
                  {alarm} ALARM
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * DiagnosePanel.jsx — the standalone diagnosis signal.
 *
 * When the plant breaches a limit, the diagnostics service distils the episode
 * into a live signature and matches it against the fault library the simulator
 * generated. Each card here is one such diagnosis: the alarm that triggered it,
 * the known faults that signature resembles (ranked, with confidence), and the
 * cascade the plant actually showed — which tags moved, which way, in what order.
 *
 * Deliberately not the Alerts feed. An alert is an event to acknowledge; this is
 * a hypothesis to weigh — a resemblance to known fault knowledge, never a verdict.
 */
import React from "react";
import { Stethoscope, ArrowUp, ArrowDown, Clock } from "lucide-react";

function confColor(c) {
  if (c >= 0.75) return "#16a34a";      // green — a strong resemblance
  if (c >= 0.4) return "#f59e0b";       // amber — plausible
  return "#94a3b8";                     // grey — weak, still shown
}

function levelColor(level) {
  return level === "HH" || level === "LL" ? "#dc2626" : "#f59e0b";
}

function relTime(iso) {
  const t = new Date(iso).getTime();
  if (isNaN(t)) return "";
  const s = Math.max(0, Math.round((Date.now() - t) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)}m ago`;
  return `${Math.round(s / 3600)}h ago`;
}

function MatchRow({ match, top }) {
  const pct = Math.round((match.confidence || 0) * 100);
  const color = confColor(match.confidence || 0);
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <div className="w-14 shrink-0 font-mono text-xs font-semibold"
        style={{ color: top ? color : "var(--text-md)" }}>
        {match.cause_id || "—"}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="truncate text-xs" style={{ color: "var(--text-md)" }}
            title={match.cause_label}>
            {match.cause_label || match.fault_mode_id}
          </span>
          <span className="shrink-0 font-mono text-xs font-bold" style={{ color }}>
            {pct}%
          </span>
        </div>
        <div className="mt-1 h-1.5 w-full rounded-full overflow-hidden"
          style={{ background: "var(--border)" }}>
          <div className="h-full rounded-full transition-all"
            style={{ width: `${pct}%`, background: color }} />
        </div>
        {match.unit_areas?.length > 0 && (
          <div className="mt-1 flex flex-wrap gap-1">
            {match.unit_areas.map((a) => (
              <span key={a} className="rounded px-1 py-0.5 text-[9px] font-mono"
                style={{ background: "var(--bg-subtle, rgba(148,163,184,0.12))", color: "var(--muted)" }}>
                {a}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Deviation({ dev }) {
  const up = dev.direction === "high";
  const Arrow = up ? ArrowUp : ArrowDown;
  const color = up ? "#dc2626" : "#2563eb";
  return (
    <div className="flex items-center gap-1.5 rounded-md px-1.5 py-1"
      style={{ background: "var(--bg-subtle, rgba(148,163,184,0.10))" }}>
      <span className="font-mono text-[9px] font-bold" style={{ color: "var(--muted)" }}>
        {dev.first_mover_rank + 1}
      </span>
      <Arrow size={11} style={{ color }} />
      <span className="font-mono text-[10px]" style={{ color: "var(--text-md)" }}
        title={`${dev.magnitude}σ, +${Math.round(dev.onset_offset_s)}s from onset`}>
        {dev.tag_id}
      </span>
      <span className="font-mono text-[9px]" style={{ color: "var(--muted)" }}>
        {Number(dev.magnitude).toFixed(1)}σ
      </span>
    </div>
  );
}

function DiagnosisCard({ d }) {
  const matches = d.matches || [];
  const devs = d.signature?.deviations || [];
  return (
    <div className="rounded-xl p-3.5 shadow-sm"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      {/* trigger header */}
      <div className="flex items-center justify-between gap-2 border-b pb-2 mb-2.5"
        style={{ borderColor: "var(--border)" }}>
        <div className="flex items-center gap-2">
          <span className="rounded px-1.5 py-0.5 font-mono text-[10px] font-bold text-white"
            style={{ background: levelColor(d.trigger_level) }}>
            {d.trigger_level || "—"}
          </span>
          <span className="font-mono text-xs font-semibold" style={{ color: "var(--text-md)" }}>
            {d.trigger_tag}
          </span>
        </div>
        <div className="flex items-center gap-1 text-[10px]" style={{ color: "var(--muted)" }}>
          <Clock size={10} />
          {relTime(d.onset)}
        </div>
      </div>

      {/* ranked matches */}
      {matches.length > 0 ? (
        <div className="divide-y" style={{ borderColor: "var(--border)" }}>
          {matches.map((m, i) => (
            <MatchRow key={m.fault_mode_id || i} match={m} top={i === 0} />
          ))}
        </div>
      ) : (
        <div className="py-2 text-xs italic" style={{ color: "var(--muted)" }}>
          No known fault mode matches this signature — an unseen disturbance, or
          the library has no case for it yet.
        </div>
      )}

      {/* the signature the plant actually showed */}
      {devs.length > 0 && (
        <div className="mt-2.5 pt-2 border-t" style={{ borderColor: "var(--border)" }}>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide"
            style={{ color: "var(--muted)" }}>
            Observed cascade
          </div>
          <div className="flex flex-wrap gap-1.5">
            {devs.map((dev) => <Deviation key={dev.tag_id} dev={dev} />)}
          </div>
        </div>
      )}
    </div>
  );
}

export default function DiagnosePanel({ diagnoses = [] }) {
  return (
    <div className="rounded-xl p-4 shadow-sm"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      <div className="flex items-center justify-between border-b pb-2 mb-3"
        style={{ borderColor: "var(--border)" }}>
        <h3 className="flex items-center gap-1.5 text-sm font-semibold"
          style={{ color: "var(--text-md)" }}>
          <Stethoscope size={14} />
          Live Diagnosis
        </h3>
        <span className="text-[10px]" style={{ color: "var(--muted)" }}>
          matched against the simulator's fault library
        </span>
      </div>

      {diagnoses.length === 0 ? (
        <div className="flex h-24 flex-col items-center justify-center gap-1 text-center">
          <span className="text-xs text-slate-400">
            No live diagnoses yet.
          </span>
          <span className="text-[10px] text-slate-400 max-w-xs">
            When the plant breaches a limit, the matched fault modes appear here —
            a short wait after the alarm while the cascade develops.
          </span>
        </div>
      ) : (
        <div className="space-y-2.5 max-h-[70vh] overflow-y-auto">
          {diagnoses.map((d, i) => (
            <DiagnosisCard key={d.id || i} d={d} />
          ))}
        </div>
      )}
    </div>
  );
}

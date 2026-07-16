import { useEffect, useState } from "react";
import { Bell, BellOff, AlertTriangle, ShieldAlert } from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";
import AlertCard from "../../components/AlertCard";

const FILTERS = [
  { id: "all",             label: "All",        icon: Bell },
  { id: "failure_pattern", label: "Failures",   icon: AlertTriangle },
  { id: "compliance",      label: "Compliance", icon: ShieldAlert },
];

export default function Alerts() {
  const { alerts, connected, markAllRead } = useAlerts();
  const [filter, setFilter] = useState("all");
  useEffect(() => { markAllRead(); }, [markAllRead]);
  const shown = alerts.filter(a => filter === "all" || a.kind === filter);

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-6">
      <div className="mb-6 flex items-center gap-3">
        <div>
          <h1 className="page-title flex items-center gap-3">
            Alerts
            {connected
              ? <span className="flex items-center gap-1.5 text-xs font-normal" style={{ color: "var(--success)" }}><span className="live-dot" /> live</span>
              : <span className="flex items-center gap-1.5 text-xs font-normal" style={{ color: "var(--muted)" }}><span className="h-2 w-2 rounded-full" style={{ background: "var(--border-md)" }} /> connecting…</span>
            }
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>Agents watch every failure and compliance event in real time</p>
        </div>

        <div className="ml-auto flex items-center gap-1.5">
          {FILTERS.map(f => (
            <button key={f.id} onClick={() => setFilter(f.id)}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150"
              style={filter === f.id
                ? { background: "#dbeafe", color: "var(--blue)", border: "1px solid #bfdbfe" }
                : { background: "var(--bg-panel)", color: "var(--muted)", border: "1px solid var(--border)" }
              }
            >
              <f.icon size={12} /> {f.label}
            </button>
          ))}
        </div>
      </div>

      {alerts.length > 0 && (
        <div className="mb-4 flex items-center gap-4 rounded-xl px-4 py-3 text-xs"
          style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
          <span style={{ color: "var(--muted)" }}>{alerts.length} total</span>
          <span className="h-3 w-px" style={{ background: "var(--border)" }} />
          <span style={{ color: "#dc2626" }}>{alerts.filter(a => a.kind === "failure_pattern").length} failures</span>
          <span className="h-3 w-px" style={{ background: "var(--border)" }} />
          <span style={{ color: "#d97706" }}>{alerts.filter(a => a.kind === "compliance").length} compliance</span>
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {shown.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
            <div className="grid h-16 w-16 place-items-center rounded-2xl"
              style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
              <BellOff size={28} style={{ color: "var(--muted-lt)" }} />
            </div>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>No alerts yet</p>
              <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>Ingest a new failure and the agents will react here.</p>
            </div>
          </div>
        ) : shown.map(a => <AlertCard key={a.id} alert={a} />)}
      </div>
    </div>
  );
}

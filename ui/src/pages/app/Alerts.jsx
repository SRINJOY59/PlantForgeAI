import { useEffect, useState } from "react";
import { BellOff } from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";
import AlertCard from "../../components/AlertCard";

export default function Alerts() {
  const { alerts, connected, markAllRead } = useAlerts();
  const [filter, setFilter] = useState("all");

  useEffect(() => { markAllRead(); }, [markAllRead]);

  const shown = alerts.filter(
    (a) => filter === "all" || a.kind === filter
  );

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-6">
      <div className="mb-4 flex items-center gap-3">
        <h1 className="text-lg font-semibold">Alerts</h1>
        <span className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-gray-400"}`} />
        <span className="text-xs muted">{connected ? "live" : "waiting for stream"}</span>
        <div className="ml-auto flex gap-1">
          {["all", "failure_pattern", "compliance"].map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${filter === f ? "bg-steel-600 text-white" : "text-gray-600 hover:bg-gray-100 dark:text-slate-400 dark:hover:bg-slate-800"}`}
            >
              {f === "failure_pattern" ? "Failures" : f === "all" ? "All" : "Compliance"}
            </button>
          ))}
        </div>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto">
        {shown.length === 0 ? (
          <div className="grid h-full place-items-center text-center muted">
            <div>
              <BellOff size={28} className="mx-auto mb-2 opacity-50" />
              <p className="text-sm">No alerts yet.</p>
              <p className="text-xs">Ingest a new failure and the agents will react here.</p>
            </div>
          </div>
        ) : (
          shown.map((a) => <AlertCard key={a.id} alert={a} />)
        )}
      </div>
    </div>
  );
}

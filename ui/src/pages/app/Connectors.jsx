import { FolderSync, Database, Plus, RefreshCw } from "lucide-react";

// Configured data sources. In production these come from the control plane
// (Supabase); here they mirror connectors.json to show the surface.
const CONNECTORS = [
  {
    id: "inbox", type: "folder", icon: FolderSync,
    detail: "data/inbox", status: "active", every: "5 min",
  },
  {
    id: "sap-pm", type: "SAP PM", icon: Database,
    detail: "not configured", status: "available", every: "—",
  },
  {
    id: "pi-historian", type: "PI Historian", icon: Database,
    detail: "not configured", status: "available", every: "—",
  },
];

export default function Connectors() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      <div className="mb-1 flex items-center gap-3">
        <h1 className="text-lg font-semibold">Connectors</h1>
        <button className="btn-primary ml-auto text-sm">
          <Plus size={16} /> Add connector
        </button>
      </div>
      <p className="mb-5 text-sm muted">
        Point a connector at a system and the brain stays current on its own —
        new documents sync in on schedule.
      </p>

      <div className="space-y-3">
        {CONNECTORS.map((c) => (
          <div key={c.id} className="surface flex items-center gap-4 rounded-lg p-4">
            <span className="grid h-10 w-10 place-items-center rounded-lg bg-steel-50 text-steel-600 dark:bg-steel-950">
              <c.icon size={20} />
            </span>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="font-medium">{c.id}</span>
                <span className="text-xs muted">· {c.type}</span>
              </div>
              <div className="tag truncate text-xs muted">{c.detail}</div>
            </div>
            <div className="text-right text-xs muted">
              <div>every {c.every}</div>
            </div>
            <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${c.status === "active" ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300" : "bg-gray-100 text-gray-500 dark:bg-slate-800"}`}>
              {c.status}
            </span>
            {c.status === "active" && (
              <button className="btn-ghost px-2" title="Sync now">
                <RefreshCw size={16} />
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

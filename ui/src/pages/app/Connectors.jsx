import { FolderSync, Database, Plus, RefreshCw, CheckCircle2, Clock, AlertCircle, ExternalLink } from "lucide-react";

const CONNECTORS = [
  {
    id: "inbox", type: "Folder Watch", icon: FolderSync,
    detail: "data/inbox", status: "active", every: "5 min",
    color: "#00ff9d", lastSync: "2 min ago", docsIngested: 142,
  },
  {
    id: "sap-pm", type: "SAP Plant Maintenance", icon: Database,
    detail: "Not configured", status: "available", every: "—",
    color: "#00ccf5", lastSync: null, docsIngested: 0,
  },
  {
    id: "pi-historian", type: "OSIsoft PI Historian", icon: Database,
    detail: "Not configured", status: "available", every: "—",
    color: "#b44dff", lastSync: null, docsIngested: 0,
  },
  {
    id: "sharepoint", type: "SharePoint / OneDrive", icon: Database,
    detail: "Not configured", status: "available", every: "—",
    color: "#ffb800", lastSync: null, docsIngested: 0,
  },
];

const statusConfig = {
  active:    { label: "Active",     color: "#00ff9d", Icon: CheckCircle2 },
  available: { label: "Available",  color: "#64748b", Icon: Clock },
  error:     { label: "Error",      color: "#ff3d6e", Icon: AlertCircle },
};

export default function Connectors() {
  return (
    <div className="mx-auto max-w-3xl px-6 py-6">
      {/* Header */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="page-title">Connectors</h1>
          <p className="text-sm mt-1" style={{ color: "var(--text-md)" }}>
            Point a connector at a system and the brain stays current on its own.
          </p>
        </div>
        <button
          className="btn-primary text-sm gap-2"
          onClick={() => alert("Connector wizard coming soon!")}
        >
          <Plus size={15} />
          Add connector
        </button>
      </div>

      {/* Stats row */}
      <div className="mb-6 grid grid-cols-3 gap-3">
        {[
          { label: "Active syncs",    value: CONNECTORS.filter((c) => c.status === "active").length, color: "#00ff9d" },
          { label: "Docs ingested",   value: CONNECTORS.reduce((s, c) => s + c.docsIngested, 0), color: "#00ccf5" },
          { label: "Available",       value: CONNECTORS.filter((c) => c.status === "available").length, color: "#64748b" },
        ].map(({ label, value, color }) => (
          <div
            key={label}
            className="rounded-xl px-4 py-3 text-center"
            style={{ background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)" }}
          >
            <div className="text-2xl font-bold font-display" style={{ color }}>{value}</div>
            <div className="text-xs mt-1" style={{ color: "var(--text-md)" }}>{label}</div>
          </div>
        ))}
      </div>

      {/* Connector cards */}
      <div className="space-y-3">
        {CONNECTORS.map((c) => {
          const { label, color, Icon: SIcon } = statusConfig[c.status];
          return (
            <div
              key={c.id}
              className="group cyber-card rounded-xl p-4"
            >
              <div className="flex items-center gap-4">
                {/* Icon */}
                <div
                  className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-xl transition-all duration-300"
                  style={{
                    background: `${c.color}12`,
                    border: `1px solid ${c.color}25`,
                  }}
                >
                  <c.icon size={20} style={{ color: c.color }} />
                </div>

                {/* Info */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm" style={{ color: "#e2e8f0" }}>
                      {c.id}
                    </span>
                    <span
                      className="rounded px-1.5 py-0.5 text-[10px] font-medium"
                      style={{
                        background: "rgba(255,255,255,0.05)",
                        color: "var(--text-md)",
                      }}
                    >
                      {c.type}
                    </span>
                  </div>
                  <div className="mt-0.5 font-mono text-[11px]" style={{ color: "var(--text-md)" }}>
                    {c.detail}
                  </div>
                  {c.lastSync && (
                    <div className="mt-1 text-[11px]" style={{ color: "#334155" }}>
                      Last sync: {c.lastSync} · {c.docsIngested} docs
                    </div>
                  )}
                </div>

                {/* Right side */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  {c.status === "active" && (
                    <div className="hidden text-right sm:block">
                      <div className="text-xs font-medium" style={{ color: "#64748b" }}>
                        every
                      </div>
                      <div className="text-xs font-mono" style={{ color: "#00ccf5" }}>
                        {c.every}
                      </div>
                    </div>
                  )}

                  {/* Status badge */}
                  <span
                    className="flex items-center gap-1.5 rounded-full px-3 py-1 text-[11px] font-medium"
                    style={{
                      background: `${color}12`,
                      color,
                      border: `1px solid ${color}25`,
                    }}
                  >
                    {c.status === "active" && (
                      <span
                        className="h-1.5 w-1.5 rounded-full"
                        style={{ background: color, boxShadow: `0 0 6px ${color}`, animation: "ping 1.5s ease-in-out infinite" }}
                      />
                    )}
                    <SIcon size={10} />
                    {label}
                  </span>

                  {/* Actions */}
                  {c.status === "active" ? (
                    <button
                      className="btn-ghost px-2 py-2"
                      title="Sync now"
                    >
                      <RefreshCw size={15} />
                    </button>
                  ) : (
                    <button
                      className="btn-ghost px-2 py-2"
                      title="Configure"
                    >
                      <ExternalLink size={15} />
                    </button>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

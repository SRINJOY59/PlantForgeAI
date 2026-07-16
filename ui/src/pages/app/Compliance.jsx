import { useState, useMemo } from "react";
import { ShieldCheck, XCircle, Clock, CheckCircle2, Search, ChevronDown, ChevronUp } from "lucide-react";

const COMPLIANCE_ITEMS = [
  { id: "PSI-2024-001", title: "Pressure Vessel Inspection — V-201", type: "Statutory", status: "overdue",   dueDate: "2024-03-15", unit: "Unit 200", inspector: "J. Singh",      notes: "API 510 mandatory every 2 years. Last done 2022-03." },
  { id: "PSI-2024-002", title: "Safety Relief Valve Test — PSV-204",  type: "Statutory", status: "overdue",   dueDate: "2024-04-01", unit: "Unit 200", inspector: "M. Patel",      notes: "Linked to K-301 trip scenario. Requires out-of-service test." },
  { id: "ATEX-2024-001",title: "ATEX Equipment Inspection — Pump Hall",type: "ATEX",    status: "due_soon",  dueDate: "2024-07-30", unit: "Unit 100", inspector: "R. Kumar",      notes: "Ex-rated motors P-101A/B. Annual check under DSEAR." },
  { id: "ISO-2024-001", title: "ISO 55001 Internal Audit",             type: "ISO",     status: "due_soon",  dueDate: "2024-08-15", unit: "All units",inspector: "S. Chakraborty",notes: "Annual asset management audit. Gather WO evidence packages." },
  { id: "LOLER-2024-001",title:"Lifting Equipment Inspection — Crane A",type:"Statutory",status:"compliant", dueDate: "2025-01-10", unit: "Unit 300", inspector: "B. Das",        notes: "6-monthly LOLER inspection. Completed 2024-07-10." },
  { id: "EL-2024-001",  title: "Electrical Installation Inspection",   type: "Statutory",status: "compliant", dueDate: "2027-01-01", unit: "Unit 100", inspector: "K. Sharma",    notes: "5-year periodic per BS 7671. Completed 2022." },
  { id: "ENV-2024-001", title: "Environmental Emissions Report — Q3",  type: "Environmental",status:"compliant",dueDate:"2024-10-31",unit:"All units",inspector:"P. Ghosh",      notes: "Quarterly EA report. Data from PI Historian." },
];

const STATUS_CFG = {
  overdue:   { label: "Overdue",   color: "#dc2626", bg: "#fee2e2", border: "#fca5a5", Icon: XCircle       },
  due_soon:  { label: "Due Soon",  color: "#d97706", bg: "#fef3c7", border: "#fcd34d", Icon: Clock         },
  compliant: { label: "Compliant", color: "#16a34a", bg: "#dcfce7", border: "#86efac", Icon: CheckCircle2  },
};

export default function Compliance() {
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [expanded, setExpanded] = useState(null);

  const filtered = useMemo(() =>
    COMPLIANCE_ITEMS.filter(i =>
      (filterStatus === "all" || i.status === filterStatus) &&
      (search === "" || i.title.toLowerCase().includes(search.toLowerCase()) ||
        i.id.toLowerCase().includes(search.toLowerCase()) || i.unit.toLowerCase().includes(search.toLowerCase()))
    ), [search, filterStatus]);

  const counts = useMemo(() => ({
    overdue:   COMPLIANCE_ITEMS.filter(i => i.status === "overdue").length,
    due_soon:  COMPLIANCE_ITEMS.filter(i => i.status === "due_soon").length,
    compliant: COMPLIANCE_ITEMS.filter(i => i.status === "compliant").length,
  }), []);

  return (
    <div className="mx-auto max-w-3xl px-6 py-6 overflow-y-auto h-full">
      <div className="mb-6">
        <h1 className="page-title flex items-center gap-2"><ShieldCheck size={20} style={{ color: "var(--blue)" }} /> Compliance</h1>
        <p className="text-sm mt-1" style={{ color: "var(--muted)" }}>
          Statutory inspections, audit evidence, and regulatory obligations across all units.
        </p>
      </div>

      {/* Stats */}
      <div className="mb-5 grid grid-cols-3 gap-3">
        {[
          { key: "overdue",   label: "Overdue",   count: counts.overdue },
          { key: "due_soon",  label: "Due Soon",  count: counts.due_soon },
          { key: "compliant", label: "Compliant", count: counts.compliant },
        ].map(({ key, label, count }) => {
          const { color, bg, border } = STATUS_CFG[key];
          const active = filterStatus === key;
          return (
            <button key={key} onClick={() => setFilterStatus(f => f === key ? "all" : key)}
              className="rounded-xl px-4 py-4 text-center transition-all duration-150"
              style={{
                background: active ? bg : "#fff",
                border: `1px solid ${active ? border : "var(--border)"}`,
                boxShadow: active ? "0 2px 8px rgba(0,0,0,0.06)" : "0 1px 2px rgba(0,0,0,0.04)",
              }}
            >
              <div className="text-2xl font-bold" style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", color }}>{count}</div>
              <div className="text-xs mt-1" style={{ color: "var(--muted)" }}>{label}</div>
            </button>
          );
        })}
      </div>

      {/* Search */}
      <div className="relative mb-4">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2" style={{ color: "var(--muted)" }} />
        <input className="input pl-9" placeholder="Search by title, ID, unit…" value={search} onChange={e => setSearch(e.target.value)} />
      </div>

      {/* Items */}
      <div className="space-y-2">
        {filtered.length === 0 && <p className="py-8 text-center text-sm" style={{ color: "var(--muted)" }}>No items match.</p>}
        {filtered.map(item => {
          const { label, color, bg, border, Icon } = STATUS_CFG[item.status];
          const isOpen = expanded === item.id;
          return (
            <div key={item.id} className="rounded-xl overflow-hidden transition-all duration-200"
              style={{
                background: "#fff",
                border: isOpen ? `1px solid ${border}` : "1px solid var(--border)",
                boxShadow: isOpen ? "0 2px 8px rgba(0,0,0,0.06)" : "0 1px 2px rgba(0,0,0,0.04)",
              }}>
              <button className="w-full flex items-center gap-3 px-4 py-3.5 text-left"
                onClick={() => setExpanded(isOpen ? null : item.id)}>
                <div className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-lg" style={{ background: bg }}>
                  <Icon size={16} style={{ color }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{item.title}</span>
                    <span className="rounded px-1.5 py-0.5 text-[10px] font-mono"
                      style={{ background: "#f1f5f9", color: "var(--muted)" }}>{item.id}</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                    <span>{item.unit}</span><span>·</span><span>{item.type}</span><span>·</span><span>Due {item.dueDate}</span>
                  </div>
                </div>
                <span className="badge flex-shrink-0" style={{ background: bg, color, border: `1px solid ${border}` }}>
                  <Icon size={10} />{label}
                </span>
                {isOpen ? <ChevronUp size={15} style={{ color: "var(--muted)" }} /> : <ChevronDown size={15} style={{ color: "var(--muted)" }} />}
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-0" style={{ borderTop: "1px solid var(--border)" }}>
                  <div className="pt-3 grid grid-cols-2 gap-3 text-xs">
                    <div><span style={{ color: "var(--muted)" }}>Inspector: </span><span style={{ color: "var(--text-md)" }}>{item.inspector}</span></div>
                    <div><span style={{ color: "var(--muted)" }}>Due date: </span><span style={{ color: "var(--text-md)" }}>{item.dueDate}</span></div>
                  </div>
                  <p className="mt-3 text-xs leading-relaxed" style={{ color: "var(--muted)" }}>{item.notes}</p>
                  <div className="mt-3 flex gap-2">
                    <button className="btn-outline text-xs px-3 py-1.5">View evidence</button>
                    <button className="btn-ghost text-xs px-3 py-1.5">Schedule inspection</button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

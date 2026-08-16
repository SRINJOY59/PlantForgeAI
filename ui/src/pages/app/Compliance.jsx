// The plant's statutory position, read from the graph.
//
// This page used to render a hardcoded array - the counts, the inspector names
// and the PSI ids were all invented, and the two action buttons had no onClick.
// Everything here now comes from GOVERNED_BY edges: which asset, which
// standard, when it was last done and when it falls due next.
//
// Status and counts are computed server-side, deliberately. Two places
// deciding what "due soon" means is how a summary card ends up disagreeing
// with the list underneath it.

import { useEffect, useMemo, useState } from "react";
import {
  ShieldCheck, XCircle, Clock, CheckCircle2, Search, ChevronDown, ChevronUp,
  FileText, CalendarPlus, Loader2,
} from "lucide-react";
import { getCompliance, scheduleInspection } from "../../lib/api";
import { DocumentModal } from "../../components/DocumentViewer";

const STATUS_CFG = {
  overdue:   { label: "Overdue",   color: "#dc2626", bg: "#fee2e2", border: "#fca5a5", Icon: XCircle },
  due_soon:  { label: "Due Soon",  color: "#d97706", bg: "#fef3c7", border: "#fcd34d", Icon: Clock },
  compliant: { label: "Compliant", color: "#16a34a", bg: "#dcfce7", border: "#86efac", Icon: CheckCircle2 },
};

export default function Compliance() {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [filterStatus, setFilterStatus] = useState("all");
  const [expanded, setExpanded] = useState(null);
  const [activeDoc, setActiveDoc] = useState(null);
  const [scheduling, setScheduling] = useState(null);
  const [scheduled, setScheduled] = useState({});

  useEffect(() => {
    let live = true;
    getCompliance()
      .then((d) => live && setData(d))
      .catch((e) => {
        if (!live) return;
        const s = Number(String(e?.message ?? "").match(/\b(\d{3})\b/)?.[1]);
        setError(s === 403
          ? "Compliance requires the engineer role."
          : "Couldn't load the compliance position. Is the backend running?");
      });
    return () => { live = false; };
  }, []);

  const items = data?.items ?? [];
  const counts = data?.counts ?? { overdue: 0, due_soon: 0, compliant: 0 };

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((i) =>
      (filterStatus === "all" || i.status === filterStatus) &&
      (q === "" || i.equipment.toLowerCase().includes(q) ||
        i.standard.toLowerCase().includes(q) ||
        i.inspection_type.toLowerCase().includes(q)));
  }, [items, search, filterStatus]);

  async function schedule(item) {
    setScheduling(item.id);
    try {
      const res = await scheduleInspection(item.id);
      setScheduled((p) => ({ ...p, [item.id]: res.order_type || "PM02" }));
    } catch (e) {
      const s = Number(String(e?.message ?? "").match(/\b(\d{3})\b/)?.[1]);
      setError(s === 403
        ? "Drafting work requires the engineer role."
        : "Couldn't draft the work order.");
    } finally {
      setScheduling(null);
    }
  }

  return (
    <div className="mx-auto h-full max-w-3xl overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="page-title flex items-center gap-2">
          <ShieldCheck size={20} style={{ color: "var(--blue)" }} /> Compliance
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Statutory obligations from the plant graph
          {data ? ` — as of ${data.as_of}, "due soon" is the next ${data.due_soon_days} days.` : "."}
        </p>
      </div>

      {error && (
        <div className="mb-4 rounded-xl px-4 py-3 text-sm"
          style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
          {error}
        </div>
      )}

      <div className="mb-5 grid grid-cols-3 gap-3">
        {["overdue", "due_soon", "compliant"].map((key) => {
          const { color, bg, border, label } = STATUS_CFG[key];
          const active = filterStatus === key;
          return (
            <button key={key}
              onClick={() => setFilterStatus((f) => (f === key ? "all" : key))}
              className="rounded-xl px-4 py-4 text-center transition-all duration-150"
              style={{ background: active ? bg : "var(--bg-panel)",
                       border: `1px solid ${active ? border : "var(--border)"}` }}>
              <div className="text-2xl font-bold"
                style={{ fontFamily: "'Plus Jakarta Sans',sans-serif", color }}>
                {data ? counts[key] : "—"}
              </div>
              <div className="mt-1 text-xs" style={{ color: "var(--muted)" }}>{label}</div>
            </button>
          );
        })}
      </div>

      <div className="relative mb-4">
        <Search size={13} className="absolute left-3 top-1/2 -translate-y-1/2"
          style={{ color: "var(--muted)" }} />
        <input className="input pl-9" placeholder="Search by tag, standard, inspection type…"
          value={search} onChange={(e) => setSearch(e.target.value)} />
      </div>

      <div className="space-y-2">
        {!data && !error && (
          <p className="py-8 text-center text-sm" style={{ color: "var(--muted)" }}>
            Reading the graph…
          </p>
        )}
        {data && items.length === 0 && (
          <p className="py-8 text-center text-sm" style={{ color: "var(--muted)" }}>
            No obligations with due dates in the graph yet — these come from
            GOVERNED_BY edges created during ingestion.
          </p>
        )}
        {data && items.length > 0 && filtered.length === 0 && (
          <p className="py-8 text-center text-sm" style={{ color: "var(--muted)" }}>
            No items match.
          </p>
        )}

        {filtered.map((item) => {
          const cfg = STATUS_CFG[item.status] ?? STATUS_CFG.compliant;
          const { label, color, bg, border, Icon } = cfg;
          const isOpen = expanded === item.id;
          return (
            <div key={item.id} className="overflow-hidden rounded-xl transition-all duration-200"
              style={{ background: "var(--bg-panel)",
                       border: isOpen ? `1px solid ${border}` : "1px solid var(--border)" }}>
              <button className="flex w-full items-center gap-3 px-4 py-3.5 text-left"
                onClick={() => setExpanded(isOpen ? null : item.id)}>
                <div className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-lg"
                  style={{ background: bg }}>
                  <Icon size={16} style={{ color }} />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium" style={{ color: "var(--text)" }}>
                      {item.inspection_type} — {item.equipment}
                    </span>
                    <span className="rounded px-1.5 py-0.5 font-mono text-[10px]"
                      style={{ background: "var(--bg-subtle)", color: "var(--muted)" }}>
                      {item.standard}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
                    <span>Due {item.next_due}</span>
                    {item.last_inspection && (<><span>·</span><span>Last {item.last_inspection}</span></>)}
                    {item.revision && (<><span>·</span><span>Rev {item.revision}</span></>)}
                  </div>
                </div>
                <span className="badge flex-shrink-0"
                  style={{ background: bg, color, border: `1px solid ${border}` }}>
                  <Icon size={10} />{label}
                </span>
                {isOpen ? <ChevronUp size={15} style={{ color: "var(--muted)" }} />
                        : <ChevronDown size={15} style={{ color: "var(--muted)" }} />}
              </button>

              {isOpen && (
                <div className="px-4 pb-4 pt-0" style={{ borderTop: "1px solid var(--border)" }}>
                  <div className="grid grid-cols-2 gap-3 pt-3 text-xs">
                    <Field label="Asset" value={item.equipment} mono />
                    <Field label="Due date" value={item.next_due} />
                    <Field label="Standard" value={item.standard} />
                    <Field label="Last inspection" value={item.last_inspection || "not recorded"} />
                  </div>

                  <div className="mt-3 flex flex-wrap gap-2">
                    <button className="btn-outline flex items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-40"
                      disabled={!item.doc_id}
                      title={item.doc_id ? `Open ${item.doc_id}` : "No source document on this obligation"}
                      onClick={() => setActiveDoc({ docId: item.doc_id })}>
                      <FileText size={12} /> View evidence
                    </button>

                    {scheduled[item.id] ? (
                      <span className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium"
                        style={{ background: "#dcfce7", color: "#166534" }}>
                        <CheckCircle2 size={12} /> {scheduled[item.id]} draft raised — approve it in Work Orders
                      </span>
                    ) : (
                      <button className="btn-ghost flex items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-40"
                        disabled={scheduling === item.id}
                        onClick={() => schedule(item)}>
                        {scheduling === item.id
                          ? <><Loader2 size={12} className="animate-spin" /> Drafting…</>
                          : <><CalendarPlus size={12} /> Schedule inspection</>}
                      </button>
                    )}
                  </div>

                  <p className="mt-2.5 text-[10px] leading-relaxed" style={{ color: "var(--muted-lt)" }}>
                    Scheduling raises a preventive work order for a planner to approve.
                    Nothing is booked into the CMMS from here.
                  </p>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {activeDoc && (
        <DocumentModal docId={activeDoc.docId} filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)} />
      )}
    </div>
  );
}

function Field({ label, value, mono }) {
  return (
    <div>
      <span style={{ color: "var(--muted)" }}>{label}: </span>
      <span className={mono ? "font-mono" : ""} style={{ color: "var(--text-md)" }}>{value}</span>
    </div>
  );
}

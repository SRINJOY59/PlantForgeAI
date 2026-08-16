// Drafted work orders awaiting a planner.
//
// The layout follows the artifact, and the artifact is deliberately split: the
// fact lists were harvested out of the graph tools, so the model could not
// invent into them, while root_cause and recommended_fix are the only prose it
// wrote. That distinction is the entire basis for trusting this page, so it is
// drawn - harvested facts as counted chips, prose under a trust banner,
// evidence clickable. A wall of text hides exactly what a planner must weigh.

import { useEffect, useRef, useState } from "react";
import {
  ClipboardList, Check, X, AlertTriangle, CheckCircle2, Wrench, ScrollText,
  FileText, Factory, ShieldAlert, Layers,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { subscribeDraftWorkOrders, decideWorkOrder } from "../../lib/api";
import { DocumentModal } from "../../components/DocumentViewer";

// Derived from failure recurrence and statutory exposure by a rule in the
// agent, never chosen by the model - which is what makes it safe to lead with.
const PRIORITY = {
  immediate: { label: "Immediate", color: "#dc2626", bg: "#fee2e2" },
  high:      { label: "High",      color: "#c2410c", bg: "#ffedd5" },
  medium:    { label: "Medium",    color: "#a16207", bg: "#fef3c7" },
  low:       { label: "Low",       color: "#0369a1", bg: "#e0f2fe" },
};

const ORDER_TYPE = { PM01: "PM01 · Corrective", PM02: "PM02 · Preventive" };

// The content without a page heading, so the Alerts page can host it as a tab
// and the standalone route can wrap it in one. Alerts and work orders are two
// halves of the same loop - what the plant is telling you, and what you are
// going to do about it - so they read better side by side than a nav apart.
export function WorkOrderPanel() {
  const [drafts, setDrafts] = useState([]);
  const [activeDoc, setActiveDoc] = useState(null);
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const seen = useRef(new Set());

  useEffect(() => {
    let stop = () => {};
    try {
      stop = subscribeDraftWorkOrders((draft) => {
        if (seen.current.has(draft.id)) return;
        seen.current.add(draft.id);
        setDrafts((prev) => [draft, ...prev]);
      });
    } catch {
      // gateway not up yet; the rest of the app still works
    }
    return () => stop();
  }, []);

  async function decide(id, decision) {
    setBusy(id); setError(null);
    try {
      const res = await decideWorkOrder(id, decision);
      setDrafts((prev) => prev.map((d) => (d.id === id
        ? { ...d, status: res.status, decided_by: res.decided_by } : d)));
    } catch (e) {
      const status = Number(String(e?.message ?? "").match(/\b(\d{3})\b/)?.[1]);
      setError(status === 403
        ? "Approving a work order requires the engineer role."
        : "Couldn't record the decision. Is the backend running?");
    } finally {
      setBusy(null);
    }
  }

  const pending = drafts.filter(
    (d) => (d.status ?? "pending_approval") === "pending_approval");

  return (
    <>
      <p className="mb-4 text-xs" style={{ color: "var(--muted)" }}>
        Drafted from failure investigations and compliance gaps.{" "}
        <strong style={{ color: "var(--text-md)" }}>{pending.length} awaiting approval</strong>
        {" "}— nothing reaches SAP until a planner signs off.
      </p>

      {error && (
        <div className="mb-4 rounded-xl px-4 py-3 text-sm"
          style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
          {error}
        </div>
      )}

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto">
        {drafts.length === 0 ? <Empty /> : drafts.map((d) => (
          <DraftCard key={d.id} draft={d} busy={busy === d.id} onDecide={decide}
            onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })} />
        ))}
      </div>

      {activeDoc && (
        <DocumentModal docId={activeDoc.docId} filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)} />
      )}
    </>
  );
}

/** The standalone /app/work-orders route. Same panel, with a page heading. */
export default function WorkOrders() {
  return (
    <div className="mx-auto flex h-full max-w-4xl flex-col px-6 py-6">
      <h1 className="page-title mb-1">Work Orders</h1>
      <WorkOrderPanel />
    </div>
  );
}

function DraftCard({ draft: d, busy, onDecide, onOpenDoc }) {
  const p = PRIORITY[d.priority] ?? PRIORITY.medium;
  const status = d.status ?? "pending_approval";

  return (
    <div className="overflow-hidden rounded-xl"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)",
               borderLeft: `3px solid ${p.color}` }}>

      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wider"
              style={{ background: p.bg, color: p.color }}>{p.label}</span>
            <span className="font-mono text-[10px]" style={{ color: "var(--muted-lt)" }}>
              {ORDER_TYPE[d.order_type] ?? d.order_type}
            </span>
          </div>
          <h2 className="mt-1.5 flex items-center gap-2 text-sm font-semibold"
            style={{ color: "var(--text)" }}>
            <ClipboardList size={15} style={{ color: p.color }} />
            {d.equipment}
            {d.failure_mode && (
              <span className="font-mono text-xs font-normal" style={{ color: "var(--muted)" }}>
                {d.failure_mode}
              </span>
            )}
          </h2>
        </div>
        <Decision status={status} by={d.decided_by} busy={busy}
          onDecide={(x) => onDecide(d.id, x)} />
      </div>

      <div className="space-y-3 px-5 pb-4 pt-3">
        <TrustBanner verified={d.verified} claims={d.unverified_claims} />

        {/* harvested from the graph - the model could not write into these */}
        <div className="grid gap-2 sm:grid-cols-2">
          <Facts icon={Factory} label="Affected equipment" items={d.affected_equipment} mono />
          <Facts icon={Wrench} label="Prior work orders" items={d.prior_work_orders} mono />
          <Facts icon={ScrollText} label="Procedures" items={d.procedures} mono />
          <Facts icon={ShieldAlert} label="Governing clauses" items={d.governing_clauses} />
        </div>

        <Prose title="Root cause" text={d.root_cause} />
        <Prose title="Recommended fix" text={d.recommended_fix} />

        {d.citations?.length > 0 && (
          <div>
            <Label>Evidence</Label>
            <div className="flex flex-wrap gap-1.5">
              {d.citations.map((c, i) => (
                <button key={i} type="button" title={c.doc_id}
                  onClick={() => onOpenDoc(c.doc_id, c.filename)}
                  className="flex items-center gap-1 rounded-lg px-2 py-1 font-mono text-[10px] transition-colors"
                  style={{ background: "var(--bg-subtle)", color: "var(--text-md)",
                           border: "1px solid var(--border)" }}>
                  <FileText size={10} style={{ color: "var(--brand)" }} />
                  {c.filename || c.doc_id}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="flex items-center gap-1.5 border-t pt-2.5 text-[10px]"
          style={{ borderColor: "var(--border)", color: "var(--muted-lt)" }}>
          <Layers size={10} />
          Reasoned against graph v{d.graph_version} — a later change to the plant
          is a different work order.
        </div>
      </div>
    </div>
  );
}

function Decision({ status, by, busy, onDecide }) {
  if (status === "approved" || status === "rejected") {
    const ok = status === "approved";
    return (
      <span className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium"
        style={{ background: ok ? "#dcfce7" : "var(--bg-subtle)",
                 color: ok ? "#166534" : "var(--muted)" }}>
        {ok ? <Check size={13} /> : <X size={13} />}
        {ok ? "Approved" : "Rejected"}{by ? ` · ${by}` : ""}
      </span>
    );
  }
  return (
    <div className="flex flex-shrink-0 gap-1.5">
      <button disabled={busy} onClick={() => onDecide("rejected")}
        className="btn-ghost px-2.5 py-1.5 text-xs disabled:opacity-40">
        <X size={13} /> Reject
      </button>
      <button disabled={busy} onClick={() => onDecide("approved")}
        className="btn-primary px-3 py-1.5 text-xs disabled:opacity-40">
        <Check size={13} /> {busy ? "Saving…" : "Approve"}
      </button>
    </div>
  );
}

function TrustBanner({ verified, claims }) {
  if (verified !== false) {
    return (
      <div className="flex items-start gap-2 rounded-lg px-3 py-2"
        style={{ background: "#dcfce7", border: "1px solid #86efac" }}>
        <CheckCircle2 size={13} className="mt-0.5 flex-shrink-0" style={{ color: "#16a34a" }} />
        <p className="text-[11px] leading-relaxed" style={{ color: "#166534" }}>
          <span className="font-semibold">Grounded.</span> Every asset, procedure
          and work order listed came out of the plant graph, not the model.
        </p>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2 rounded-lg px-3 py-2"
      style={{ background: "#fee2e2", border: "1px solid #fca5a5" }}>
      <AlertTriangle size={13} className="mt-0.5 flex-shrink-0" style={{ color: "#dc2626" }} />
      <div className="text-[11px] leading-relaxed" style={{ color: "#991b1b" }}>
        <span className="font-semibold">Not fully grounded.</span> Parts of the
        narrative could not be traced to evidence and may be wrong:
        <span className="ml-1 font-mono">{(claims || []).join(", ")}</span>
      </div>
    </div>
  );
}

function Label({ children }) {
  return (
    <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-widest"
      style={{ color: "var(--muted-lt)" }}>{children}</div>
  );
}

function Facts({ icon: Icon, label, items, mono }) {
  const has = items?.length > 0;
  return (
    <div className="rounded-lg px-3 py-2.5"
      style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <Icon size={11} style={{ color: "var(--muted)" }} />
        <span className="text-[9px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted-lt)" }}>{label}</span>
        {has && (
          <span className="ml-auto text-[10px] font-bold" style={{ color: "var(--muted)" }}>
            {items.length}
          </span>
        )}
      </div>
      {!has ? (
        <p className="text-[11px] italic" style={{ color: "var(--muted-lt)" }}>
          None in the graph.
        </p>
      ) : (
        <div className="flex flex-wrap gap-1">
          {items.map((it, i) => (
            <span key={i}
              className={`rounded px-1.5 py-0.5 text-[11px] ${mono ? "font-mono" : ""}`}
              style={{ background: "var(--bg-panel)", color: "var(--text-md)",
                       border: "1px solid var(--border)" }}>
              {it}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function Prose({ title, text }) {
  if (!text) return null;
  return (
    <div>
      <Label>{title}</Label>
      <div className="prose prose-sm max-w-none text-[13px] dark:prose-invert prose-p:my-1 prose-p:leading-relaxed prose-ol:my-1 prose-ul:my-1 prose-li:my-0.5"
        style={{ color: "var(--text-md)" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
      </div>
    </div>
  );
}

function Empty() {
  return (
    <div className="flex h-48 flex-col items-center justify-center gap-3 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl"
        style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
        <ClipboardList size={24} style={{ color: "var(--muted-lt)" }} />
      </div>
      <div>
        <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>No drafts yet</p>
        <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>
          One is drafted whenever a failure investigation concludes.
        </p>
      </div>
    </div>
  );
}

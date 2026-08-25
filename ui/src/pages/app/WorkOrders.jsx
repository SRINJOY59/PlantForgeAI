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
  FileText, Factory, ShieldAlert, Layers, Calendar, Users, Send, Clock,
  Plus, Trash2, Globe,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  subscribeDraftWorkOrders, decideWorkOrder, scheduleWorkOrder,
  dispatchWorkOrder, getSchedules, getCrew, addCrewMember, removeCrewMember,
} from "../../lib/api";
import { DocumentModal } from "../../components/DocumentViewer";
// Shared with the field shell, so a language offered here is one a worker
// can actually read their job card in.
import { DISPATCH_LANGUAGES } from "../../lib/i18n";

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
  const [scheduleModal, setScheduleModal] = useState(null);
  const seen = useRef(new Set());

  useEffect(() => {
    let stop = () => {};
    try {
      stop = subscribeDraftWorkOrders((draft) => {
        if (seen.current.has(draft.id)) {
          // Update existing draft (e.g. schedule status changed)
          setDrafts((prev) => prev.map((d) =>
            d.id === draft.id ? { ...d, ...draft } : d));
          return;
        }
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

  async function handleScheduleSubmit(draftId, schedData) {
    setBusy(draftId); setError(null);
    try {
      const res = await scheduleWorkOrder(draftId, schedData);
      setDrafts((prev) => prev.map((d) => (d.id === draftId
        ? { ...d, schedule_status: "pending_approval", schedule: res.schedule } : d)));
      setScheduleModal(null);
    } catch (e) {
      setError("Failed to schedule work order. Is Slack configured?");
    } finally {
      setBusy(null);
    }
  }

  // The Slack half of the flow happens outside this app entirely: somebody
  // taps Approve in a chat client and a crew gets dispatched, with nothing
  // landing on the drafts stream to say so. So while anything is waiting on an
  // answer, poll for it - and stop the moment nothing is, rather than tick
  // forever against a console left open on a desk overnight.
  const waiting = drafts.some((d) => d.schedule_status === "pending_approval");
  useEffect(() => {
    if (!waiting) return undefined;
    let cancelled = false;
    const timer = setInterval(async () => {
      try {
        const schedules = await getSchedules();
        if (cancelled) return;
        setDrafts((prev) => prev.map((d) => {
          const sched = schedules[d.id];
          if (!sched || sched.status === d.schedule_status) return d;
          return { ...d, schedule_status: sched.status, schedule: sched };
        }));
      } catch {
        // A missed poll is a card that updates a few seconds later; the next
        // tick fixes it and an error banner here would be noise.
      }
    }, 5000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [waiting]);

  // Retry a delivery that failed after Slack had already approved it. Not an
  // approval path - the gateway refuses anything Slack has not authorised - so
  // this only ever re-sends work somebody already signed off.
  async function redispatch(draftId) {
    setBusy(draftId); setError(null);
    try {
      const res = await dispatchWorkOrder(draftId);
      setDrafts((prev) => prev.map((d) => (d.id === draftId
        ? { ...d, schedule: { ...(d.schedule ?? {}),
                              dispatched_to: res.dispatched_to,
                              dispatch_error: undefined } }
        : d)));
    } catch {
      setError("Couldn't reach the crew. Check that the roster has workers with emails.");
    } finally {
      setBusy(null);
    }
  }

  const awaitingSlack = drafts.filter(
    (d) => d.schedule_status === "pending_approval");
  const pending = drafts.filter(
    (d) => (d.status ?? "pending_approval") === "pending_approval");

  return (
    <>
      <p className="mb-4 text-xs" style={{ color: "var(--muted)" }}>
        Drafted from failure investigations and compliance gaps.{" "}
        <strong style={{ color: "var(--text-md)" }}>{pending.length} awaiting review</strong>
        {awaitingSlack.length > 0 && (
          <>, <strong style={{ color: "var(--text-md)" }}>
            {awaitingSlack.length} awaiting Slack approval</strong></>
        )}
        {" "}— scheduling asks Slack to authorise the work, and no crew is
        notified until it answers.
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
            onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })}
            onSchedule={(draft) => setScheduleModal(draft)}
            onDispatch={redispatch} />
        ))}
      </div>

      {activeDoc && (
        <DocumentModal docId={activeDoc.docId} filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)} />
      )}

      {scheduleModal && (
        <ScheduleModal
          draft={scheduleModal}
          busy={busy === scheduleModal.id}
          onSubmit={(data) => handleScheduleSubmit(scheduleModal.id, data)}
          onClose={() => setScheduleModal(null)}
        />
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

function DraftCard({ draft: d, busy, onDecide, onOpenDoc, onSchedule, onDispatch }) {
  const p = PRIORITY[d.priority] ?? PRIORITY.medium;
  const status = d.status ?? "pending_approval";
  const scheduleStatus = d.schedule_status ?? null;

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
        <div className="flex items-center gap-2">
          <Decision status={status} by={d.decided_by} busy={busy}
            onDecide={(x) => onDecide(d.id, x)} />
        </div>
      </div>

      <div className="space-y-3 px-5 pb-4 pt-3">
        <TrustBanner verified={d.verified} claims={d.unverified_claims} />

        {/* Where the Slack authorisation for this work has got to, and - once
            it is given - who it actually reached. */}
        {scheduleStatus && (
          <ScheduleStatusBadge status={scheduleStatus} schedule={d.schedule}
            busy={busy} onDispatch={() => onDispatch(d.id)} />
        )}

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

        <div className="flex items-center justify-between border-t pt-2.5"
          style={{ borderColor: "var(--border)" }}>
          <div className="flex items-center gap-1.5 text-[10px]"
            style={{ color: "var(--muted-lt)" }}>
            <Layers size={10} />
            Reasoned against graph v{d.graph_version} — a later change to the plant
            is a different work order.
          </div>

          {/* Scheduling is what sends this to Slack, so it is offered on any
              draft nobody has rejected - the approval it is asking for IS the
              Slack one, and requiring a console approval first would mean the
              card already read "Approved" while still waiting to be. Offered
              again after a Slack rejection: a rejected slot is a rejected
              slot, not a rejected work order. */}
          {status !== "rejected" && scheduleStatus !== "pending_approval"
            && scheduleStatus !== "approved" && (
            <button onClick={() => onSchedule(d)} disabled={busy}
              className="btn-primary flex items-center gap-1.5 px-3 py-1.5 text-xs disabled:opacity-40">
              <Calendar size={12} />
              {scheduleStatus === "rejected" ? "Re-schedule Work" : "Schedule Work"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ScheduleStatusBadge({ status, schedule, busy, onDispatch }) {
  const sent = schedule?.dispatched_to ?? [];
  const failed = schedule?.dispatch_error;

  // "Approved" and "delivered" are two different facts and the card must never
  // merge them. An order Slack authorised but that reached nobody is the
  // failure this whole flow exists to prevent, so it gets its own state and a
  // way out of it, rather than a green tick that is quietly lying.
  const cfg = {
    pending_approval: {
      icon: Clock, label: "Awaiting approval in Slack", color: "#a16207",
      bg: "#fef3c7", border: "#fde68a",
    },
    approved: failed ? {
      icon: AlertTriangle, label: "Approved, but not delivered", color: "#c2410c",
      bg: "#ffedd5", border: "#fed7aa",
    } : {
      icon: CheckCircle2, label: "Approved and sent to the crew", color: "#166534",
      bg: "#dcfce7", border: "#86efac",
    },
    rejected: {
      icon: X, label: "Schedule rejected in Slack", color: "#991b1b",
      bg: "#fee2e2", border: "#fca5a5",
    },
  }[status];
  if (!cfg) return null;
  const Icon = cfg.icon;

  return (
    <div className="rounded-lg px-3 py-2"
      style={{ background: cfg.bg, border: `1px solid ${cfg.border}` }}>
      <div className="flex items-center gap-2">
        <Icon size={14} style={{ color: cfg.color }} />
        <span className="text-xs font-medium" style={{ color: cfg.color }}>
          {cfg.label}
        </span>
        {schedule?.decided_by && (
          <span className="ml-auto text-[10px]" style={{ color: cfg.color }}>
            {schedule.decided_by}
          </span>
        )}
      </div>

      {status === "pending_approval" && (
        <p className="mt-1 text-[11px] leading-relaxed" style={{ color: cfg.color }}>
          Nobody has been notified yet. The crew is told the moment this is
          approved, not before.
        </p>
      )}

      {failed && (
        <div className="mt-1.5">
          <p className="text-[11px] leading-relaxed" style={{ color: cfg.color }}>
            The approval stands — only the delivery failed: {failed}
          </p>
          <button onClick={onDispatch} disabled={busy}
            className="btn-ghost mt-1.5 flex items-center gap-1.5 px-2.5 py-1 text-[11px] disabled:opacity-40">
            <Send size={11} /> {busy ? "Sending…" : "Retry dispatch"}
          </button>
        </div>
      )}

      {sent.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <Users size={11} style={{ color: cfg.color }} />
          {sent.map((r) => (
            <span key={r.assignment_id ?? r.worker_key}
              className="rounded px-1.5 py-0.5 text-[10px]"
              style={{ background: "rgba(255,255,255,.55)", color: cfg.color }}>
              {r.name} · {r.lang}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}


function ScheduleModal({ draft, busy, onSubmit, onClose }) {
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [notes, setNotes] = useState("");
  const [crew, setCrew] = useState([]);
  const [loadingCrew, setLoadingCrew] = useState(true);
  const [newName, setNewName] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [newLang, setNewLang] = useState("en");

  useEffect(() => {
    getCrew().then(setCrew).catch(() => setCrew([])).finally(() => setLoadingCrew(false));
  }, []);

  async function handleAddCrew(e) {
    e.preventDefault();
    if (!newName.trim() || !newEmail.trim()) return;
    try {
      await addCrewMember({ name: newName.trim(), email: newEmail.trim(), lang: newLang });
      const updated = await getCrew();
      setCrew(updated);
      setNewName(""); setNewEmail(""); setNewLang("en");
    } catch { /* swallow */ }
  }

  async function handleRemoveCrew(id) {
    try {
      await removeCrewMember(id);
      setCrew((prev) => prev.filter((w) => w.id !== id));
    } catch { /* swallow */ }
  }

  function submit() {
    onSubmit({ windowStart, windowEnd, notes });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm"
      onClick={onClose}>
      <div className="mx-4 w-full max-w-lg rounded-2xl shadow-2xl"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
        onClick={(e) => e.stopPropagation()}>

        <div className="border-b px-6 py-4" style={{ borderColor: "var(--border)" }}>
          <h3 className="flex items-center gap-2 text-base font-semibold"
            style={{ color: "var(--text)" }}>
            <Calendar size={18} style={{ color: "var(--brand)" }} />
            Schedule Work — {draft.equipment}
          </h3>
          <p className="mt-1 text-xs" style={{ color: "var(--muted)" }}>
            Propose a time window and assign crew. This will be sent to Slack for approval.
          </p>
        </div>

        <div className="space-y-4 px-6 py-5">
          {/* Time window */}
          <div className="grid gap-3 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--muted-lt)" }}>Start</label>
              <input type="datetime-local" value={windowStart}
                onChange={(e) => setWindowStart(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                         color: "var(--text)" }} />
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--muted-lt)" }}>End</label>
              <input type="datetime-local" value={windowEnd}
                onChange={(e) => setWindowEnd(e.target.value)}
                className="w-full rounded-lg border px-3 py-2 text-sm"
                style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                         color: "var(--text)" }} />
            </div>
          </div>

          {/* Crew roster */}
          <div>
            <label className="mb-2 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--muted-lt)" }}>
              <Users size={11} /> Crew
            </label>

            {loadingCrew ? (
              <p className="text-xs italic" style={{ color: "var(--muted)" }}>Loading crew…</p>
            ) : crew.length === 0 ? (
              <p className="text-xs" style={{ color: "#c2410c" }}>
                No crew yet. Add at least one worker — an approved order with
                nobody on the roster reaches nobody.
              </p>
            ) : (
              <div className="mb-2 space-y-1">
                {crew.map((w) => (
                  <div key={w.id} className="flex items-center justify-between rounded-lg px-3 py-1.5"
                    style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium" style={{ color: "var(--text)" }}>{w.name}</span>
                      <span className="flex items-center gap-0.5 text-[10px]" style={{ color: "var(--muted)" }}>
                        <Globe size={9} /> {w.lang}
                      </span>
                    </div>
                    <button onClick={() => handleRemoveCrew(w.id)}
                      className="rounded p-1 transition-colors hover:bg-red-100"
                      style={{ color: "var(--muted)" }}>
                      <Trash2 size={12} />
                    </button>
                  </div>
                ))}
              </div>
            )}

            <form onSubmit={handleAddCrew} className="flex gap-2">
              <input placeholder="Name" value={newName}
                onChange={(e) => setNewName(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-xs"
                style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                         color: "var(--text)" }} />
              <input placeholder="Email" value={newEmail}
                onChange={(e) => setNewEmail(e.target.value)}
                className="min-w-0 flex-1 rounded-lg border px-2.5 py-1.5 text-xs"
                style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                         color: "var(--text)" }} />
              <select value={newLang} onChange={(e) => setNewLang(e.target.value)}
                className="rounded-lg border px-2 py-1.5 text-xs"
                style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                         color: "var(--text)" }}>
                {DISPATCH_LANGUAGES.map((l) => (
                  <option key={l.code} value={l.code}>{l.label}</option>
                ))}
              </select>
              <button type="submit"
                className="btn-ghost flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs">
                <Plus size={12} /> Add
              </button>
            </form>
          </div>

          {/* Notes */}
          <div>
            <label className="mb-1 block text-[10px] font-semibold uppercase tracking-widest"
              style={{ color: "var(--muted-lt)" }}>Engineer's Notes</label>
            <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
              placeholder="Any special instructions for the approver or crew…"
              rows={2}
              className="w-full rounded-lg border px-3 py-2 text-sm"
              style={{ background: "var(--bg-subtle)", borderColor: "var(--border)",
                       color: "var(--text)", resize: "vertical" }} />
          </div>
        </div>

        <div className="flex justify-end gap-2 border-t px-6 py-4"
          style={{ borderColor: "var(--border)" }}>
          <button onClick={onClose} className="btn-ghost px-4 py-2 text-xs">Cancel</button>
          <button onClick={submit} disabled={busy || !windowStart || crew.length === 0}
            title={crew.length === 0 ? "Add at least one worker to your crew first" : ""}
            className="btn-primary flex items-center gap-1.5 px-4 py-2 text-xs disabled:opacity-40">
            <Send size={12} /> {busy ? "Sending…" : "Send to Slack"}
          </button>
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

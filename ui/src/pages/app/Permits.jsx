import { useState } from "react";
import { FileSignature, ShieldAlert, Check, Loader2, Key, HelpCircle, HardHat, ClipboardCheck } from "lucide-react";
import { draftPermitStream } from "../../lib/api";

const STEP_LABEL = {
  get_connected_equipment: "Process connections (LOTO)",
  get_failure_history: "Operating hazard history",
  get_governing_clauses: "Governing safety clauses",
  get_fix_procedures: "Maintenance procedures",
  get_work_orders: "Historical work orders",
  get_documents_mentioning: "Reference documentation",
};

export default function Permits() {
  const [tag, setTag] = useState("");
  const [workDescription, setWorkDescription] = useState("");
  const [requestedBy, setRequestedBy] = useState("");
  
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState([]);
  const [streamBody, setStreamBody] = useState("");
  const [permit, setPermit] = useState(null);
  const [error, setError] = useState(null);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!tag.trim() || !workDescription.trim()) return;

    setBusy(true);
    setError(null);
    setPermit(null);
    setSteps([]);
    setStreamBody("");

    try {
      const data = await draftPermitStream(
        {
          tag: tag.toUpperCase().trim(),
          workDescription,
          requestedBy,
        },
        {
          onStep: (tool) => setSteps((s) => (s.includes(tool) ? s : [...s, tool])),
          onToken: (token) => setStreamBody((body) => body + token),
        }
      );
      setPermit(data);
    } catch (err) {
      setError("Failed to draft safety permit. Is the backend running?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="page-title flex items-center gap-2">
          <FileSignature size={22} style={{ color: "var(--blue)" }} />
          Permit-to-Work (PTW)
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Automatically construct job safety analyses, hazard identifications, and Lock-Out/Tag-Out (LOTO) boundaries using graph intelligence.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        {/* Left Side Form */}
        <div className="lg:sticky lg:top-0 lg:self-start space-y-4">
          <div className="card p-5">
            <h2 className="text-xs font-bold uppercase tracking-wider mb-4" style={{ color: "var(--text-main)" }}>
              Job Details
            </h2>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-md)" }}>
                  Asset Tag *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. P-101A"
                  value={tag}
                  onChange={(e) => setTag(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                  style={{ background: "var(--bg-panel)", borderColor: "var(--border)", color: "var(--text-main)" }}
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-md)" }}>
                  Work Description *
                </label>
                <textarea
                  required
                  placeholder="e.g. replace mechanical seal"
                  value={workDescription}
                  onChange={(e) => setWorkDescription(e.target.value)}
                  disabled={busy}
                  rows={3}
                  className="w-full rounded-xl border px-3 py-2 text-sm focus:outline-none focus:border-blue-500 resize-none"
                  style={{ background: "var(--bg-panel)", borderColor: "var(--border)", color: "var(--text-main)" }}
                />
              </div>

              <div>
                <label className="block text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--text-md)" }}>
                  Requested By
                </label>
                <input
                  type="text"
                  placeholder="e.g. tech@plant.com"
                  value={requestedBy}
                  onChange={(e) => setRequestedBy(e.target.value)}
                  disabled={busy}
                  className="w-full rounded-xl border px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                  style={{ background: "var(--bg-panel)", borderColor: "var(--border)", color: "var(--text-main)" }}
                />
              </div>

              <button
                type="submit"
                disabled={busy || !tag.trim() || !workDescription.trim()}
                className="w-full flex items-center justify-center gap-2 rounded-xl py-2.5 text-sm font-semibold text-white transition-all"
                style={{
                  background: busy ? "var(--muted-lt)" : "var(--blue)",
                  cursor: busy || !tag.trim() || !workDescription.trim() ? "not-allowed" : "pointer",
                }}
              >
                {busy ? (
                  <>
                    <Loader2 size={16} className="animate-spin" />
                    Drafting Safety...
                  </>
                ) : (
                  <>
                    <FileSignature size={16} />
                    Draft Permit
                  </>
                )}
              </button>
            </form>
          </div>
        </div>

        {/* Right Side Content */}
        <div>
          {busy && <Streaming steps={steps} body={streamBody} />}
          {error && !busy && (
            <div
              className="rounded-xl px-4 py-3 text-sm"
              style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}
            >
              {error}
            </div>
          )}
          {permit && !busy && <PermitCard permit={permit} />}
          {!permit && !busy && !error && <EmptyState />}
        </div>
      </div>
    </div>
  );
}

function Streaming({ steps, body }) {
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--muted)" }}>
          Gathering Evidence
        </h3>
        <div className="space-y-1.5">
          {steps.length === 0 && (
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
              <Loader2 size={13} className="animate-spin" style={{ color: "var(--blue)" }} />
              Querying the plant graph…
            </div>
          )}
          {steps.map((tool) => (
            <div key={tool} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-md)" }}>
              <Check size={13} style={{ color: "#16a34a" }} />
              {STEP_LABEL[tool] || tool}
            </div>
          ))}
        </div>
      </div>

      {body && (
        <div className="card p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--muted)" }}>
            <Loader2 size={11} className="animate-spin" style={{ color: "var(--blue)" }} />
            Drafting Permit Checklists
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>
            {body}
          </p>
        </div>
      )}
    </div>
  );
}

function PermitCard({ permit }) {
  const permitBadgeColors = {
    "Hot Work": { bg: "#fee2e2", text: "#991b1b", border: "#fca5a5" },
    "Confined Space Entry": { bg: "#fef3c7", text: "#92400e", border: "#fcd34d" },
    "Electrical Isolation": { bg: "#e0f2fe", text: "#0369a1", border: "#bae6fd" },
    "Cold Work": { bg: "#dcfce7", text: "#166534", border: "#bbf7d0" },
    "General Maintenance": { bg: "#f1f5f9", text: "#334155", border: "#cbd5e1" },
  };

  const badge = permitBadgeColors[permit.permit_type] || permitBadgeColors["General Maintenance"];

  return (
    <div className="space-y-5">
      {/* Header Info */}
      <div className="card p-5 flex items-center justify-between gap-4">
        <div>
          <span className="text-[10px] font-mono" style={{ color: "var(--muted)" }}>
            Permit Draft (Graph Version {permit.graph_version})
          </span>
          <h3 className="text-base font-bold mt-1" style={{ color: "var(--text-main)" }}>
            Work Permit for {permit.request.tag}
          </h3>
          <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
            Job: {permit.request.work_description}
          </p>
        </div>
        <div
          className="rounded-full px-3 py-1 text-xs font-semibold border"
          style={{ background: badge.bg, color: badge.text, borderColor: badge.border }}
        >
          {permit.permit_type}
        </div>
      </div>

      {/* Main Narrative */}
      <div className="card p-6">
        <h3 className="text-xs font-bold uppercase tracking-wider mb-3 pb-1 border-b" style={{ color: "var(--muted)", borderColor: "var(--border)" }}>
          Safety Analysis & Pre-Job Instruction
        </h3>
        <p className="whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>
          {permit.body}
        </p>
      </div>

      {/* LOTO Isolation Points */}
      <div className="card p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: "var(--text-main)" }}>
          <Key size={14} style={{ color: "var(--blue)" }} />
          Lock-Out / Tag-Out (LOTO) Boundaries
        </h3>
        {permit.isolation_points.length === 0 ? (
          <p className="text-xs italic" style={{ color: "var(--muted)" }}>No process isolation points returned from plant topology.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {permit.isolation_points.map((pt) => (
              <span
                key={pt}
                className="rounded-lg px-2.5 py-1 text-xs font-mono font-medium border"
                style={{ background: "var(--bg-card)", borderColor: "var(--border)", color: "var(--text-main)" }}
              >
                {pt}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* Hazards & PPE */}
      <div className="grid gap-5 sm:grid-cols-2">
        <div className="card p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: "var(--text-main)" }}>
            <ShieldAlert size={14} style={{ color: "#dc2626" }} />
            Identified Hazards
          </h3>
          {permit.identified_hazards.length === 0 ? (
            <p className="text-xs italic" style={{ color: "var(--muted)" }}>No hazards identified from operating / failure records.</p>
          ) : (
            <ul className="space-y-1.5">
              {permit.identified_hazards.map((h, i) => (
                <li key={i} className="text-xs flex items-start gap-2" style={{ color: "var(--text-md)" }}>
                  <span className="text-red-500 font-bold">•</span>
                  {h}
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="card p-5">
          <h3 className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-2" style={{ color: "var(--text-main)" }}>
            <HardHat size={14} style={{ color: "#eab308" }} />
            Required PPE
          </h3>
          <ul className="space-y-1.5">
            {permit.required_ppe.map((ppe, i) => (
              <li key={i} className="text-xs flex items-start gap-2" style={{ color: "var(--text-md)" }}>
                <span className="text-yellow-600 font-bold">•</span>
                {ppe}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* Governing Standards & Procedures */}
      <div className="card p-5">
        <h3 className="text-xs font-bold uppercase tracking-wider mb-4 flex items-center gap-2" style={{ color: "var(--text-main)" }}>
          <ClipboardCheck size={14} style={{ color: "var(--blue)" }} />
          Compliance Standards & Applicable SOPs
        </h3>
        <div className="space-y-3.5">
          <div>
            <h4 className="text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
              Applicable Procedures
            </h4>
            {permit.procedures_to_follow.length === 0 ? (
              <p className="text-xs italic" style={{ color: "var(--muted)" }}>No specific repair/operation procedures found in database.</p>
            ) : (
              <ul className="space-y-1.5">
                {permit.procedures_to_follow.map((proc, i) => (
                  <li key={i} className="text-xs flex items-start gap-2" style={{ color: "var(--text-md)" }}>
                    <span className="text-green-600 font-bold">•</span>
                    {proc}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <h4 className="text-[11px] font-semibold uppercase tracking-wider mb-1.5" style={{ color: "var(--muted)" }}>
              Regulatory Constraints
            </h4>
            {permit.governing_clauses.length === 0 ? (
              <p className="text-xs italic" style={{ color: "var(--muted)" }}>No governing compliance standards returned for this asset.</p>
            ) : (
              <ul className="space-y-1.5">
                {permit.governing_clauses.map((cl, i) => (
                  <li key={i} className="text-xs flex items-start gap-2" style={{ color: "var(--text-md)" }}>
                    <span className="text-blue-500 font-bold">•</span>
                    {cl}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-xl" style={{ background: "#eff6ff", border: "1px solid #bfdbfe" }}>
        <FileSignature size={20} style={{ color: "var(--blue)" }} />
      </div>
      <p className="max-w-xs text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
        Fill out the job details on the left. The Permit-to-Work draft — LOTO boundaries, PPE, and hazard analysis — will stream here.
      </p>
    </div>
  );
}

import { useState } from "react";
import { GitPullRequestArrow, Check, Loader2 } from "lucide-react";
import { assessChangeStream } from "../../lib/api";
import ProposalForm from "../../components/moc/ProposalForm";
import AssessmentCard from "../../components/moc/AssessmentCard";
import { DocumentModal } from "../../components/DocumentViewer";

// The tool names the agent emits, in plainer words for a reviewer watching.
const STEP_LABEL = {
  get_connected_equipment: "Process connections",
  get_failure_history: "Failure history",
  get_governing_clauses: "Governing clauses",
  get_documents_mentioning: "Referring documents",
  get_fix_procedures: "Fix procedures",
  get_sibling_history: "Sibling equipment",
  get_work_orders: "Work orders",
};

// /moc/assess/stream is role-gated (engineer) and rate-limited, so "couldn't
// reach the backend" is the wrong story for most of its failures - a 403 sent
// an engineer hunting a dead service when the real answer is their role.
// api.js throws Error(`assessment failed: ${status}`), so the code is in there.
function explainFailure(e) {
  const status = Number(String(e?.message ?? "").match(/\b(\d{3})\b/)?.[1]);
  if (status === 401) return "Your session expired. Sign in again.";
  if (status === 403) return "Change Impact requires the engineer role, and this account does not have it.";
  if (status === 429) return "Too many assessments in the last minute. Wait a moment and retry.";
  if (status >= 500) return `The assessment service failed (${status}). Check the agents service logs.`;
  return "Couldn't reach the assessment service. Is the backend running?";
}

export default function Moc() {
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState([]);        // tool names, in arrival order
  const [streamBody, setStreamBody] = useState("");
  const [assessment, setAssessment] = useState(null);
  const [error, setError] = useState(null);
  const [activeDoc, setActiveDoc] = useState(null);   // { docId, filename }

  async function run(proposal) {
    setBusy(true); setError(null); setAssessment(null);
    setSteps([]); setStreamBody("");
    try {
      const done = await assessChangeStream(proposal, {
        onStep: (tool) => setSteps((s) => (s.includes(tool) ? s : [...s, tool])),
        onToken: (t) => setStreamBody((b) => b + t),
      });
      // A 200 that never delivers a 'done' frame is a real failure mode - the
      // agent can die after the headers are already out. Without this branch
      // the page silently falls back to the empty state, which reads as "the
      // button did nothing" rather than "the assessment broke".
      if (!done) {
        setError("The assessment ended before it returned a result. The agents "
                 + "service likely failed mid-stream — check its logs.");
        return;
      }
      setAssessment(done);
    } catch (e) {
      setError(explainFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto h-full max-w-5xl overflow-y-auto px-6 py-6">
      <div className="mb-6">
        <h1 className="page-title flex items-center gap-2">
          <GitPullRequestArrow size={20} style={{ color: "var(--blue)" }} />
          Change Impact
        </h1>
        <p className="mt-1 text-sm" style={{ color: "var(--muted)" }}>
          Before a change is made, see what it touches — connected equipment,
          failure history, the clauses that govern it, and every document that
          would have to be revised. The plant already knows; this reads it back.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[320px_1fr]">
        <div className="lg:sticky lg:top-0 lg:self-start">
          <ProposalForm onSubmit={run} busy={busy} />
        </div>

        <div>
          {busy && <Streaming steps={steps} body={streamBody} />}
          {error && !busy && (
            <div className="rounded-xl px-4 py-3 text-sm"
              style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
              {error}
            </div>
          )}
          {assessment && !busy && (
            <AssessmentCard assessment={assessment}
              onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })} />
          )}
          {!assessment && !busy && !error && <EmptyState />}
        </div>
      </div>

      {activeDoc && (
        <DocumentModal docId={activeDoc.docId} filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)} />
      )}
    </div>
  );
}

// While the agent works: the evidence it has gathered so far (steps light up as
// they arrive), then the assessment streaming in beneath them.
function Streaming({ steps, body }) {
  return (
    <div className="space-y-4">
      <div className="card p-4">
        <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          Gathering evidence
        </h3>
        <div className="space-y-1.5">
          {steps.length === 0 && (
            <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
              <Loader2 size={13} className="animate-spin" style={{ color: "var(--blue)" }} />
              Reading the graph…
            </div>
          )}
          {steps.map((tool) => (
            <div key={tool} className="flex items-center gap-2 text-xs"
              style={{ color: "var(--text-md)" }}>
              <Check size={13} style={{ color: "#16a34a" }} />
              {STEP_LABEL[tool] || tool}
            </div>
          ))}
        </div>
      </div>

      {body && (
        <div className="card p-5">
          <h3 className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--muted)" }}>
            <Loader2 size={11} className="animate-spin" style={{ color: "var(--blue)" }} />
            Writing the assessment
          </h3>
          <p className="whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>
            {body}
          </p>
        </div>
      )}
    </div>
  );
}

function EmptyState() {
  return (
    <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-xl"
        style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
        <GitPullRequestArrow size={20} style={{ color: "var(--blue)" }} />
      </div>
      <p className="max-w-xs text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
        Describe a proposed change on the left. The assessment — what it
        affects, what argues against it, and what must be revised — appears here.
      </p>
    </div>
  );
}

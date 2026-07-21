import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  CheckCircle2, AlertTriangle, Wrench, ScrollText, FileWarning, Info, FileText,
} from "lucide-react";

// The design thesis of this whole feature, made visible: the three fact lists
// are harvested from what the graph tools actually returned, so the model
// cannot invent into them. The prose can, which is why it sits below a trust
// banner and they do not. Same reason the backend keeps them apart.
export default function AssessmentCard({ assessment: a, onOpenDoc }) {
  return (
    <div className="space-y-4">
      <TrustBanner verified={a.verified} claims={a.unverified_claims} />

      <div className="grid gap-3 sm:grid-cols-2">
        <FactList icon={Wrench} title="Affected equipment"
          items={a.affected_equipment} kind="tag" accent="#2563eb" bg="#dbeafe" />
        <FactList icon={ScrollText} title="Governing clauses"
          items={a.governing_clauses} kind="tag" accent="#92400e" bg="#fef3c7" />
      </div>

      <FactList icon={FileWarning} title="Documents to revise"
        items={a.documents_to_revise} kind="file" accent="#7c3aed" bg="#ede9fe"
        note="Every one of these refers to the asset and must be reviewed before close-out." />

      <div className="card p-5">
        <h3 className="mb-3 text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          Assessment
        </h3>
        <div className="prose prose-sm max-w-none prose-headings:font-semibold prose-headings:text-[var(--text)] prose-p:leading-relaxed prose-li:my-0.5"
          style={{ color: "var(--text-md)" }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{a.body}</ReactMarkdown>
        </div>
      </div>

      <Sources citations={a.citations} onOpenDoc={onOpenDoc} />
      <Footer proposal={a.proposal} graphVersion={a.graph_version} />
    </div>
  );
}

function Sources({ citations, onOpenDoc }) {
  if (!citations?.length) return null;
  return (
    <div className="card p-4">
      <h3 className="mb-2.5 text-[10px] font-semibold uppercase tracking-widest"
        style={{ color: "var(--muted)" }}>
        Sources — the evidence this rests on
      </h3>
      <div className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <button key={i} type="button" onClick={() => onOpenDoc?.(c.doc_id, c.filename)}
            className="flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] transition-colors"
            style={{ background: "var(--bg-subtle)", color: "var(--text-md)", border: "1px solid var(--border)" }}
            onMouseEnter={(e) => { e.currentTarget.style.borderColor = "var(--blue-mid)"; e.currentTarget.style.background = "var(--brand-light)"; }}
            onMouseLeave={(e) => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.background = "var(--bg-subtle)"; }}
            title={c.doc_id}>
            <FileText size={11} style={{ color: "var(--blue)" }} />
            <span className="font-mono">{c.filename || c.doc_id}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function TrustBanner({ verified, claims }) {
  if (verified) {
    return (
      <div className="flex items-start gap-2.5 rounded-xl px-4 py-3"
        style={{ background: "#dcfce7", border: "1px solid #86efac" }}>
        <CheckCircle2 size={15} className="mt-0.5 flex-shrink-0" style={{ color: "#16a34a" }} />
        <p className="text-xs leading-relaxed" style={{ color: "#166534" }}>
          <span className="font-semibold">Grounded.</span> Every asset and clause
          named below was pulled from the plant graph, not asserted by the model.
        </p>
      </div>
    );
  }
  return (
    <div className="flex items-start gap-2.5 rounded-xl px-4 py-3"
      style={{ background: "#fee2e2", border: "1px solid #fca5a5" }}>
      <AlertTriangle size={15} className="mt-0.5 flex-shrink-0" style={{ color: "#dc2626" }} />
      <div className="text-xs leading-relaxed" style={{ color: "#991b1b" }}>
        <span className="font-semibold">Not fully grounded.</span> Parts of the
        assessment below could not be traced to graph evidence and may be wrong:
        <span className="ml-1 font-mono">{(claims || []).join(", ")}</span>
      </div>
    </div>
  );
}

function FactList({ icon: Icon, title, items, kind, accent, bg, note }) {
  const has = items && items.length > 0;
  return (
    <div className="card p-4">
      <div className="mb-2.5 flex items-center gap-1.5">
        <Icon size={13} style={{ color: accent }} />
        <h3 className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          {title}
        </h3>
        {has && (
          <span className="ml-auto rounded-full px-1.5 text-[10px] font-bold"
            style={{ background: bg, color: accent }}>
            {items.length}
          </span>
        )}
      </div>

      {!has && (
        <p className="text-xs italic" style={{ color: "var(--muted-lt)" }}>
          None found in the graph.
        </p>
      )}

      {has && kind === "tag" && (
        <div className="flex flex-wrap gap-1.5">
          {items.map((it, i) => (
            <span key={i} className="rounded-full px-2 py-0.5 font-mono text-[11px]"
              style={{ background: bg, color: accent, border: `1px solid ${accent}22` }}>
              {it}
            </span>
          ))}
        </div>
      )}

      {has && kind === "file" && (
        <ul className="space-y-1">
          {items.map((it, i) => (
            <li key={i} className="flex items-center gap-2 text-[12px]"
              style={{ color: "var(--text-md)" }}>
              <span className="h-1 w-1 flex-shrink-0 rounded-full" style={{ background: accent }} />
              <span className="font-mono">{it}</span>
            </li>
          ))}
        </ul>
      )}

      {has && note && (
        <p className="mt-2.5 text-[10px] leading-relaxed" style={{ color: "var(--muted-lt)" }}>
          {note}
        </p>
      )}
    </div>
  );
}

function Footer({ proposal, graphVersion }) {
  return (
    <div className="rounded-xl px-4 py-3"
      style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
      <div className="flex items-start gap-2">
        <Info size={13} className="mt-0.5 flex-shrink-0" style={{ color: "var(--muted)" }} />
        <p className="text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>
          This is an impact assessment, not an approval. A competent person signs
          off a change; this is the evidence they weigh. Reasoned against
          graph version <span className="font-mono">{graphVersion}</span> — a
          later change to the plant is a different assessment.
        </p>
      </div>
    </div>
  );
}

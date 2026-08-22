import { FileText, PencilLine, BookOpen } from "lucide-react";
import { DocumentViewer, DocumentModal } from "../DocumentViewer";

export default function EvidencePanel({ answer, activeDoc, onSelect, onClose }) {
  const allCitations = dedupe(answer?.citations || []);

  // This column is hidden below lg, but the answer's inline citations are not -
  // they still call onCite, which set activeDoc and then had nowhere to render
  // it, so on a phone tapping a source did visibly nothing. Same document,
  // opened over the conversation instead of beside it.
  const sheet = activeDoc ? (
    <div className="lg:hidden">
      <DocumentModal docId={activeDoc} filename={nameFor(allCitations, activeDoc)}
        onClose={onClose} />
    </div>
  ) : null;

  if (!answer) {
    return (
      <>
      {sheet}
      <aside
        className="hidden lg:flex w-72 shrink-0 flex-col items-center justify-center p-6 text-center"
        style={{ borderLeft: "1px solid var(--border)", background: "var(--bg-surface)" }}
      >
        <div className="mb-3 grid h-12 w-12 place-items-center rounded-xl"
          style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
          <BookOpen size={20} style={{ color: "var(--blue)" }} />
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
          Ask a question — its sources and reasoning chain appear here.
        </p>
      </aside>
      </>
    );
  }

  const citations = allCitations;
  // a document somebody has overturned must not sit in this list looking as
  // clean as the ones nobody has challenged
  const corrected = new Map((answer.corrections || []).map(c => [c.doc_id, c]));

  return (
    <>
    {sheet}
    <aside
      className="hidden lg:flex w-72 shrink-0 flex-col"
      style={{ borderLeft: "1px solid var(--border)", background: "var(--bg-surface)" }}
    >
      {activeDoc ? (
        <DocumentViewer docId={activeDoc} filename={nameFor(citations, activeDoc)}
          onClose={onClose} />
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <div className="mb-4 flex items-center justify-between">
            <h3 className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--muted)" }}>
              Sources
            </h3>
            <span className="badge badge-blue">{citations.length}</span>
          </div>

          <div className="space-y-2">
            {citations.map((c, i) => (
              <SourceCard key={i} citation={c} correction={corrected.get(c.doc_id)}
                onSelect={onSelect} />
            ))}
            {!citations.length && (
              <p className="py-6 text-center text-xs" style={{ color: "var(--muted-lt)" }}>No sources for this answer.</p>
            )}
          </div>
        </div>
      )}
    </aside>
    </>
  );
}

function SourceCard({ citation: c, correction, onSelect }) {
  const flagged = Boolean(correction);
  return (
    <div className="overflow-hidden rounded-xl"
      style={{ background: "var(--bg-panel)",
               border: `1px solid ${flagged ? "#fcd34d" : "var(--border)"}`,
               boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}>
      <button type="button" onClick={() => onSelect?.(c.doc_id)}
        className="block w-full p-3 text-left transition-colors duration-150"
        onMouseEnter={e => { e.currentTarget.style.background = "var(--bg-subtle)"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "transparent"; }}
      >
        <div className="flex items-center gap-2">
          <div className="grid h-6 w-6 flex-shrink-0 place-items-center rounded-md"
            style={{ background: flagged ? "#fef3c7" : "var(--brand-light)" }}>
            {flagged
              ? <PencilLine size={11} style={{ color: "#92400e" }} />
              : <FileText size={11} style={{ color: "var(--blue)" }} />}
          </div>
          <span className="tag flex-1 truncate text-[11px]" title={c.doc_id}>
            {c.filename || c.doc_id}
          </span>
          {c.page != null && (
            <span className="rounded px-1.5 py-0.5 text-[10px]"
              style={{ background: "var(--bg-subtle)", color: "var(--muted)" }}>
              p{c.page}
            </span>
          )}
        </div>
        {c.snippet && (
          <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed"
            style={{ color: "var(--muted)", opacity: flagged ? 0.6 : 1 }}>
            {c.snippet}
          </p>
        )}
      </button>

      {flagged && (
        <button type="button" onClick={() => onSelect?.(correction.correction_id)}
          className="block w-full px-3 py-2 text-left"
          style={{ background: "#fffbeb", borderTop: "1px solid #fcd34d" }}
          title="Open the correction record">
          <span className="text-[9px] font-semibold uppercase tracking-widest"
            style={{ color: "#92400e" }}>
            Corrected by {correction.author}
          </span>
          <p className="mt-0.5 text-[11px] leading-relaxed" style={{ color: "#78350f" }}>
            {correction.text}
          </p>
        </button>
      )}
    </div>
  );
}

function nameFor(citations, docId) {
  return citations.find(c => c.doc_id === docId)?.filename;
}

function dedupe(citations) {
  const seen = new Set();
  return citations.filter(c => { const k = `${c.doc_id}:${c.page}`; if (seen.has(k)) return false; seen.add(k); return true; });
}

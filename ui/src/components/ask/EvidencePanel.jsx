import { useEffect, useState } from "react";
import { ExternalLink, FileText, X, BookOpen } from "lucide-react";
import { fetchDocumentUrl } from "../../lib/api";

// The document endpoint needs the JWT, which an <iframe src> can't send, so
// the bytes are fetched with auth and shown from a blob URL (revoked on
// close so we don't leak object URLs as the user clicks through citations).
function useDocumentBlob(docId) {
  const [url, setUrl] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!docId) return;
    let revoked = false;
    let objectUrl = null;
    setUrl(null);
    setError(null);

    fetchDocumentUrl(docId)
      .then((u) => {
        if (revoked) return URL.revokeObjectURL(u);
        objectUrl = u;
        setUrl(u);
      })
      .catch((e) => setError(e.message));

    return () => {
      revoked = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [docId]);

  return { url, error };
}

export default function EvidencePanel({ answer, activeDoc, onSelect, onClose }) {
  if (!answer) {
    return (
      <aside
        className="hidden lg:flex w-72 shrink-0 flex-col items-center justify-center p-6 text-center"
        style={{ borderLeft: "1px solid var(--border)", background: "var(--bg-surface)" }}
      >
        <div className="mb-3 grid h-12 w-12 place-items-center rounded-xl"
          style={{ background: "#dbeafe", border: "1px solid #bfdbfe" }}>
          <BookOpen size={20} style={{ color: "var(--blue)" }} />
        </div>
        <p className="text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
          Ask a question — its sources and reasoning chain appear here.
        </p>
      </aside>
    );
  }

  const citations = dedupe(answer.citations || []);

  return (
    <aside
      className="hidden lg:flex w-72 shrink-0 flex-col"
      style={{ borderLeft: "1px solid var(--border)", background: "var(--bg-surface)" }}
    >
      {activeDoc ? (
        <SourceViewer docId={activeDoc} onClose={onClose} />
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
              <button key={i} type="button" onClick={() => onSelect?.(c.doc_id)}
                className="block w-full rounded-xl p-3 text-left transition-all duration-150"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", boxShadow: "0 1px 2px rgba(0,0,0,0.03)" }}
                onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--blue-mid)"; e.currentTarget.style.boxShadow = "0 2px 8px rgba(37,99,235,0.06)"; }}
                onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "0 1px 2px rgba(0,0,0,0.03)"; }}
              >
                <div className="flex items-center gap-2">
                  <div className="grid h-6 w-6 flex-shrink-0 place-items-center rounded-md"
                    style={{ background: "#dbeafe" }}>
                    <FileText size={11} style={{ color: "var(--blue)" }} />
                  </div>
                  <span className="tag flex-1 truncate text-[11px]">{c.doc_id}</span>
                  {c.page != null && (
                    <span className="rounded px-1.5 py-0.5 text-[10px]"
                      style={{ background: "var(--bg-subtle)", color: "var(--muted)" }}>
                      p{c.page}
                    </span>
                  )}
                </div>
                {c.snippet && (
                  <p className="mt-2 line-clamp-3 text-[11px] leading-relaxed" style={{ color: "var(--muted)" }}>
                    {c.snippet}
                  </p>
                )}
              </button>
            ))}
            {!citations.length && (
              <p className="py-6 text-center text-xs" style={{ color: "var(--muted-lt)" }}>No sources for this answer.</p>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function SourceViewer({ docId, onClose }) {
  const { url, error } = useDocumentBlob(docId);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-panel)" }}>
        <span className="tag flex-1 truncate text-xs">{docId}</span>
        <button onClick={onClose} className="btn-ghost px-1.5 py-1"><X size={14} /></button>
      </div>

      {error ? (
        <div className="flex-1 p-4 text-xs" style={{ color: "var(--danger)" }}>
          Couldn't load this source: {error}
        </div>
      ) : url ? (
        <iframe title="source" src={url}
          className="min-h-0 flex-1 bg-[var(--bg-panel)]" />
      ) : (
        <div className="flex-1 p-4 text-xs" style={{ color: "var(--muted)" }}>
          Loading source…
        </div>
      )}

      {url && (
        <a href={url} target="_blank" rel="noreferrer"
          className="flex items-center gap-1.5 px-4 py-2.5 text-xs font-medium transition-colors"
          style={{ borderTop: "1px solid var(--border)", color: "var(--blue)", background: "var(--bg-panel)" }}>
          Open full document <ExternalLink size={11} />
        </a>
      )}
    </div>
  );
}

function dedupe(citations) {
  const seen = new Set();
  return citations.filter(c => { const k = `${c.doc_id}:${c.page}`; if (seen.has(k)) return false; seen.add(k); return true; });
}

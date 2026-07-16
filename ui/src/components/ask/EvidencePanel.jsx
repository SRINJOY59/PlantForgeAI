import { ExternalLink, FileText, X } from "lucide-react";
import { documentUrl } from "../../lib/api";

// The trust surface: the citations behind the focused answer, and a click
// opens the original document.
export default function EvidencePanel({ answer, activeDoc, onClose }) {
  if (!answer) {
    return (
      <aside className="hidden w-80 shrink-0 border-l border-gray-200 p-5 text-sm muted dark:border-slate-800 lg:block">
        Ask a question — its sources and the reasoning behind it appear here.
      </aside>
    );
  }

  const citations = dedupe(answer.citations || []);

  return (
    <aside className="hidden w-80 shrink-0 flex-col border-l border-gray-200 dark:border-slate-800 lg:flex">
      {activeDoc ? (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="flex items-center justify-between border-b border-gray-200 px-4 py-2.5 dark:border-slate-800">
            <span className="tag truncate text-sm">{activeDoc}</span>
            <button onClick={onClose} className="btn-ghost px-1">
              <X size={16} />
            </button>
          </div>
          <iframe
            title="source"
            src={documentUrl(activeDoc)}
            className="min-h-0 flex-1 bg-white"
          />
          <a
            href={documentUrl(activeDoc)}
            target="_blank"
            rel="noreferrer"
            className="flex items-center gap-1.5 border-t border-gray-200 px-4 py-2 text-xs text-steel-600 dark:border-slate-800"
          >
            Open full document <ExternalLink size={12} />
          </a>
        </div>
      ) : (
        <div className="min-h-0 flex-1 overflow-y-auto p-4">
          <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide muted">
            Sources ({citations.length})
          </h3>
          <div className="space-y-2">
            {citations.map((c, i) => (
              <div key={i} className="surface rounded-lg p-3">
                <div className="flex items-center gap-2">
                  <FileText size={14} className="text-steel-600" />
                  <span className="tag truncate text-xs">{c.doc_id}</span>
                  {c.page != null && (
                    <span className="text-[11px] muted">p{c.page}</span>
                  )}
                </div>
                {c.snippet && (
                  <p className="mt-1.5 line-clamp-3 text-xs muted">{c.snippet}</p>
                )}
              </div>
            ))}
            {!citations.length && (
              <p className="text-sm muted">No sources for this answer.</p>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}

function dedupe(citations) {
  const seen = new Set();
  return citations.filter((c) => {
    const k = `${c.doc_id}:${c.page}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  });
}

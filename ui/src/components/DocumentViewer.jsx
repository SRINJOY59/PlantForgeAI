import { useEffect, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import { fetchDocumentUrl } from "../lib/api";

// The document endpoint needs the JWT, which an <iframe src> can't send, so the
// bytes are fetched with auth and shown from a blob URL (revoked on close so we
// don't leak object URLs as the user clicks through citations). Shared: Ask's
// evidence panel and the MOC assessment both open sources the same way.
export function useDocumentBlob(docId) {
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

// The panel body: header (name), the framed document, an open-in-tab link.
export function DocumentViewer({ docId, filename, onClose }) {
  const { url, error } = useDocumentBlob(docId);
  const label = filename || docId;

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center gap-2 px-4 py-3"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-panel)" }}>
        <span className="flex-1 truncate text-xs font-medium" style={{ color: "var(--text)" }}
          title={docId}>
          {label}
        </span>
        <button onClick={onClose} className="btn-ghost px-1.5 py-1"><X size={14} /></button>
      </div>

      {error ? (
        <div className="flex-1 p-4 text-xs" style={{ color: "var(--danger)" }}>
          Couldn't load this source: {error}
        </div>
      ) : url ? (
        <iframe title="source" src={url} className="min-h-0 flex-1 bg-[var(--bg-panel)]" />
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

// A centered overlay wrapping the viewer, for pages with no evidence sidebar
// (MOC). Click the backdrop or press Escape to close.
export function DocumentModal({ docId, filename, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!docId) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(15,23,42,0.55)" }}
      onClick={onClose}>
      <div className="flex h-[85vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl"
        style={{ background: "var(--bg-panel)", boxShadow: "0 20px 60px rgba(0,0,0,0.35)" }}
        onClick={(e) => e.stopPropagation()}>
        <DocumentViewer docId={docId} filename={filename} onClose={onClose} />
      </div>
    </div>
  );
}

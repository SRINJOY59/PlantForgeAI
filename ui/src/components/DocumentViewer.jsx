import { useEffect, useState } from "react";
import { ExternalLink, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchDocumentUrl } from "../lib/api";

// The document endpoint needs the JWT, which an <iframe src> can't send, so the
// bytes are fetched with auth and shown from a blob URL (revoked on close so we
// don't leak object URLs as the user clicks through citations). Shared: Ask's
// evidence panel and the MOC assessment both open sources the same way.
export function useDocumentBlob(docId) {
  const [url, setUrl] = useState(null);
  const [name, setName] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!docId) return;
    let cancelled = false;
    setUrl(null);
    setName(null);
    setError(null);

    fetchDocumentUrl(docId)
      .then(({ url: u, filename }) => {
        if (cancelled) return;
        setUrl(u);
        setName(filename);
      })
      .catch((e) => { if (!cancelled) setError(e.message); });

    return () => { cancelled = true; };
  }, [docId]);

  return { url, error, filename: name };
}

// Markdown and the other text formats are served as text/plain, which an
// iframe shows as raw source - "## Heading" instead of a heading. For those we
// read the text out of the blob and render it: markdown properly, other text in
// a monospace pre. Binary sources (pdf, svg, images) stay in the iframe, which
// is what a browser renders well.
const MARKDOWN = /\.(md|markdown)$/i;
const PLAINTEXT = /\.(txt|csv|tsv|log|eml)$/i;

function useBlobText(url, enabled) {
  const [text, setText] = useState(null);
  useEffect(() => {
    if (!url || !enabled) { setText(null); return; }
    let live = true;
    fetch(url).then((r) => r.text()).then((t) => { if (live) setText(t); });
    return () => { live = false; };
  }, [url, enabled]);
  return text;
}

// The panel body: header (name), the rendered document, an open-in-tab link.
export function DocumentViewer({ docId, filename, onClose }) {
  const { url, error, filename: resolved } = useDocumentBlob(docId);
  // Prefer the name the citation carried, fall back to the one storage knows,
  // and only then to the hash. This is not just cosmetic: the render mode is
  // chosen by extension below, so a doc_id with no ".md" on it sent markdown
  // to the iframe, which shows raw source instead of a rendered document.
  const label = filename || resolved || docId;
  const isMarkdown = MARKDOWN.test(label);
  const isText = isMarkdown || PLAINTEXT.test(label);
  const text = useBlobText(url, isText);

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
      ) : !url || (isText && text === null) ? (
        <div className="flex-1 p-4 text-xs" style={{ color: "var(--muted)" }}>
          Loading source…
        </div>
      ) : isMarkdown ? (
        <div className="prose prose-sm min-h-0 max-w-none flex-1 overflow-y-auto p-5 dark:prose-invert prose-headings:font-semibold prose-headings:text-[var(--text)] prose-p:leading-relaxed prose-td:border prose-th:border"
          style={{ color: "var(--text-md)" }}>
          {/* default renderer escapes raw HTML, so an uploaded doc can't inject
              script into the app - the safe way to show an untrusted source */}
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
        </div>
      ) : isText ? (
        <pre className="min-h-0 flex-1 overflow-auto p-4 text-[11px] leading-relaxed"
          style={{ color: "var(--text-md)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
          {text}
        </pre>
      ) : (
        // sandbox with nothing allowed: a binary source is still shown, but an
        // uploaded HTML or scripted SVG cannot run script, submit a form or
        // open a popup. This is the teeth behind viewing untrusted documents.
        <iframe title="source" src={url} sandbox=""
          className="min-h-0 flex-1 bg-[var(--bg-panel)]" />
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

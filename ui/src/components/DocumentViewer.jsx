import { useEffect, useState, useMemo } from "react";
import { ExternalLink, X, Copy, Check, FileText, Download, ZoomIn, ZoomOut, Maximize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fetchDocumentBlob } from "../lib/api";

export function useDocumentBlob(docId) {
  const [data, setData] = useState({ url: null, filename: null, text: null, error: null, loading: false });

  useEffect(() => {
    if (!docId) {
      setData({ url: null, filename: null, text: null, error: null, loading: false });
      return;
    }

    let cancelled = false;
    let createdUrl = null;
    setData(prev => ({ ...prev, loading: true, error: null }));

    fetchDocumentBlob(docId)
      .then((res) => {
        if (cancelled) {
          if (res.url) URL.revokeObjectURL(res.url);
          return;
        }
        createdUrl = res.url;
        setData({
          url: res.url,
          filename: res.filename,
          text: res.text,
          contentType: res.contentType,
          error: null,
          loading: false,
        });
      })
      .catch((e) => {
        if (!cancelled) {
          setData({ url: null, filename: null, text: null, error: e.message || "Failed to load document", loading: false });
        }
      });

    return () => {
      cancelled = true;
      if (createdUrl) {
        URL.revokeObjectURL(createdUrl);
      }
    };
  }, [docId]);

  return data;
}

const MARKDOWN = /\.(md|markdown)$/i;
const CSV_EXT = /\.(csv|tsv)$/i;
const IMAGE_EXT = /\.(png|jpe?g|webp|gif|svg)$/i;
const PDF_EXT = /\.pdf$/i;

function SimpleCsvTable({ text }) {
  const rows = useMemo(() => {
    if (!text) return [];
    return text.trim().split("\n").map(line => {
      // Split by comma or tab (respecting simple quotes)
      const delimiter = line.includes("\t") ? "\t" : ",";
      return line.split(delimiter).map(cell => cell.trim().replace(/^["']|["']$/g, ""));
    });
  }, [text]);

  if (rows.length === 0) return null;
  const headers = rows[0];
  const body = rows.slice(1);

  return (
    <div className="overflow-x-auto rounded-lg border border-[var(--border)]" style={{ background: "var(--bg-surface)" }}>
      <table className="w-full text-left text-xs border-collapse">
        <thead>
          <tr style={{ background: "var(--bg-subtle)", borderBottom: "2px solid var(--border)" }}>
            {headers.map((h, i) => (
              <th key={i} className="px-3 py-2.5 font-semibold text-[var(--text)] whitespace-nowrap">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rIdx) => (
            <tr
              key={rIdx}
              className="border-b border-[var(--border)] transition-colors hover:bg-[var(--bg-subtle)]"
              style={{ background: rIdx % 2 === 0 ? "var(--bg-panel)" : "var(--bg-surface)" }}
            >
              {row.map((cell, cIdx) => (
                <td key={cIdx} className="px-3 py-2 text-[var(--text-md)] font-mono text-[11px] whitespace-nowrap">
                  {cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function DocumentViewer({ docId, filename, onClose }) {
  const { url, error, filename: resolved, text, loading } = useDocumentBlob(docId);
  const [copied, setCopied] = useState(false);
  const [imageZoom, setImageZoom] = useState(1);

  const label = filename || resolved || docId;
  const isMarkdown = MARKDOWN.test(label);
  const isCsv = CSV_EXT.test(label);
  const isImage = IMAGE_EXT.test(label);
  const isPdf = PDF_EXT.test(label);
  const isPlainText = !isMarkdown && !isCsv && !isImage && !isPdf && text !== null;

  const handleCopyText = () => {
    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col h-full overflow-hidden" style={{ background: "var(--bg-panel)" }}>
      {/* Header */}
      <div className="flex items-center justify-between gap-3 px-5 py-3.5"
        style={{ borderBottom: "1px solid var(--border)", background: "var(--bg-surface)" }}>
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="grid h-7 w-7 flex-shrink-0 place-items-center rounded-lg"
            style={{ background: "var(--brand-light)", color: "var(--blue)" }}>
            <FileText size={15} />
          </div>
          <div className="min-w-0">
            <h3 className="truncate text-xs font-semibold" style={{ color: "var(--text)" }} title={label}>
              {label}
            </h3>
            <p className="font-mono text-[10px] truncate" style={{ color: "var(--muted)" }}>
              ID: {String(docId || "").replace(/^doc:/, "")}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          {text && (
            <button
              onClick={handleCopyText}
              title="Copy text"
              className="flex items-center gap-1 px-2 py-1 rounded text-[11px] font-medium transition-colors"
              style={{ background: "var(--bg-subtle)", color: "var(--text-md)", border: "1px solid var(--border)" }}
            >
              {copied ? <Check size={12} className="text-emerald-500" /> : <Copy size={12} />}
              {copied ? "Copied" : "Copy"}
            </button>
          )}

          {url && (
            <a
              href={url}
              target="_blank"
              rel="noreferrer"
              title="Open in new window"
              className="p-1.5 rounded transition-colors hover:bg-[var(--bg-subtle)]"
              style={{ color: "var(--muted)" }}
            >
              <ExternalLink size={14} />
            </a>
          )}

          {onClose && (
            <button
              onClick={onClose}
              className="p-1.5 rounded transition-colors hover:bg-[var(--bg-subtle)]"
              style={{ color: "var(--muted)" }}
            >
              <X size={16} />
            </button>
          )}
        </div>
      </div>

      {/* Content Area */}
      <div className="flex-1 min-h-0 overflow-y-auto p-5">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 text-[var(--muted)]">
            <div className="h-6 w-6 animate-spin rounded-full border-2 border-[var(--blue)] border-t-transparent mb-3" />
            <span className="text-xs font-medium">Loading document content…</span>
          </div>
        ) : error ? (
          <div className="rounded-xl border border-rose-200 bg-rose-50/60 p-5 text-center text-xs dark:bg-rose-950/20 dark:border-rose-800">
            <p className="font-semibold text-rose-700 dark:text-rose-400 mb-1">⚠️ Couldn't load document</p>
            <p className="text-rose-600 dark:text-rose-300">{error}</p>
          </div>
        ) : isMarkdown && text ? (
          <div className="prose prose-sm max-w-none dark:prose-invert prose-headings:font-semibold prose-headings:text-[var(--text)] prose-p:leading-relaxed prose-pre:bg-[var(--bg-surface)] prose-pre:border prose-pre:border-[var(--border)] prose-table:border prose-table:border-[var(--border)] prose-th:bg-[var(--bg-subtle)] prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2"
            style={{ color: "var(--text-md)" }}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
          </div>
        ) : isCsv && text ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between text-xs text-[var(--muted)]">
              <span>Tabular Document View</span>
              <span>{text.trim().split("\n").length} rows</span>
            </div>
            <SimpleCsvTable text={text} />
          </div>
        ) : isImage && url ? (
          <div className="flex flex-col items-center justify-center py-4">
            <div className="flex items-center gap-2 mb-3">
              <button
                onClick={() => setImageZoom(z => Math.max(0.5, z - 0.25))}
                className="btn-ghost p-1 rounded border border-[var(--border)]"
                title="Zoom Out"
              >
                <ZoomOut size={14} />
              </button>
              <span className="text-xs font-mono text-[var(--muted)]">{Math.round(imageZoom * 100)}%</span>
              <button
                onClick={() => setImageZoom(z => Math.min(3, z + 0.25))}
                className="btn-ghost p-1 rounded border border-[var(--border)]"
                title="Zoom In"
              >
                <ZoomIn size={14} />
              </button>
              <button
                onClick={() => setImageZoom(1)}
                className="btn-ghost p-1 rounded border border-[var(--border)] text-[10px]"
                title="Reset Zoom"
              >
                100%
              </button>
            </div>
            <div className="max-w-full overflow-auto rounded-lg border border-[var(--border)] p-2"
              style={{ background: "var(--bg-surface)" }}>
              <img
                src={url}
                alt={label}
                className="max-w-full transition-transform duration-200"
                style={{ transform: `scale(${imageZoom})`, transformOrigin: "center top" }}
              />
            </div>
          </div>
        ) : isPdf && url ? (
          <iframe
            title={label}
            src={url}
            className="w-full h-full min-h-[500px] rounded-lg border border-[var(--border)] bg-[var(--bg-surface)]"
          />
        ) : text ? (
          <pre className="overflow-auto rounded-lg p-4 font-mono text-xs leading-relaxed border border-[var(--border)]"
            style={{ background: "var(--bg-surface)", color: "var(--text-md)", whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {text}
          </pre>
        ) : url ? (
          <iframe
            title={label}
            src={url}
            sandbox="allow-same-origin"
            className="w-full h-full min-h-[500px] rounded-lg border border-[var(--border)] bg-[var(--bg-surface)]"
          />
        ) : (
          <div className="text-center py-10 text-xs text-[var(--muted)]">
            No preview available for this document format.
          </div>
        )}
      </div>

      {/* Footer */}
      {url && (
        <div className="flex items-center justify-between px-5 py-2.5 text-xs font-medium"
          style={{ borderTop: "1px solid var(--border)", background: "var(--bg-surface)" }}>
          <span className="text-[11px] text-[var(--muted)]">
            Format: {label.split(".").pop()?.toUpperCase() || "FILE"}
          </span>
          <a
            href={url}
            download={label}
            className="flex items-center gap-1.5 text-[var(--blue)] hover:underline"
          >
            <Download size={13} /> Download File
          </a>
        </div>
      )}
    </div>
  );
}

export function DocumentModal({ docId, filename, onClose }) {
  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  if (!docId) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 backdrop-blur-sm"
      style={{ background: "rgba(15,23,42,0.65)" }}
      onClick={onClose}
    >
      <div
        className="flex h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-[var(--border)] shadow-2xl animate-in fade-in zoom-in-95 duration-150"
        style={{ background: "var(--bg-panel)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <DocumentViewer docId={docId} filename={filename} onClose={onClose} />
      </div>
    </div>
  );
}

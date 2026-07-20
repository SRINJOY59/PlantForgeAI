import React, { useState } from "react";
import { FilePieChart, FileDown, Loader2, RefreshCw } from "lucide-react";
import { generateReport, documentUrl } from "../api";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

export function ReportGenerator() {
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState(null);
  const [error, setError] = useState(null);

  async function handleGenerate(e) {
    e.preventDefault();
    if (!tag.trim()) return;

    setBusy(true);
    setError(null);
    setReport(null);

    try {
      const data = await generateReport({ tag: tag.toUpperCase().trim() });
      setReport(data);
    } catch (err) {
      setError("Failed to generate report. Make sure the backend is active and the tag is valid.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid gap-6">
      {/* Input Form */}
      <div className="card p-5">
        <form onSubmit={handleGenerate} className="flex flex-col sm:flex-row gap-4 items-end">
          <div className="flex-1">
            <label className="block text-xs font-semibold uppercase tracking-wider mb-2" style={{ color: "var(--text-md)" }}>
              Equipment / Instrument Tag
            </label>
            <input
              type="text"
              value={tag}
              onChange={(e) => setTag(e.target.value)}
              placeholder="e.g. P-101A"
              disabled={busy}
              className="w-full rounded-xl border px-3.5 py-2.5 text-sm transition-all focus:outline-none"
              style={{
                background: "var(--bg-panel)",
                borderColor: "var(--border)",
                color: "var(--text)",
              }}
            />
          </div>
          <button
            type="submit"
            disabled={busy || !tag.trim()}
            className="flex items-center justify-center gap-2 rounded-xl px-5 py-2.5 text-sm font-semibold text-white transition-all w-full sm:w-auto"
            style={{
              background: busy ? "var(--muted-lt)" : "var(--blue)",
              cursor: busy || !tag.trim() ? "not-allowed" : "pointer",
            }}
          >
            {busy ? (
              <>
                <Loader2 size={16} className="animate-spin" />
                Generating Report...
              </>
            ) : (
              <>
                <RefreshCw size={16} />
                Compile Report
              </>
            )}
          </button>
        </form>
      </div>

      {/* Error State */}
      {error && (
        <div
          className="rounded-xl px-4 py-3 text-sm"
          style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}
        >
          {error}
        </div>
      )}

      {/* Loading State */}
      {busy && (
        <div className="card flex flex-col items-center justify-center py-16 text-center">
          <Loader2 size={36} className="animate-spin mb-4" style={{ color: "var(--blue)" }} />
          <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>
            Analyzing plant topology & operational records...
          </p>
          <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>
            Querying failure history, drafting narrative, and rendering PDF report.
          </p>
        </div>
      )}

      {/* Report Display */}
      {report && (
        <div className="space-y-4">
          {/* Download Card */}
          <div
            className="card p-4 flex flex-col sm:flex-row items-center justify-between gap-4"
            style={{ borderLeft: "4px solid var(--blue)" }}
          >
            <div>
              <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>
                PDF Report Generated Successfully
              </h3>
              <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
                Contains verified citations, tabular data, and dynamic failure frequency plots.
              </p>
            </div>
            <a
              href={documentUrl(report.doc_id)}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-2 rounded-xl border px-4 py-2 text-xs font-semibold transition-all hover:opacity-80"
              style={{
                borderColor: "var(--border)",
                background: "var(--bg-subtle)",
                color: "var(--text)",
              }}
            >
              <FileDown size={14} style={{ color: "var(--blue)" }} />
              Download PDF Report
            </a>
          </div>

          {/* Markdown Preview */}
          <div className="card p-6">
            <h2 className="text-xs font-semibold uppercase tracking-wider mb-4 pb-2 border-b" style={{ color: "var(--muted)", borderColor: "var(--border)" }}>
              Report Preview (Markdown)
            </h2>
            <div className="prose prose-sm max-w-none dark:prose-invert" style={{ color: "var(--text)" }}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {report.markdown}
              </ReactMarkdown>
            </div>
          </div>
        </div>
      )}

      {/* Empty State */}
      {!report && !busy && !error && (
        <div className="card flex flex-col items-center gap-3 px-6 py-16 text-center">
          <div
            className="grid h-12 w-12 place-items-center rounded-xl"
            style={{ background: "var(--blue-light)", border: "1px solid var(--blue-mid)" }}
          >
            <FilePieChart size={20} style={{ color: "var(--blue)" }} />
          </div>
          <p className="max-w-xs text-xs leading-relaxed" style={{ color: "var(--muted)" }}>
            Enter an asset tag above (e.g. <b>P-101A</b>) to compile the full
            historical asset analysis.
          </p>
        </div>
      )}
    </div>
  );
}

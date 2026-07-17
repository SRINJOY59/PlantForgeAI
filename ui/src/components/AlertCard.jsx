import { AlertTriangle, ExternalLink, Globe, ShieldAlert, Wrench } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const SEVERITY = {
  critical: { border: "#fca5a5", bg: "#fff1f2", iconBg: "#fee2e2", color: "#991b1b", chipBg: "#fee2e2" },
  warning:  { border: "#fcd34d", bg: "#fffbeb", iconBg: "#fef3c7", color: "#92400e", chipBg: "#fef3c7" },
  info:     { border: "var(--blue-mid)", bg: "#f0f9ff", iconBg: "#dbeafe", color: "#1d4ed8", chipBg: "#dbeafe" },
};

// Alerts whose evidence is somebody else's web page rather than a document we
// hold. Kept as a set because the distinction drives the UI, not the styling.
export const WEB_KINDS = new Set(["standard_revision"]);

const ICONS = {
  compliance: ShieldAlert,
  standard_revision: Globe,
  failure_pattern: Wrench,
};

export default function AlertCard({ alert }) {
  const s = SEVERITY[alert.severity] ?? SEVERITY.info;
  const Icon = ICONS[alert.kind] ?? Wrench;
  const fromWeb = WEB_KINDS.has(alert.kind);

  return (
    <div
      className="animate-slide-up rounded-xl p-4 transition-all duration-150"
      style={{
        background: "var(--bg-panel)",
        border: "1px solid var(--border)",
        borderLeft: `3px solid ${s.border}`,
        boxShadow: "0 1px 3px rgba(0,0,0,0.04)",
      }}
      onMouseEnter={e => { e.currentTarget.style.boxShadow = "0 4px 12px rgba(0,0,0,0.06)"; e.currentTarget.style.borderTopColor = s.border; }}
      onMouseLeave={e => { e.currentTarget.style.boxShadow = "0 1px 3px rgba(0,0,0,0.04)"; }}
    >
      <div className="flex items-center gap-3">
        <div className="grid h-8 w-8 flex-shrink-0 place-items-center rounded-lg" style={{ background: s.iconBg }}>
          <Icon size={15} style={{ color: s.color }} />
        </div>
        <span className="flex-1 text-sm font-semibold" style={{ color: "var(--text)" }}>{alert.title}</span>
        <span className="badge" style={{ background: s.chipBg, color: s.color }}>
          {alert.severity ?? "info"}
        </span>
      </div>

      {alert.equipment && (
        <div className="mt-2 font-mono text-[11px]" style={{ color: "var(--muted)" }}>📍 {alert.equipment}</div>
      )}

      <div className="mt-2.5 text-sm leading-relaxed prose prose-sm max-w-none" style={{ color: "var(--muted)" }}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{alert.body}</ReactMarkdown>
      </div>

      {/* verified=false means two different things. On a plant alert the agent
          named something its evidence didn't support - a mistake. On a web
          alert it is simply what the source is, and saying "unverified claim"
          there would read as a fault rather than a fact. */}
      {alert.verified === false && !fromWeb && (
        <div className="mt-3 flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-[11px]"
          style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
          <AlertTriangle size={11} /> Unverified — some claims not fully grounded in evidence
        </div>
      )}

      {alert.citations?.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--muted-lt)" }}>
            {fromWeb ? "Your documents that cite this standard" : "Sources"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {alert.citations.map((c, i) => (
              <span key={i} className="rounded-full px-2 py-0.5 font-mono text-[10px]"
                style={{ background: "#dbeafe", color: "#1d4ed8", border: "1px solid #bfdbfe" }}>
                {c.doc_id}
              </span>
            ))}
          </div>
        </div>
      )}

      {alert.web_sources?.length > 0 && (
        <div className="mt-3">
          <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--muted-lt)" }}>
            Read on the web
          </p>
          <div className="flex flex-col gap-1">
            {alert.web_sources.map((w, i) => (
              <a key={i} href={w.url} target="_blank" rel="noreferrer noopener"
                className="flex items-center gap-1.5 text-[11px] hover:underline"
                style={{ color: "var(--blue)" }}>
                <ExternalLink size={10} className="flex-shrink-0" />
                <span className="truncate">{w.title || w.url}</span>
              </a>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

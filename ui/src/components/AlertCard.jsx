import { AlertTriangle, ClipboardList, ExternalLink, Globe, ShieldAlert, Wrench } from "lucide-react";
import { Link } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const SEVERITY = {
  critical: { border: "#fca5a5", bg: "#fff1f2", iconBg: "#fee2e2", color: "#991b1b", chipBg: "#fee2e2" },
  warning:  { border: "#fcd34d", bg: "#fffbeb", iconBg: "#fef3c7", color: "#92400e", chipBg: "#fef3c7" },
  info:     { border: "var(--blue-mid)", bg: "#f0f9ff", iconBg: "var(--brand-light)", color: "var(--brand-dark)", chipBg: "var(--brand-light)" },
};

// Alerts whose evidence is somebody else's web page rather than a document we
// hold. Kept as a set because the distinction drives the UI, not the styling.
export const WEB_KINDS = new Set(["standard_revision"]);

const ICONS = {
  compliance: ShieldAlert,
  standard_revision: Globe,
  failure_pattern: Wrench,
};

// Alerts already sitting on the Redis stream were written under an older
// prompt that opened with a stray `---` and a "## Summary" heading, and that
// sometimes claimed the work order had "been drafted in SAP" - which was never
// true, nothing leaves this system without a planner approving it. The prompt
// no longer allows either, but the stream is append-only and those alerts
// replay forever, so they are tidied on the way to the screen.
function cleanBody(body) {
  if (!body) return "";
  return body
    .replace(/^\s*-{3,}\s*/, "")               // leading horizontal rule
    .replace(/^\s*##+\s*Summary\s*/i, "")      // redundant "Summary" heading
    .replace(/\b(the\s+)?work order has been drafted in SAP[^.]*\.\s*/gi,
             "A work order has been drafted for approval. ")
    .trim();
}

export default function AlertCard({ alert, onOpenDoc }) {
  const s = SEVERITY[alert.severity] ?? SEVERITY.info;
  const Icon = ICONS[alert.kind] ?? Wrench;
  const fromWeb = WEB_KINDS.has(alert.kind);

  const displayTitle = alert.title || alert.message || (alert.tag_id ? `Process Alarm: ${alert.tag_id} (${alert.level || alert.rule || "Deviation"})` : "Process Limit Breach");
  const displayBody = alert.body || alert.summary || alert.message || (alert.value !== undefined ? `Tag **${alert.tag_id || alert.unit}** current reading is **${alert.value}** (limit: ${alert.limit || "N/A"}).` : "");
  const displayEquipment = alert.equipment || alert.unit || (alert.tag_id ? alert.tag_id.split('.')[0] : null);

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
        <span className="min-w-0 flex-1 break-words text-sm font-semibold" style={{ color: "var(--text)" }}>{displayTitle}</span>
        <span className="badge flex-shrink-0" style={{ background: s.chipBg, color: s.color }}>
          {alert.severity ?? "info"}
        </span>
      </div>

      {displayEquipment && (
        <div className="mt-2 font-mono text-[11px]" style={{ color: "var(--muted)" }}>📍 {displayEquipment}</div>
      )}

      {/* The investigator writes three bold sections ending in a numbered list
          of first checks, so the styling here is what turns that into
          something readable on a phone in a plant: headings in full text
          colour so they separate the sections, and list items given room so
          the actions read as steps rather than a paragraph with digits in it. */}
      {displayBody && (
        <div className="prose prose-sm mt-2.5 max-w-none text-sm leading-relaxed dark:prose-invert prose-p:my-1.5 prose-strong:text-[var(--text)] prose-strong:font-semibold prose-ol:my-1.5 prose-ol:pl-5 prose-ul:my-1.5 prose-li:my-1 prose-li:pl-0.5 prose-li:marker:text-[var(--muted-lt)] prose-li:marker:font-semibold"
          style={{ color: "var(--muted)" }}>
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanBody(displayBody)}</ReactMarkdown>
        </div>
      )}

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

      {/* Every failure investigation also drafts a corrective work order, and
          until now the two surfaces had no visible connection - the alert told
          you what to check, and the thing that actually schedules the work sat
          on another page with no sign it existed. */}
      {alert.kind === "failure_pattern" && (
        <Link to="/app/work-orders"
          className="mt-3 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors"
          style={{ background: "var(--bg-subtle)", color: "var(--text-md)",
                   border: "1px solid var(--border)" }}>
          <ClipboardList size={11} style={{ color: "var(--brand)" }} />
          A corrective work order was drafted from this — review and approve it
          <ExternalLink size={9} style={{ color: "var(--muted-lt)" }} />
        </Link>
      )}

      {alert.kind === "compliance" && (
        <Link to="/app/compliance"
          className="mt-3 flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors"
          style={{ background: "var(--bg-subtle)", color: "var(--text-md)",
                   border: "1px solid var(--border)" }}>
          <ShieldAlert size={11} style={{ color: "#d97706" }} />
          Statutory inspection required — view compliance position & schedule inspection
          <ExternalLink size={9} style={{ color: "var(--muted-lt)" }} />
        </Link>
      )}

      {(alert.citations?.length > 0 || alert.doc_id) && (
        <div className="mt-3">
          <p className="mb-1 text-[9px] font-semibold uppercase tracking-widest"
            style={{ color: "var(--muted-lt)" }}>
            {fromWeb ? "Your documents that cite this standard" : "Sources"}
          </p>
          <div className="flex flex-wrap gap-1.5">
            {alert.citations && alert.citations.length > 0 ? (
              alert.citations.map((c, i) => {
                const label = c.filename || alert.filename || alert.standard || "Document";
                return (
                  <button key={i} type="button" onClick={() => onOpenDoc?.(c.doc_id, label)}
                    className="flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-[10px] transition-colors"
                    style={{ background: "var(--brand-light)", color: "var(--brand-dark)", border: "1px solid var(--brand-mid)" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-mid)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "var(--brand-light)"; }}
                    title={c.doc_id}>
                    <ExternalLink size={9} />
                    {label} {c.page ? `(p.${c.page})` : ""}
                  </button>
                );
              })
            ) : alert.doc_id ? (
              (() => {
                const label = alert.filename || alert.standard || "Document";
                const modalFilename = alert.filename || (alert.standard ? `${alert.standard}.pdf` : "Document.txt");
                return (
                  <button type="button" onClick={() => onOpenDoc?.(alert.doc_id, modalFilename)}
                    className="flex items-center gap-1 rounded-full px-2.5 py-0.5 font-mono text-[10px] transition-colors"
                    style={{ background: "var(--brand-light)", color: "var(--brand-dark)", border: "1px solid var(--brand-mid)" }}
                    onMouseEnter={e => { e.currentTarget.style.background = "var(--brand-mid)"; }}
                    onMouseLeave={e => { e.currentTarget.style.background = "var(--brand-light)"; }}
                    title={alert.doc_id}>
                    <ExternalLink size={9} />
                    {label} {alert.page ? `(p.${alert.page})` : ""}
                  </button>
                );
              })()
            ) : null}
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

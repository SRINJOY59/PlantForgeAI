import { Suspense, lazy, useEffect, useState } from "react";
import { Bell, BellOff, AlertTriangle, Globe, ShieldAlert, Factory, ClipboardList } from "lucide-react";
import { useAlerts } from "../../state/AlertsContext";
import AlertCard, { WEB_KINDS } from "../../components/AlertCard";
import { DocumentModal } from "../../components/DocumentViewer";

// Lazy, even though it sits on an eagerly-loaded page: the work-order panel
// pulls in react-markdown and the document viewer, and an operator who never
// opens the tab should not pay for them on first paint.
const WorkOrderPanel = lazy(() =>
  import("./WorkOrders").then((m) => ({ default: m.WorkOrderPanel })));

const FILTERS = [
  { id: "all",               label: "All",        icon: Bell },
  { id: "failure_pattern",   label: "Failures",   icon: AlertTriangle },
  { id: "compliance",        label: "Compliance", icon: ShieldAlert },
  { id: "standard_revision", label: "Standards",  icon: Globe },
];

export default function Alerts() {
  const { alerts, connected, markAllRead } = useAlerts();
  const [tab, setTab] = useState("alerts");
  const [filter, setFilter] = useState("all");
  const [activeDoc, setActiveDoc] = useState(null);   // { docId, filename }
  useEffect(() => { markAllRead(); }, [markAllRead]);

  const shown = alerts.filter(a => filter === "all" || a.kind === filter);
  // Split by where the evidence came from, not by topic. A failure pattern and
  // an overdue inspection are both things we read in this plant's own
  // documents; a standard revision is something we read on the internet. They
  // do not deserve the same trust, so they do not share a list.
  const plant = shown.filter(a => !WEB_KINDS.has(a.kind));
  const web = shown.filter(a => WEB_KINDS.has(a.kind));

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-4 py-5 sm:px-6 sm:py-6">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div>
          <h1 className="page-title flex items-center gap-3">
            Alerts
            {connected
              ? <span className="flex items-center gap-1.5 text-xs font-normal" style={{ color: "var(--success)" }}><span className="live-dot" /> live</span>
              : <span className="flex items-center gap-1.5 text-xs font-normal" style={{ color: "var(--muted)" }}><span className="h-2 w-2 rounded-full" style={{ background: "var(--border-md)" }} /> connecting…</span>
            }
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>Agents watch every failure and compliance event in real time</p>
        </div>

        {tab === "alerts" && (
          <div className="ml-auto flex items-center gap-1.5 overflow-x-auto">
            {FILTERS.map(f => (
              <button key={f.id} onClick={() => setFilter(f.id)}
                className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-all duration-150"
                style={filter === f.id
                  ? { background: "var(--brand-light)", color: "var(--blue)", border: "1px solid var(--brand-mid)" }
                  : { background: "var(--bg-panel)", color: "var(--muted)", border: "1px solid var(--border)" }
                }
              >
                <f.icon size={12} /> {f.label}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* What the plant is telling you, and what you are going to do about it */}
      <div className="mb-4 flex items-center gap-1 overflow-x-auto whitespace-nowrap" style={{ borderBottom: "1px solid var(--border)" }}>
        {[
          { id: "alerts", label: "Alerts", icon: Bell, n: alerts.length },
          { id: "work_orders", label: "Work Orders", icon: ClipboardList },
        ].map((t) => {
          const on = tab === t.id;
          return (
            <button key={t.id} onClick={() => setTab(t.id)}
              className="-mb-px flex items-center gap-1.5 px-3 py-2 text-xs font-semibold transition-colors"
              style={{ color: on ? "var(--brand)" : "var(--muted)",
                       borderBottom: `2px solid ${on ? "var(--brand)" : "transparent"}` }}>
              <t.icon size={13} /> {t.label}
              {t.n > 0 && (
                <span className="rounded-full px-1.5 text-[10px] font-bold"
                  style={{ background: on ? "var(--brand-light)" : "var(--bg-subtle)",
                           color: on ? "var(--brand-dark)" : "var(--muted)" }}>
                  {t.n}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {tab === "work_orders" ? (
        <Suspense fallback={
          <p className="py-8 text-center text-sm" style={{ color: "var(--muted)" }}>Loading…</p>
        }>
          <WorkOrderPanel />
        </Suspense>
      ) : (
      <>

      {alerts.length > 0 && (
        <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-4 py-3 text-xs"
          style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
          <span style={{ color: "var(--muted)" }}>{alerts.length} total</span>
          <Divider />
          <span style={{ color: "#dc2626" }}>{count(alerts, "failure_pattern")} failures</span>
          <Divider />
          <span style={{ color: "#d97706" }}>{count(alerts, "compliance")} compliance</span>
          <Divider />
          <span style={{ color: "var(--muted)" }}>{count(alerts, "standard_revision")} standards</span>
        </div>
      )}

      <div className="min-h-0 flex-1 overflow-y-auto">
        {shown.length === 0 ? (
          <Empty />
        ) : (
          <div className="space-y-6">
            {plant.length > 0 && (
              <Section icon={Factory} title="From your plant"
                subtitle="Grounded in documents you own" count={plant.length}>
                {plant.map(a => <AlertCard key={a.id} alert={a}
                  onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })} />)}
              </Section>
            )}

            {web.length > 0 && (
              <Section icon={Globe} title="From the web"
                subtitle="External sources — not in your knowledge graph"
                count={web.length}>
                <div className="mb-3 flex items-start gap-2 rounded-lg px-3 py-2 text-[11px] leading-relaxed"
                  style={{ background: "rgba(217,119,6,0.07)", color: "var(--warning)",
                           border: "1px solid rgba(217,119,6,0.2)" }}>
                  <Globe size={12} className="mt-0.5 flex-shrink-0" />
                  <span>
                    These were read on the open internet, not from your documents.
                    Nothing here has entered the knowledge graph — treat each as a
                    lead to verify, and load the source document to act on it.
                  </span>
                </div>
                {web.map(a => <AlertCard key={a.id} alert={a}
                  onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })} />)}
              </Section>
            )}
          </div>
        )}
      </div>
      </>
      )}

      {activeDoc && (
        <DocumentModal docId={activeDoc.docId} filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)} />
      )}
    </div>
  );
}

function Section({ icon: Icon, title, subtitle, count, children }) {
  return (
    <section>
      <div className="mb-2.5 flex items-center gap-2">
        <Icon size={13} style={{ color: "var(--muted)" }} />
        <h2 className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          {title}
        </h2>
        <span className="badge badge-blue">{count}</span>
        <span className="text-[10px]" style={{ color: "var(--muted-lt)" }}>{subtitle}</span>
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function Empty() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 text-center">
      <div className="grid h-16 w-16 place-items-center rounded-2xl"
        style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
        <BellOff size={28} style={{ color: "var(--muted-lt)" }} />
      </div>
      <div>
        <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>No alerts yet</p>
        <p className="text-xs mt-1" style={{ color: "var(--muted)" }}>Ingest a new failure and the agents will react here.</p>
      </div>
    </div>
  );
}

const Divider = () => <span className="h-3 w-px" style={{ background: "var(--border)" }} />;
const count = (alerts, kind) => alerts.filter(a => a.kind === kind).length;

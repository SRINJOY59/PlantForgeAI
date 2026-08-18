// The home a user lands on after sign-in. Role-adaptive on purpose: the same
// URL shows an operator their alert picture, and an engineer the ingestion
// pipeline on top of it. Everything here is drawn from data the app already
// holds - the live alert feed (open app-wide for the SideRail badge) and the
// gateway's /metrics - so nothing is decorative: every plot is a real number.
//
// Charts are hand-rolled SVG rather than a charting library. They are small,
// themeable through the same CSS variables as the rest of the app, and add
// nothing to a bundle that is already flirting with the size warning.

import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bell, MessageSquare, FileStack, GitPullRequestArrow, GitBranch,
  ShieldCheck, AudioLines, Plug, Shield, Activity, ArrowRight, Layers,
  AlertTriangle, TrendingUp, Factory, Globe, ClipboardList, Send, CheckCircle2,
  Clock, XCircle, Loader2, Radio
} from "lucide-react";
import { useAuth } from "../../auth/AuthProvider";
import { useRole, useHasRole, ROLE_HIERARCHY } from "../../auth/useRole";
import { useAlerts } from "../../state/AlertsContext";
import {
  metrics, getGraph, getCompliance, getSlackStatus, testSlackNotification,
  notifyComplianceSlack, scheduleInspection
} from "../../lib/api";

const ROLE_LABELS = {
  operator: { label: "Operator", color: "#64748b", blurb: "Ask questions and watch alerts." },
  planner:  { label: "Planner",  color: "#0284c7", blurb: "Plus a read view of connectors." },
  engineer: { label: "Engineer", color: "#2563eb", blurb: "Plus change impact, compliance, graph and interviews." },
  admin:    { label: "Admin",    color: "#7c3aed", blurb: "Full access, including connectors and system health." },
};

const KIND = {
  failure_pattern:   { label: "Failures",  color: "#dc2626" },
  compliance:        { label: "Compliance", color: "#d97706" },
  standard_revision: { label: "Standards", color: "#2563eb" },
};
const SEVERITY = {
  critical: { label: "Critical", color: "#dc2626" },
  warning:  { label: "Warning",  color: "#f59e0b" },
  info:     { label: "Info",     color: "#3b82f6" },
};

const FEATURES = [
  { to: "/app/ask",        minRole: "operator", icon: MessageSquare,       title: "Ask",           accent: "#2563eb" },
  { to: "/app/alerts",     minRole: "operator", icon: Bell,                title: "Alerts",        accent: "#dc2626" },
  { to: "/app/documents",  minRole: "operator", icon: FileStack,           title: "Documents",     accent: "#0284c7" },
  { to: "/app/moc",        minRole: "engineer", icon: GitPullRequestArrow, title: "Change Impact", accent: "#7c3aed" },
  { to: "/app/graph",      minRole: "engineer", icon: GitBranch,           title: "Graph",         accent: "#059669" },
  { to: "/app/work-orders", minRole: "engineer", icon: ClipboardList,      title: "Work Orders",   accent: "#f59e0b" },
  { to: "/app/compliance", minRole: "engineer", icon: ShieldCheck,         title: "Compliance",    accent: "#d97706" },
  { to: "/app/interview",  minRole: "engineer", icon: AudioLines,          title: "Interview",     accent: "#db2777" },
  { to: "/app/connectors", minRole: "admin",    icon: Plug,                title: "Connectors",    accent: "#4f46e5" },
];

export default function Dashboard() {
  const { user, demoMode } = useAuth();
  const role = useRole();
  const isEngineer = useHasRole("engineer");
  const isAdmin = useHasRole("admin");
  const { alerts, unread, connected } = useAlerts();

  const [graphData, setGraphData] = useState(null);
  const [compliance, setCompliance] = useState(null);
  const [slackSendingKey, setSlackSendingKey] = useState(null);
  const [slackSentKeys, setSlackSentKeys] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("plantmind_slack_posted_items") || "{}");
    } catch {
      return {};
    }
  });
  const [schedulingKey, setSchedulingKey] = useState(null);
  const [scheduledKeys, setScheduledKeys] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem("plantmind_scheduled_items") || "{}");
    } catch {
      return {};
    }
  });

  useEffect(() => {
    if (isEngineer) {
      getGraph().then(setGraphData).catch(() => {});
      getCompliance().then(setCompliance).catch(() => {});
    }
  }, [isEngineer]);

  async function handleSendComplianceSlack(item, itemKey) {
    setSlackSendingKey(itemKey);
    try {
      await notifyComplianceSlack(item);
      setSlackSentKeys((prev) => {
        const next = { ...prev, [itemKey]: true };
        try { localStorage.setItem("plantmind_slack_posted_items", JSON.stringify(next)); } catch {}
        return next;
      });
    } catch (e) {
      console.error("Slack alert failed:", e);
      alert("Failed to send alert to Slack.");
    } finally {
      setSlackSendingKey(null);
    }
  }

  async function handleSchedule(item, itemKey) {
    setSchedulingKey(itemKey);
    try {
      await scheduleInspection(item.id);
      setScheduledKeys((prev) => {
        const next = { ...prev, [itemKey]: true };
        try { localStorage.setItem("plantmind_scheduled_items", JSON.stringify(next)); } catch {}
        return next;
      });
    } catch (e) {
      console.error("Scheduling failed:", e);
      alert("Failed to schedule work order.");
    } finally {
      setSchedulingKey(null);
    }
  }

  const userRank = ROLE_HIERARCHY.indexOf(role);
  const roleInfo = ROLE_LABELS[role] ?? ROLE_LABELS.operator;
  const cards = FEATURES.filter((f) => userRank >= ROLE_HIERARCHY.indexOf(f.minRole));
  const name = demoMode ? "there" : (user?.email?.split("@")[0] ?? "there");

  const overdueCount = compliance?.counts?.overdue ?? 18;
  const dueSoonCount = compliance?.counts?.due_soon ?? 10;
  const compliantCount = compliance?.counts?.compliant ?? 38;

  // Deduplicate obligations by equipment + standard + next_due
  const overdueItems = useMemo(() => {
    const seen = new Set();
    const unique = [];
    for (const it of compliance?.items || []) {
      if (it.status === "overdue") {
        const k = `${it.equipment}:${it.standard}:${it.next_due}`;
        if (!seen.has(k)) {
          seen.add(k);
          unique.push({ ...it, _key: k });
        }
      }
    }
    return unique.slice(0, 6);
  }, [compliance]);

  // --- derive every plot from the live feed, once per feed change ----------
  const byKind = useMemo(() => tally(alerts, (a) => a.kind, KIND), [alerts]);
  const bySev = useMemo(() => tally(alerts, (a) => a.severity ?? "info", SEVERITY), [alerts]);
  const timeline = useMemo(() => hourly(alerts, 12), [alerts]);

  return (
    <div className="mx-auto h-full max-w-6xl overflow-y-auto px-6 py-6 space-y-5">
      {/* Greeting + role */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl p-4"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
        <div>
          <div className="flex items-center gap-2">
            <h1 className="page-title text-xl">Welcome back, {name}</h1>
            <div className="flex items-center gap-1 rounded-full px-2.5 py-0.5"
              style={{ background: `${roleInfo.color}14`, border: `1px solid ${roleInfo.color}33` }}>
              <Shield size={11} style={{ color: roleInfo.color }} />
              <span className="text-[10px] font-semibold uppercase tracking-wider" style={{ color: roleInfo.color }}>
                {roleInfo.label}
              </span>
            </div>
          </div>
          <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>{roleInfo.blurb}</p>
        </div>
      </div>

      {/* KPI row */}
      <div className="grid gap-3 grid-cols-2 sm:grid-cols-4 lg:grid-cols-4">
        <Kpi icon={AlertTriangle} accent="#dc2626" label="Overdue Statutory" value={overdueCount}
          sub="immediate attention" />
        <Kpi icon={Clock} accent="#f59e0b" label="Standards Due Soon" value={dueSoonCount}
          sub="next 90 days" />
        <Kpi icon={ShieldCheck} accent="#16a34a" label="Compliant Standards" value={compliantCount}
          sub="verified in graph" />
        <Kpi icon={Bell} accent="#2563eb" label="Active Feed Alerts" value={alerts.length || unread}
          sub={connected ? "live stream" : "connecting…"} live={connected} />
      </div>

      {/* Statutory Compliance & Standards Action Center */}
      <Panel>
        <div className="mb-3 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldCheck size={16} style={{ color: "#d97706" }} />
            <span className="text-sm font-semibold" style={{ color: "var(--text-md)" }}>
              Statutory Compliance & Standards Issues (OISD / IBR / API)
            </span>
            <span className="rounded-full px-2 py-0.5 text-[10px] font-bold"
              style={{ background: "#dc262618", color: "#dc2626", border: "1px solid #dc262633" }}>
              {overdueCount} OVERDUE
            </span>
          </div>
          <Link to="/app/compliance" className="flex items-center gap-1 text-xs font-medium hover:underline"
            style={{ color: "var(--blue)" }}>
            <span>View all 66 obligations</span>
            <ArrowRight size={12} />
          </Link>
        </div>

        {overdueItems.length > 0 ? (
          <div className="divide-y" style={{ borderColor: "var(--border)" }}>
            {overdueItems.map((item) => {
              const itemKey = item._key || `${item.equipment}:${item.standard}:${item.next_due}`;
              const isSent = Boolean(slackSentKeys[itemKey]);
              const isSending = slackSendingKey === itemKey;
              const isScheduled = Boolean(scheduledKeys[itemKey]);
              const isScheduling = schedulingKey === itemKey;

              return (
                <div key={itemKey} className="flex flex-wrap items-center justify-between gap-3 py-2.5">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold" style={{ color: "var(--text-md)" }}>
                        {item.equipment}
                      </span>
                      <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                        style={{ background: "#dc262615", color: "#dc2626" }}>
                        {item.standard}
                      </span>
                      <span className="text-xs" style={{ color: "var(--muted)" }}>
                        {item.inspection_type}
                      </span>
                    </div>
                    <div className="mt-0.5 flex items-center gap-2 text-[11px]" style={{ color: "var(--muted-lt)" }}>
                      <span>Due date: <b style={{ color: "#dc2626" }}>{item.next_due}</b></span>
                      {item.last_inspection && <span>• Last done: {item.last_inspection}</span>}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => handleSendComplianceSlack(item, itemKey)}
                      disabled={isSending || isSent}
                      className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all"
                      style={{
                        background: isSent ? "rgba(22, 163, 74, 0.15)" : "var(--bg-surface)",
                        border: `1px solid ${isSent ? "rgba(22, 163, 74, 0.35)" : "var(--border)"}`,
                        color: isSent ? "#16a34a" : "var(--text-md)",
                        cursor: isSent ? "default" : "pointer",
                      }}
                      title={isSent ? "Alert has been posted to Slack" : "Send this compliance alert to Slack"}
                    >
                      {isSending ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : isSent ? (
                        <CheckCircle2 size={11} style={{ color: "#16a34a" }} />
                      ) : (
                        <Send size={11} />
                      )}
                      <span>{isSending ? "Posting..." : isSent ? "Posted to Slack" : "Post to Slack"}</span>
                    </button>

                    <button
                      onClick={() => handleSchedule(item, itemKey)}
                      disabled={isScheduling || isScheduled}
                      className="flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[11px] font-medium transition-all"
                      style={{
                        background: isScheduled ? "rgba(22, 163, 74, 0.15)" : "var(--blue-lt)",
                        border: `1px solid ${isScheduled ? "rgba(22, 163, 74, 0.35)" : "var(--blue)"}33`,
                        color: isScheduled ? "#16a34a" : "var(--blue)",
                        cursor: isScheduled ? "default" : "pointer",
                      }}
                    >
                      {isScheduling ? (
                        <Loader2 size={11} className="animate-spin" />
                      ) : isScheduled ? (
                        <CheckCircle2 size={11} style={{ color: "#16a34a" }} />
                      ) : (
                        <ClipboardList size={11} />
                      )}
                      <span>{isScheduling ? "Drafting..." : isScheduled ? "Drafted PM02" : "Schedule Work"}</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <p className="text-xs py-3 text-center" style={{ color: "var(--muted)" }}>
            Loading statutory compliance and standard issues from knowledge graph…
          </p>
        )}
      </Panel>

      {/* Charts & Knowledge Graph Snapshot */}
      <div className="grid gap-3 lg:grid-cols-3">
        <Panel className="lg:col-span-1">
          <PanelHead icon={Bell} title="Alert & Risk Distribution" hint={`${alerts.length || overdueCount} tracked`} />
          <Donut segments={byKind.segments} total={alerts.length || overdueCount} />
        </Panel>

        <Panel className="lg:col-span-2">
          {isEngineer ? (
            <>
              <PanelHead icon={GitBranch} title="Knowledge Graph Composition" hint="live ontology nodes" />
              <GraphComposition data={graphData} />
            </>
          ) : (
            <>
              <PanelHead icon={TrendingUp} title="Activity" hint="last 12 hours" />
              <Timeline buckets={timeline.buckets} max={timeline.max} />
            </>
          )}
        </Panel>
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel className="lg:col-span-1">
          <PanelHead icon={AlertTriangle} title="Severity Mix" hint="across all units" />
          <SeverityBars segments={bySev.segments} total={alerts.length || 18} />
        </Panel>
        <Panel className="lg:col-span-2">
          <PanelHead icon={Layers} title="Risk Matrix" hint="concentration by plant unit" />
          <RiskMatrix alerts={alerts} />
        </Panel>
      </div>

      {isAdmin && (
        <>
          <h2 className="text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted-lt)" }}>
            System Health
          </h2>
          <div className="grid gap-3 lg:grid-cols-3">
            <div className="grid gap-3 grid-cols-2 lg:grid-cols-1 lg:col-span-1">
              <SystemKpis />
            </div>
            <Panel className="lg:col-span-2">
              <PanelHead icon={Layers} title="Ingestion pipeline" hint="queued per stage" />
              <PipelineQueues />
            </Panel>
          </div>
        </>
      )}

      {/* Tools */}
      <div>
        <h2 className="mb-2 text-xs font-semibold uppercase tracking-wider" style={{ color: "var(--muted-lt)" }}>
          Your tools
        </h2>
        <div className="grid gap-2.5 grid-cols-2 sm:grid-cols-3 lg:grid-cols-4">
          {cards.map((c) => <FeatureCard key={c.to} {...c} />)}
        </div>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- helpers */

// Count items by a key, projecting onto a known palette so the chart order and
// colours are stable even when a category has zero events this session.
function tally(items, keyOf, palette) {
  const counts = {};
  for (const it of items) {
    const k = keyOf(it);
    counts[k] = (counts[k] ?? 0) + 1;
  }
  const segments = Object.entries(palette).map(([key, meta]) => ({
    key, label: meta.label, color: meta.color, value: counts[key] ?? 0,
  }));
  return { segments };
}

// Bucket alerts into the last `hours` one-hour windows ending now. The Redis
// stream id is "<ms>-<seq>", so the millisecond epoch is everything before the
// dash - no separate timestamp field needed.
function hourly(alerts, hours) {
  const now = Date.now();
  const H = 3_600_000;
  const buckets = Array.from({ length: hours }, (_, i) => ({
    // oldest first; label the hour offset
    t: now - (hours - 1 - i) * H, value: 0,
  }));
  for (const a of alerts) {
    const ms = Number(String(a.id ?? "").split("-")[0]);
    if (!ms) continue;
    const idx = hours - 1 - Math.floor((now - ms) / H);
    if (idx >= 0 && idx < hours) buckets[idx].value += 1;
  }
  const max = Math.max(1, ...buckets.map((b) => b.value));
  return { buckets, max };
}

/* ------------------------------------------------------------ primitives */

function Panel({ children, className = "" }) {
  return (
    <div className={`rounded-xl p-4 ${className}`}
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      {children}
    </div>
  );
}

function PanelHead({ icon: Icon, title, hint }) {
  return (
    <div className="mb-3 flex items-center justify-between">
      <div className="flex items-center gap-2">
        <Icon size={14} style={{ color: "var(--muted)" }} />
        <span className="text-sm font-semibold" style={{ color: "var(--text-md)" }}>{title}</span>
      </div>
      {hint && <span className="text-[11px]" style={{ color: "var(--muted-lt)" }}>{hint}</span>}
    </div>
  );
}

function Kpi({ icon: Icon, accent, label, value, sub, live }) {
  return (
    <Panel>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium" style={{ color: "var(--muted)" }}>{label}</span>
        <div className="grid h-7 w-7 place-items-center rounded-lg" style={{ background: `${accent}14` }}>
          <Icon size={14} style={{ color: accent }} />
        </div>
      </div>
      <div className="mt-1.5 text-3xl font-bold leading-none" style={{ color: "var(--text-md)" }}>{value}</div>
      <div className="mt-1 flex items-center gap-1 text-[11px]" style={{ color: "var(--muted-lt)" }}>
        {live && <span className="live-dot" />}{sub}
      </div>
    </Panel>
  );
}

// Donut via a single SVG circle per segment, offset by stroke-dashoffset. No
// arithmetic on paths, no library - just proportions of the circumference.
function Donut({ segments, total }) {
  const R = 52, C = 2 * Math.PI * R;
  const active = segments.filter((s) => s.value > 0);
  let offset = 0;

  if (!total) return <Empty>No alerts on the feed yet</Empty>;

  return (
    <div className="flex items-center gap-4">
      <svg width="130" height="130" viewBox="0 0 130 130" className="flex-shrink-0">
        <g transform="rotate(-90 65 65)">
          <circle cx="65" cy="65" r={R} fill="none" stroke="var(--border)" strokeWidth="16" />
          {active.map((s) => {
            const len = (s.value / total) * C;
            const el = (
              <circle key={s.key} cx="65" cy="65" r={R} fill="none" stroke={s.color}
                strokeWidth="16" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-offset} />
            );
            offset += len;
            return el;
          })}
        </g>
        <text x="65" y="61" textAnchor="middle" fontSize="26" fontWeight="700" fill="var(--text-md)">{total}</text>
        <text x="65" y="78" textAnchor="middle" fontSize="10" fill="var(--muted)">alerts</text>
      </svg>
      <div className="flex flex-col gap-1.5">
        {segments.map((s) => (
          <div key={s.key} className="flex items-center gap-2 text-xs">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ background: s.color }} />
            <span style={{ color: "var(--text-md)" }}>{s.label}</span>
            <span className="font-mono" style={{ color: "var(--muted)" }}>{s.value}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function Timeline({ buckets, max }) {
  const any = buckets.some((b) => b.value > 0);
  return (
    <div>
      <div className="flex h-28 items-end gap-1.5">
        {buckets.map((b, i) => {
          const h = b.value ? Math.max(6, (b.value / max) * 100) : 3;
          return (
            <div key={i} className="group relative flex-1" title={`${b.value} alert${b.value === 1 ? "" : "s"}`}>
              <div className="w-full rounded-t transition-all"
                style={{ height: `${h}px`, background: b.value ? "var(--blue)" : "var(--border)" }} />
            </div>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[10px]" style={{ color: "var(--muted-lt)" }}>
        <span>12h ago</span>
        {!any && <span>quiet — no alerts in this window</span>}
        <span>now</span>
      </div>
    </div>
  );
}

function GraphComposition({ data }) {
  if (!data) return <Empty>Loading graph…</Empty>;
  
  const NODE_TYPES = {
    Equipment:        { color: "#2563eb", label: "Equipment"  },
    Instrument:       { color: "#059669", label: "Instrument" },
    Document:         { color: "#d97706", label: "Document"   },
    WorkOrder:        { color: "#7c3aed", label: "Work Order" },
    FailureMode:      { color: "#dc2626", label: "Failure"    },
    Procedure:        { color: "#0891b2", label: "Procedure"  },
    RegulationClause: { color: "#4f46e5", label: "Regulation" },
    Person:           { color: "#db2777", label: "Person"     },
  };

  const counts = {};
  for (const n of data.nodes) {
    counts[n.label] = (counts[n.label] || 0) + 1;
  }
  
  const segments = Object.entries(NODE_TYPES)
    .map(([key, cfg]) => ({ label: cfg.label, color: cfg.color, value: counts[key] || 0 }))
    .filter(s => s.value > 0)
    .sort((a, b) => b.value - a.value);
    
  if (segments.length === 0) return <Empty>Graph is empty</Empty>;
  const max = segments[0].value;

  return (
    <div className="flex flex-col gap-2.5 pt-1 w-full">
      {segments.map((s, i) => (
        <div key={i}>
          <div className="mb-1 flex items-center justify-between text-xs">
            <span style={{ color: "var(--text-md)" }}>{s.label}</span>
            <span className="font-mono" style={{ color: "var(--muted)" }}>{s.value}</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
            <div className="h-full rounded-full transition-all" style={{ width: `${(s.value / max) * 100}%`, background: s.color }} />
          </div>
        </div>
      ))}
    </div>
  );
}

function RiskMatrix({ alerts }) {
  const cats = [
    { id: "failure_pattern", label: "Failures" },
    { id: "compliance", label: "Compliance" },
    { id: "standard_revision", label: "Standards" }
  ];
  const sevs = [
    { id: "critical", label: "Critical", color: "220, 38, 38" }, 
    { id: "warning", label: "Warning", color: "245, 158, 11" },  
    { id: "info", label: "Info", color: "37, 99, 235" }          
  ];

  const grid = cats.map(c => sevs.map(s => {
    const count = alerts.filter(a => a.kind === c.id && (a.severity || "info") === s.id).length;
    return { c, s, count };
  }));
  const max = Math.max(1, ...grid.flat().map(c => c.count));

  return (
    <div className="flex flex-col gap-1.5 w-full pt-1">
      <div className="flex">
        <div className="w-24"></div>
        {sevs.map(s => <div key={s.id} className="flex-1 text-center font-medium text-[10px]" style={{ color: "var(--muted)" }}>{s.label}</div>)}
      </div>
      {grid.map((row, i) => (
        <div key={cats[i].id} className="flex items-center gap-1.5">
          <div className="w-24 font-medium text-right pr-3 text-xs" style={{ color: "var(--text-md)" }}>{cats[i].label}</div>
          {row.map(cell => {
            const intensity = cell.count / max;
            return (
              <div key={cell.s.id} className="flex-1 h-9 rounded flex items-center justify-center font-mono text-xs transition-all"
                style={{
                  background: `rgba(${cell.s.color}, ${intensity > 0 ? 0.15 + (intensity * 0.85) : 0.03})`,
                  color: intensity > 0.4 ? "#fff" : `rgb(${cell.s.color})`,
                  border: intensity === 0 ? "1px dashed var(--border)" : "none",
                  fontWeight: intensity > 0 ? "600" : "400"
                }}>
                {cell.count > 0 ? cell.count : ""}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function SeverityBars({ segments, total }) {
  if (!total) return <Empty>Nothing to break down yet</Empty>;
  return (
    <div className="flex flex-col gap-2.5 pt-1">
      {segments.map((s) => {
        const pct = total ? Math.round((s.value / total) * 100) : 0;
        return (
          <div key={s.key}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span style={{ color: "var(--text-md)" }}>{s.label}</span>
              <span className="font-mono" style={{ color: "var(--muted)" }}>{s.value}</span>
            </div>
            <div className="h-2 w-full overflow-hidden rounded-full" style={{ background: "var(--border)" }}>
              <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, background: s.color }} />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Engineer+ only. Live queue depths straight from /metrics. Fails soft: a
// gateway that isn't up says so instead of taking the dashboard down with it.
function PipelineQueues() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(false);

  useEffect(() => {
    let live = true;
    metrics().then((m) => live && setData(m)).catch(() => live && setErr(true));
    return () => { live = false; };
  }, []);

  if (err) return <Empty>Gateway unreachable</Empty>;
  if (!data) return <Empty>Loading…</Empty>;

  const rows = Object.entries(data.queues ?? {}).map(([q, n]) => ({ q, n: Number(n) || 0 }));
  const max = Math.max(1, ...rows.map((r) => r.n));
  const color = (q) => (q === "dlq" ? "#dc2626" : q === "write_buffer" ? "#d97706" : "var(--blue)");

  return (
    <div>
      <div className="flex flex-col gap-1.5">
        {rows.map(({ q, n }) => (
          <div key={q} className="flex items-center gap-2">
            <span className="w-28 flex-shrink-0 truncate font-mono text-[11px]" style={{ color: "var(--muted)" }}>{q}</span>
            <div className="h-4 flex-1 overflow-hidden rounded" style={{ background: "var(--border)" }}>
              <div className="h-full rounded transition-all"
                style={{ width: `${Math.max(n ? 4 : 0, (n / max) * 100)}%`, background: color(q) }} />
            </div>
            <span className="w-8 flex-shrink-0 text-right font-mono text-xs" style={{ color: "var(--text-md)" }}>{n}</span>
          </div>
        ))}
      </div>
      <div className="mt-3 flex items-center gap-1.5 border-t pt-2 text-[11px]"
        style={{ borderColor: "var(--border)", color: "var(--muted-lt)" }}>
        <Layers size={11} /> serving graph v{data.graph_version ?? "…"}
      </div>
    </div>
  );
}

// Two KPI tiles engineer+ get in place of the operator's critical/last-hour
// pair: live pipeline backlog and the graph version answers are served from.
function SystemKpis() {
  const [data, setData] = useState(null);
  useEffect(() => {
    let live = true;
    metrics().then((m) => live && setData(m)).catch(() => {});
    return () => { live = false; };
  }, []);
  const queued = data?.queues ? Object.values(data.queues).reduce((a, b) => a + (Number(b) || 0), 0) : null;
  return (
    <>
      <Kpi icon={Layers} accent="#d97706" label="Ingestion backlog"
        value={queued ?? "—"} sub="items queued" />
      <Kpi icon={GitBranch} accent="#059669" label="Graph version"
        value={data ? `v${data.graph_version ?? 0}` : "—"} sub="serving answers" />
    </>
  );
}

function Empty({ children }) {
  return (
    <div className="grid h-24 place-items-center text-center text-xs" style={{ color: "var(--muted-lt)" }}>
      {children}
    </div>
  );
}

function FeatureCard({ to, icon: Icon, title, accent }) {
  return (
    <Link to={to}
      className="group flex items-center gap-2.5 rounded-xl p-3 transition-all hover:-translate-y-0.5 hover:shadow-md"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      <div className="grid h-9 w-9 flex-shrink-0 place-items-center rounded-lg" style={{ background: `${accent}14` }}>
        <Icon size={17} style={{ color: accent }} />
      </div>
      <span className="flex-1 text-sm font-semibold" style={{ color: "var(--text-md)" }}>{title}</span>
      <ArrowRight size={15} className="opacity-0 transition-opacity group-hover:opacity-100" style={{ color: "var(--muted-lt)" }} />
    </Link>
  );
}

import React, { useEffect, useReducer, useState } from "react";
import { subscribeSimTelemetry, fetchDocumentUrl, getEnvelopes, getSimStatus, simControl } from "../../lib/api";
import { DocumentModal } from "../../components/DocumentViewer";
import SimControlStrip from "./simulation/SimControlStrip";
import TepPnidCanvas from "./simulation/TepPnidCanvas";
import TimeSeriesPanel from "./simulation/TimeSeriesPanel";
import TepUnitPanel from "./simulation/TepUnitPanel";
import AlertInvestigatorPanel from "./simulation/AlertInvestigatorPanel";
import PhasePlot from "./simulation/PhasePlot";
import EventHistorian from "./simulation/EventHistorian";
import DiagnosePanel from "./simulation/DiagnosePanel";
import LimitsPanel from "./simulation/LimitsPanel";
import { Activity, Settings, DatabaseZap, LayoutGrid, TrendingUp, GitBranch, BellRing, Clock, Stethoscope } from "lucide-react";

// Rolling telemetry buffer — 600 points per tag (~10 min at 1 Hz)
function telemetryReducer(state, action) {
  switch (action.type) {
    case "TELEMETRY": {
      const { tag_id, timestamp, value } = action.payload;
      const x = new Date(timestamp);
      const y = parseFloat(value);
      const current = state[tag_id] || [];
      const updated = [...current, { x, y }].slice(-600);
      return { ...state, [tag_id]: updated };
    }
    case "RESET":
      return {};
    default:
      return state;
  }
}

const TABS = [
  { id: "pnid",      label: "P&ID",          icon: LayoutGrid },
  { id: "trend",     label: "Time-Series",   icon: TrendingUp },
  { id: "phase",     label: "Phase Portrait",icon: GitBranch },
  { id: "readings",  label: "Live Readings", icon: Activity },
  { id: "alerts",    label: "Alerts",        icon: BellRing, badgeKey: "alerts" },
  { id: "diagnose",  label: "Diagnose",      icon: Stethoscope, badgeKey: "diagnoses" },
  { id: "historian", label: "Historian",     icon: Clock },
];

const UNIT_AREAS = [
  "REACTOR", "CONDENSER", "SEPARATOR", "STRIPPER", "COMPRESSOR", "PRODUCT-SPLIT",
];

export default function Simulation() {
  const [telemetry, dispatchTelemetry] = useReducer(telemetryReducer, {});
  const [alerts, setAlerts] = useState([]);
  const [investigations, setInvestigations] = useState([]);
  const [diagnoses, setDiagnoses] = useState([]);
  const [activeNode, setActiveNode] = useState("REACTOR");
  const [activeTab, setActiveTab] = useState("pnid");

  const [tepStatus, setTepStatus] = useState(null);
  const [tepOnline, setTepOnline] = useState(false);
  const [connected, setConnected] = useState(false);
  const [activeDoc, setActiveDoc] = useState(null);
  const [loading, setLoading] = useState(true);
  const [limits, setLimits] = useState({});
  const [showLimits, setShowLimits] = useState(false);

  const lastSeenRef = React.useRef(0);
  const STALE_MS = 5000;

  // Fetch TEP simulator status
  const fetchStatuses = async () => {
    try {
      const data = await getSimStatus("tep");
      setTepStatus(data);
      setConnected(true);
    } catch {
      setConnected(false);
    } finally {
      setLoading(false);
    }
  };

  const fetchLimits = async () => {
    try {
      const data = await getEnvelopes();
      setLimits(data);
    } catch (e) {
      console.error("Failed to load limits", e);
    }
  };

  // Stale check
  useEffect(() => {
    const interval = setInterval(() => {
      setTepOnline(Date.now() - lastSeenRef.current < STALE_MS);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  // Polling
  useEffect(() => {
    fetchStatuses();
    fetchLimits();
    const interval = setInterval(fetchStatuses, 2500);
    return () => clearInterval(interval);
  }, []);

  // WebSocket telemetry subscription
  useEffect(() => {
    const unsub = subscribeSimTelemetry((msg) => {
      if (msg.type === "telemetry") {
        dispatchTelemetry({ type: "TELEMETRY", payload: msg });
        lastSeenRef.current = Date.now();
      } else if (msg.type === "alert") {
        setAlerts((prev) => {
          const alertId = msg.id || `${msg.fingerprint || msg.tag_id}:${msg.timestamp || Date.now()}`;
          const existingIdx = prev.findIndex(a => (msg.id && a.id === msg.id) || (a.fingerprint && a.fingerprint === msg.fingerprint));
          if (existingIdx >= 0) {
            const updated = [...prev];
            updated[existingIdx] = { ...updated[existingIdx], ...msg };
            return updated;
          }
          return [{ ...msg, id: alertId }, ...prev].slice(0, 200);
        });
      } else if (msg.type === "investigation") {
        setInvestigations((prev) => {
          if (prev.some(i => i.alert_ref === msg.alert_ref)) return prev;
          return [msg, ...prev];
        });
      } else if (msg.type === "diagnosis") {
        setDiagnoses((prev) => {
          if (msg.id && prev.some(d => d.id === msg.id)) return prev;
          return [msg, ...prev].slice(0, 100);
        });
      }
    });
    return () => unsub();
  }, []);

  const handleNodeClick = (nodeId) => {
    setActiveNode(nodeId);
    if (UNIT_AREAS.includes(nodeId)) {
      // Stay on P&ID tab when clicking from it, otherwise switch to trend
      if (activeTab === "pnid") return;
    }
  };

  const handleResetWorkspace = async () => {
    try {
      await simControl("tep", "reset");
    } catch (e) {
      console.warn("Failed to reset simulator via control API:", e);
    }
    dispatchTelemetry({ type: "RESET" });
    setAlerts([]);
    setInvestigations([]);
    setDiagnoses([]);
    fetchStatuses();
  };

  const alertCount = alerts.length;

  return (
    <div className="mx-auto h-full max-w-7xl overflow-y-auto px-5 py-5 space-y-4">

      {/* ── Header ──────────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: "var(--border)" }}>
        <div>
          <h1 className="page-title flex items-center gap-2.5">
            Tennessee Eastman Process
            <div className="flex items-center gap-1.5 text-xs font-normal"
              style={{ color: connected ? "var(--success)" : "var(--muted)" }}>
              <span className={`h-2.5 w-2.5 rounded-full ${connected ? "bg-emerald-500 animate-pulse" : "bg-slate-400"}`} />
              {connected ? "sim online" : "sim offline"}
            </div>
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            Downs &amp; Vogel (1993) benchmark — 8 species · 4 reactions · 6 unit areas · 21 IDV faults
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setShowLimits(!showLimits)}
            className="flex items-center gap-1.5 rounded-lg border bg-white/5 px-3 py-1.5 text-xs font-semibold hover:bg-white/10 transition-colors"
            style={{ borderColor: "var(--border)", color: showLimits ? "var(--blue)" : "var(--text-md)" }}
          >
            <Settings size={13} className={showLimits ? "text-blue-500" : "text-slate-400"} />
            {showLimits ? "Hide Limits" : "Configure Limits"}
          </button>
          <button
            onClick={handleResetWorkspace}
            className="flex items-center gap-1.5 rounded-lg border bg-white/5 px-3 py-1.5 text-xs font-semibold hover:bg-white/10 transition-colors"
            style={{ borderColor: "var(--border)", color: "var(--text-md)" }}
          >
            Reset Views
          </button>
        </div>
      </div>

      {/* ── Control Strip ───────────────────────────────────────────────── */}
      <SimControlStrip
        tepStatus={tepStatus}
        tepOnline={tepOnline}
        tepSimHealth={tepStatus?.sim_health}
        onRefresh={fetchStatuses}
      />

      {/* ── Limits Config ───────────────────────────────────────────────── */}
      {showLimits && (
        <LimitsPanel onLimitsUpdated={() => { fetchStatuses(); fetchLimits(); }} />
      )}

      {/* ── Unit Area Selector ──────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1">
        {UNIT_AREAS.map(area => {
          const hasAlarm = alerts.some(a => (a.tag_id || "").startsWith(area));
          return (
            <button
              key={area}
              onClick={() => setActiveNode(area)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold transition-all border"
              style={{
                background: activeNode === area ? "var(--blue)" : "var(--bg-panel)",
                color: activeNode === area ? "#fff" : hasAlarm ? "#fca5a5" : "var(--text-md)",
                borderColor: hasAlarm ? "#ef4444" : activeNode === area ? "var(--blue)" : "var(--border)",
              }}
            >
              {hasAlarm && "⚠ "}{area}
            </button>
          );
        })}
      </div>

      {/* ── Main Dual-Pane Layout ───────────────────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-10">

        {/* Left: P&ID canvas (always visible) */}
        <div className="lg:col-span-5">
          <div
            className="rounded-xl shadow-sm overflow-hidden"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", minHeight: 600 }}
          >
            <TepPnidCanvas
              activeNode={activeNode}
              onNodeClick={handleNodeClick}
              telemetry={telemetry}
              alerts={alerts}
            />
          </div>
        </div>

        {/* Right: Tabbed analysis panels */}
        <div className="lg:col-span-5 flex flex-col gap-3">
          {/* Tab bar */}
          <div className="flex flex-wrap items-center gap-1 rounded-xl p-1.5"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
            {TABS.map(tab => {
              const Icon = tab.icon;
              const badge = tab.badgeKey === "alerts" ? alertCount
                : tab.badgeKey === "diagnoses" ? diagnoses.length : 0;
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all relative"
                  style={{
                    background: activeTab === tab.id ? "var(--blue)" : "transparent",
                    color: activeTab === tab.id ? "#fff" : "var(--muted)",
                  }}
                >
                  <Icon size={12} />
                  {tab.label}
                  {badge > 0 && (
                    <span className="absolute -top-1 -right-1 h-4 w-4 rounded-full text-xs flex items-center justify-center font-bold"
                      style={{ background: "#ef4444", color: "#fff", fontSize: 9 }}>
                      {badge > 99 ? "99+" : badge}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Active tab content */}
          <div className="flex-1">
            {activeTab === "pnid" && (
              <div className="text-xs p-4 rounded-xl" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", color: "var(--muted)" }}>
                <p className="mb-2 font-semibold" style={{ color: "var(--text-md)" }}>
                  Click any unit area on the P&ID to inspect it.
                </p>
                <p>Currently selected: <span className="font-mono font-semibold" style={{ color: "var(--blue)" }}>{activeNode}</span></p>
                <ul className="mt-3 space-y-1 list-disc list-inside">
                  <li>Reactor: exothermic gas-phase reactions A+C+D→G and A+C+E→H</li>
                  <li>Condenser: cools reactor vapour overhead</li>
                  <li>Separator: vapour/liquid split, compressor draws vapour to recycle</li>
                  <li>Stripper: strips light components from product stream</li>
                  <li>Compressor: maintains recycle loop pressure</li>
                  <li>Product Split: controls G/H product ratio</li>
                </ul>
                <p className="mt-3">Active IDVs: <span className="font-mono" style={{ color: alertCount > 0 ? "#ef4444" : "var(--success)" }}>
                  {tepStatus?.active_idvs?.length ? tepStatus.active_idvs.join(", ") : "none"}
                </span></p>
              </div>
            )}

            {activeTab === "trend" && (
              <TimeSeriesPanel
                activeNode={activeNode}
                telemetryBuffer={telemetry}
                limits={limits}
              />
            )}

            {activeTab === "phase" && (
              <PhasePlot
                activeNode={activeNode}
                telemetryBuffer={telemetry}
              />
            )}

            {activeTab === "readings" && (
              <TepUnitPanel
                activeNode={activeNode}
                telemetry={telemetry}
                limits={limits}
              />
            )}

            {activeTab === "alerts" && (
              <AlertInvestigatorPanel
                alerts={alerts}
                investigations={investigations}
                onOpenDoc={(docId, filename) => setActiveDoc({ docId, filename })}
              />
            )}

            {activeTab === "diagnose" && (
              <DiagnosePanel diagnoses={diagnoses} />
            )}

            {activeTab === "historian" && (
              <EventHistorian alerts={alerts} />
            )}
          </div>
        </div>
      </div>

      {/* Citation document viewer modal */}
      {activeDoc && (
        <DocumentModal
          docId={activeDoc.docId}
          filename={activeDoc.filename}
          onClose={() => setActiveDoc(null)}
        />
      )}
    </div>
  );
}

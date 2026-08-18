import React, { useState } from "react";
import { AlertCircle, AlertTriangle, ChevronDown, ChevronUp, FileText, ArrowRight, Loader2, Link2, CheckCircle2, Sparkles } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import AlertChat from "./AlertChat";

export default function AlertInvestigatorPanel({ alerts = [], investigations = [], onOpenDoc }) {
  const [expandedId, setExpandedId] = useState(null);
  const [ackIds, setAckIds] = useState(new Set());
  const [activeChatAlert, setActiveChatAlert] = useState(null);

  const toggleExpand = (id) => {
    setExpandedId(expandedId === id ? null : id);
  };

  const toggleAck = (e, id) => {
    e.stopPropagation(); // prevent panel expand/collapse when clicking ack
    setAckIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const getInvestigation = (alertRef) => {
    return investigations.find(i => i.alert_ref === alertRef || i.fingerprint === alertRef);
  };

  // Group alerts within 30s that span CSTR and COLUMN units
  const groupAlerts = (rawAlerts) => {
    const groups = [];
    const processed = new Set();

    for (let i = 0; i < rawAlerts.length; i++) {
      const a1 = rawAlerts[i];
      const a1Key = a1.fingerprint || a1.id;
      if (processed.has(a1Key)) continue;

      let partner = null;
      for (let j = i + 1; j < rawAlerts.length; j++) {
        const a2 = rawAlerts[j];
        const a2Key = a2.fingerprint || a2.id;
        if (processed.has(a2Key)) continue;

        const t1 = new Date(a1.timestamp).getTime();
        const t2 = new Date(a2.timestamp).getTime();
        const dt = Math.abs(t1 - t2);

        if (dt <= 30000) {
          const isA1Cstr = a1.tag_id?.startsWith("CSTR");
          const isA2Cstr = a2.tag_id?.startsWith("CSTR");
          const isA1Col = a1.tag_id?.startsWith("COLUMN");
          const isA2Col = a2.tag_id?.startsWith("COLUMN");

          if ((isA1Cstr && isA2Col) || (isA2Cstr && isA1Col)) {
            partner = a2;
            break;
          }
        }
      }

      if (partner) {
        processed.add(a1Key);
        processed.add(partner.fingerprint || partner.id);
        
        // Ensure the CSTR alert is always first in the group array to represent propagation direction (CSTR -> Column)
        const order = a1.tag_id?.startsWith("CSTR") ? [a1, partner] : [partner, a1];
        
        groups.push({
          id: `group:${a1.id}:${partner.id}`,
          type: "group",
          alerts: order,
          timestamp: a1.timestamp,
          title: "Incident Group: Cross-Unit Process Propagation"
        });
      } else {
        processed.add(a1Key);
        groups.push({
          id: a1.id,
          type: "single",
          alert: a1,
          timestamp: a1.timestamp
        });
      }
    }
    return groups;
  };

  const renderRcaBlock = (alert) => {
    const inv = getInvestigation(alert.fingerprint || alert.id);
    // Root-cause analysis is on-demand now (the "Investigate with AI" button on
    // the Diagnose tab), not automatic - so there is no perpetual "investigating…"
    // spinner here. The synthesis renders only once an investigation actually
    // exists for this alert; otherwise the block is absent.
    if (!inv) return null;
    const affected = inv.affected_equipment || [];

    return (
      <div className="rounded-lg p-3 border mt-2" style={{ background: "rgba(241,245,249,0.3)", borderColor: "var(--border)" }}>
        <div className="flex items-center justify-between mb-2">
          <div className="font-bold text-slate-800 text-[10px] uppercase tracking-wider">
            🤖 Agent Grounded RCA Synthesis
          </div>
          <div className="text-[9px] font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded">
            Grounding: Grounded
          </div>
        </div>

        <div className="space-y-3">
            <div className="prose prose-sm max-w-none text-xs text-slate-700">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{inv.summary || inv.text || ""}</ReactMarkdown>
            </div>

            {/* Affected Equipment */}
            {affected.length > 0 && (
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-widest text-slate-400 mb-1">Affected Equipment Chain</div>
                <div className="flex flex-wrap items-center gap-1">
                  {affected.map((item, idx) => (
                    <React.Fragment key={item}>
                      <span className="rounded border px-2 py-0.5 font-mono text-[9px] font-medium bg-white text-slate-700">
                        {item}
                      </span>
                      {idx < affected.length - 1 && <ArrowRight size={10} className="text-slate-300" />}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}

            {/* SOP Citations */}
            {inv.citations && inv.citations.length > 0 && (
              <div>
                <div className="text-[9px] font-semibold uppercase tracking-widest text-slate-400 mb-1">Grounding References & Procedures</div>
                <div className="flex flex-wrap gap-1.5">
                  {inv.citations.map((c, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => onOpenDoc?.(c.doc_id, c.filename || c.doc_id)}
                      className="flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[9px] transition-colors border"
                      style={{ background: "#dbeafe", color: "#1d4ed8", borderColor: "#bfdbfe" }}
                    >
                      <FileText size={10} />
                      {c.filename || c.doc_id}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Discuss Incident with Agent Button */}
            {inv && (
              <div className="mt-3 flex justify-end border-t pt-2.5" style={{ borderColor: "var(--border)" }}>
                <button
                  type="button"
                  onClick={() => setActiveChatAlert({ alert, rca: inv })}
                  className="flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] font-bold bg-blue-50 border border-blue-200 text-blue-700 hover:bg-blue-100 transition-colors shadow-sm"
                >
                  <Sparkles size={11} className="text-blue-500 animate-pulse" />
                  Discuss Incident with Agent
                </button>
              </div>
            )}
          </div>
      </div>
    );
  };

  const renderSeverityBadge = (severity) => {
    const isCrit = severity === "critical";
    return (
      <span
        className={`rounded-full px-1.5 py-0.5 text-[9px] font-bold border`}
        style={{
          background: isCrit ? "rgba(239, 68, 68, 0.08)" : "rgba(245, 158, 11, 0.08)",
          color: isCrit ? "#dc2626" : "#d97706",
          borderColor: isCrit ? "rgba(239, 68, 68, 0.2)" : "rgba(245, 158, 11, 0.2)",
        }}
      >
        {isCrit ? "Critical" : "Warning"}
      </span>
    );
  };

  if (!alerts || alerts.length === 0) {
    return (
      <div
        className="rounded-xl p-6 text-center text-xs text-slate-400 shadow-sm"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
      >
        No active process alerts. Simulators operating within envelopes.
      </div>
    );
  }

  const groupedItems = groupAlerts(alerts);

  return (
    <div
      className="rounded-xl p-4 shadow-sm"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between border-b pb-2 mb-3" style={{ borderColor: "var(--border)" }}>
        <h3 className="text-sm font-semibold flex items-center gap-2" style={{ color: "var(--text-md)" }}>
          <AlertCircle size={15} className="text-rose-500" />
          Active Process Alerts & Agent Investigations ({alerts.length})
        </h3>
      </div>

      <div className="flex flex-col lg:flex-row gap-4 items-start">
        <div className={`space-y-3 flex-1 w-full ${activeChatAlert ? "max-h-[500px] overflow-y-auto pr-1" : ""}`}>
          {groupedItems.map((item) => {
            if (item.type === "group") {
              const isExpanded = expandedId === item.id;
              const isGroupAcked = item.alerts.every(a => ackIds.has(a.id));

              return (
                <div
                  key={item.id}
                  className="rounded-lg border-2 transition-all overflow-hidden"
                  style={{
                    borderColor: isExpanded ? "rgba(124, 58, 237, 0.4)" : "rgba(124, 58, 237, 0.2)",
                    background: isExpanded ? "rgba(124, 58, 237, 0.02)" : "rgba(124, 58, 237, 0.01)",
                    opacity: isGroupAcked ? 0.55 : 1
                  }}
                >
                  {/* Group Header */}
                  <div
                    onClick={() => toggleExpand(item.id)}
                    className="flex cursor-pointer items-center justify-between p-3 gap-3"
                  >
                    <div className="flex items-center gap-3">
                      <div className="grid h-7 w-7 place-items-center rounded bg-violet-100 text-violet-700">
                        <Link2 size={14} className="animate-pulse" />
                      </div>
                      <div>
                        <div className="text-xs font-bold text-violet-900 flex items-center gap-1.5">
                          {item.title}
                        </div>
                        <div className="text-[10px] text-violet-700/80">
                          Incident propagation: <span className="font-semibold">{item.alerts[0].equipment}</span>
                          {" "}→{" "}
                          <span className="font-semibold">{item.alerts[1].equipment}</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          // Toggle ack state for all alerts in group
                          setAckIds(prev => {
                            const next = new Set(prev);
                            const allAcked = item.alerts.every(a => next.has(a.id));
                            item.alerts.forEach(a => {
                              if (allAcked) next.delete(a.id);
                              else next.add(a.id);
                            });
                            return next;
                          });
                        }}
                        className={`flex items-center gap-1 rounded border px-2 py-0.5 text-[9px] font-bold transition-all ${
                          isGroupAcked
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <CheckCircle2 size={10} />
                        {isGroupAcked ? "Acknowledged" : "Acknowledge Incident"}
                      </button>
                      <span className="text-[10px] text-slate-400">
                        {new Date(item.timestamp).toLocaleTimeString()}
                      </span>
                      {isExpanded ? <ChevronUp size={14} className="text-slate-400" /> : <ChevronDown size={14} className="text-slate-400" />}
                    </div>
                  </div>

                  {/* Expanded Group Details */}
                  {isExpanded && (
                    <div className="border-t p-3 space-y-4 bg-white" style={{ borderColor: "rgba(124, 58, 237, 0.15)" }}>
                      <div className="grid gap-3 md:grid-cols-2">
                        {item.alerts.map((alert, idx) => (
                          <div key={alert.id} className="rounded-lg border p-3 bg-slate-50/50" style={{ borderColor: "var(--border)" }}>
                            <div className="flex items-start justify-between gap-2 mb-2">
                              <div>
                                <div className="text-xs font-bold text-slate-800">{alert.title}</div>
                                <div className="text-[9px] text-slate-400 mt-0.5">
                                  Tag: <span className="font-mono">{alert.tag_id}</span> | Value: {alert.value}
                                </div>
                              </div>
                              {renderSeverityBadge(alert.severity)}
                            </div>
                            <p className="text-[11px] text-slate-600 mb-2">{alert.body}</p>
                            {renderRcaBlock(alert)}
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              );
            } else {
              // Single Alert
              const alert = item.alert;
              const isExpanded = expandedId === alert.id;
              const isAcked = ackIds.has(alert.id);

              return (
                <div
                  key={alert.id}
                  className="rounded-lg border transition-all"
                  style={{
                    borderColor: isExpanded ? "var(--blue-mid)" : "var(--border)",
                    background: isExpanded ? "rgba(248,250,252,0.4)" : "transparent",
                    opacity: isAcked ? 0.55 : 1
                  }}
                >
                  {/* Header block */}
                  <div
                    onClick={() => toggleExpand(alert.id)}
                    className="flex cursor-pointer items-center justify-between p-3 gap-3"
                  >
                    <div className="flex items-center gap-2.5">
                      <div className="grid h-7 w-7 place-items-center rounded bg-rose-50 text-rose-700">
                        <AlertTriangle size={13} />
                      </div>
                      <div>
                        <div className="text-xs font-bold" style={{ color: "var(--text)" }}>
                          {alert.title}
                        </div>
                        <div className="text-[10px]" style={{ color: "var(--muted)" }}>
                          Tag: <span className="font-mono">{alert.tag_id}</span> | Value: {alert.value} (Limit: {alert.threshold})
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-3">
                      {renderSeverityBadge(alert.severity)}
                      <button
                        onClick={(e) => toggleAck(e, alert.id)}
                        className={`flex items-center gap-1 rounded border px-2 py-0.5 text-[9px] font-bold transition-all ${
                          isAcked
                            ? "bg-emerald-50 text-emerald-700 border-emerald-200"
                            : "bg-white text-slate-600 border-slate-300 hover:bg-slate-50"
                        }`}
                      >
                        <CheckCircle2 size={10} />
                        {isAcked ? "Acknowledged" : "Acknowledge"}
                      </button>
                      <span className="text-[10px]" style={{ color: "var(--muted-lt)" }}>
                        {alert.timestamp ? new Date(alert.timestamp).toLocaleTimeString() : ""}
                      </span>
                      {isExpanded ? <ChevronUp size={14} style={{ color: "var(--muted)" }} /> : <ChevronDown size={14} style={{ color: "var(--muted)" }} />}
                    </div>
                  </div>

                  {/* Expanded details */}
                  {isExpanded && (
                    <div className="border-t p-3 text-xs leading-relaxed space-y-3" style={{ borderColor: "var(--border)" }}>
                      <div>
                        <div className="font-semibold text-slate-500 uppercase tracking-wider text-[9px] mb-1.5">Process Breach Summary</div>
                        <div className="prose prose-sm max-w-none text-xs leading-relaxed dark:prose-invert" style={{ color: "var(--text-md)" }}>
                          <ReactMarkdown remarkPlugins={[remarkGfm]}>{alert.body || alert.message || ""}</ReactMarkdown>
                        </div>
                      </div>
                      {renderRcaBlock(alert)}
                    </div>
                  )}
                </div>
              );
            }
          })}
        </div>

        {activeChatAlert && (
          <div className="w-full lg:w-[380px] sticky top-0 shrink-0">
            <AlertChat
              alert={activeChatAlert.alert}
              rca={activeChatAlert.rca}
              onClose={() => setActiveChatAlert(null)}
              onOpenDoc={onOpenDoc}
            />
          </div>
        )}
      </div>
    </div>
  );
}

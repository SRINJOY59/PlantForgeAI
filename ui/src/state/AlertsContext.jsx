import { createContext, useContext, useEffect, useRef, useState } from "react";
import { subscribeAlerts, getCompliance, getInitialAlerts } from "../lib/api";

const AlertsContext = createContext(null);

const FEED_LIMIT = 200;

const isSimulationEvent = (a) =>
  a?.kind === "process_limit" ||
  a?.type === "investigation" ||
  a?.fingerprint?.startsWith("tep:") ||
  a?.fingerprint?.startsWith("cstr:") ||
  a?.fingerprint?.startsWith("column:");

export function AlertsProvider({ children }) {
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const [connected, setConnected] = useState(false);
  const seen = useRef(new Set());

  // Load real statutory compliance and graph failure patterns dynamically
  useEffect(() => {
    Promise.all([
      getCompliance().catch(() => ({ items: [] })),
      getInitialAlerts().catch(() => []),
    ]).then(([complianceData, graphFailures]) => {
      const complianceAlerts = (complianceData?.items || [])
        .filter((item) => item.status === "overdue" || item.status === "due_soon")
        .map((item) => ({
          id: item.id,
          title: `Statutory Inspection Overdue: ${item.equipment} (${item.standard})`,
          body: `**Obligation**: ${item.inspection_type} under **${item.standard}**.\n\n* **Asset**: \`${item.equipment}\`\n* **Due Date**: **${item.next_due}** (Past Due)\n* **Last Done**: ${item.last_inspection || "N/A"}\n\nImmediate maintenance action required to maintain statutory operating compliance.`,
          kind: item.standard?.includes("OISD") || item.standard?.includes("IBR") ? "compliance" : "standard_revision",
          severity: item.status === "overdue" ? "critical" : "warning",
          equipment: item.equipment,
          standard: item.standard,
          doc_id: item.doc_id,
          page: item.page,
          verified: true,
        }));

      setAlerts((prev) => {
        const combined = [...prev];
        for (const a of [...complianceAlerts, ...(graphFailures || [])]) {
          if (!isSimulationEvent(a) && !seen.current.has(a.id)) {
            seen.current.add(a.id);
            combined.push(a);
          }
        }
        return combined.slice(0, FEED_LIMIT);
      });
    });
  }, []);

  // Listen to real-time live plant events (filtering out transient simulation noise)
  useEffect(() => {
    let stop = () => {};
    try {
      stop = subscribeAlerts((alert) => {
        if (seen.current.has(alert.id)) return;
        seen.current.add(alert.id);
        setConnected(true);
        if (isSimulationEvent(alert)) return;
        setAlerts((prev) => [alert, ...prev].slice(0, FEED_LIMIT));
        setUnread((n) => n + 1);
      });
    } catch {
      // gateway not up yet - the rest of the app still works
    }
    return () => stop();
  }, []);

  const value = { alerts, unread, connected, markAllRead: () => setUnread(0) };
  return (
    <AlertsContext.Provider value={value}>{children}</AlertsContext.Provider>
  );
}

export const useAlerts = () => useContext(AlertsContext);

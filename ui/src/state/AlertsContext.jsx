import { createContext, useContext, useEffect, useRef, useState } from "react";
import { subscribeAlerts } from "../lib/api";

const AlertsContext = createContext(null);

export function AlertsProvider({ children }) {
  const [alerts, setAlerts] = useState([]);
  const [unread, setUnread] = useState(0);
  const [connected, setConnected] = useState(false);
  const seen = useRef(new Set());

  useEffect(() => {
    let stop = () => {};
    try {
      stop = subscribeAlerts((alert) => {
        if (seen.current.has(alert.id)) return;
        seen.current.add(alert.id);
        setConnected(true);
        setAlerts((prev) => [alert, ...prev].slice(0, 100));
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

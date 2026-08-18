import { createContext, useContext, useEffect, useRef, useState } from "react";
import { subscribeAlerts } from "../lib/api";

const AlertsContext = createContext(null);

// How many events the feed holds. The stream is replayed from the start on
// connect, so this is a window on the newest end of it, not a quota.
const FEED_LIMIT = 200;

// The simulator's process alarms and the RCA investigations that answer them
// share alerts:critical with the agent alerts — one stream, deliberately, so
// the Simulation page can tail both from its own socket. They do not belong on
// this feed, and not merely because they are noise: a single fault injection
// puts dozens of tag-level entries on the stream, and since the feed keeps the
// newest N, an afternoon of simulator work silently evicts every compliance
// and failure-pattern alert from the page whose whole job is to show them.
// Simulation traffic is shown on the Simulation page, which has the tag
// context to make sense of it.
const isSimulationEvent = (a) =>
  a?.kind === "process_limit" || a?.type === "investigation";

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
        // connected tracks the socket, so it is set for every event that
        // arrives — including the ones this feed then drops
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

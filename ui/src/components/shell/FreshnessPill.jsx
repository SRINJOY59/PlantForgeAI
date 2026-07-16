import { useEffect, useState } from "react";
import { metrics } from "../../lib/api";

export default function FreshnessPill() {
  const [version, setVersion] = useState(null);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let active = true;
    const poll = async () => {
      try {
        const m = await metrics();
        if (!active) return;
        setVersion(m.graph_version);
        setLive(true);
      } catch {
        if (active) setLive(false);
      }
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => { active = false; clearInterval(id); };
  }, []);

  return (
    <div
      className="hidden md:flex items-center gap-2 rounded-full px-3 py-1 text-xs font-medium"
      style={
        live
          ? { background: "#dcfce7", color: "#166534", border: "1px solid #bbf7d0" }
          : { background: "#f1f5f9", color: "var(--muted)", border: "1px solid var(--border)" }
      }
    >
      <span
        className="h-1.5 w-1.5 rounded-full flex-shrink-0"
        style={{ background: live ? "#16a34a" : "#cbd5e1" }}
      />
      {live ? `graph v${version ?? "—"} · live` : "brain offline"}
    </div>
  );
}

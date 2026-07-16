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
    return () => {
      active = false;
      clearInterval(id);
    };
  }, []);

  return (
    <div className="hidden items-center gap-2 rounded-full border border-gray-200 px-3 py-1 text-xs muted dark:border-slate-800 md:flex">
      <span
        className={`h-1.5 w-1.5 rounded-full ${
          live ? "bg-emerald-500" : "bg-gray-400"
        }`}
      />
      {live ? `live · graph v${version ?? "—"}` : "brain offline"}
    </div>
  );
}

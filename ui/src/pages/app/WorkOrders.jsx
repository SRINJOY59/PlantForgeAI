import { useEffect, useState, useRef } from "react";
import { ClipboardList, Check } from "lucide-react";
import { subscribeDraftWorkOrders } from "../../lib/api";

export default function WorkOrders() {
  const [drafts, setDrafts] = useState([]);
  const seen = useRef(new Set());
  const [approved, setApproved] = useState(new Set());

  useEffect(() => {
    let stop = () => {};
    try {
      stop = subscribeDraftWorkOrders((draft) => {
        if (seen.current.has(draft.id)) return;
        seen.current.add(draft.id);
        setDrafts((prev) => [draft, ...prev]);
      });
    } catch {
      // ignore
    }
    return () => stop();
  }, []);

  const handleApprove = (id) => {
    setApproved((prev) => {
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col px-6 py-6">
      <div className="mb-6 flex items-center gap-3">
        <div>
          <h1 className="page-title flex items-center gap-3">
            Pending Work Orders
          </h1>
          <p className="text-xs mt-0.5" style={{ color: "var(--muted)" }}>
            Drafted by the AI runtime based on failure investigations
          </p>
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto space-y-4">
        {drafts.length === 0 ? (
          <div className="flex h-40 flex-col items-center justify-center gap-3 text-center">
            <div className="grid h-16 w-16 place-items-center rounded-2xl"
              style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
              <ClipboardList size={28} style={{ color: "var(--muted-lt)" }} />
            </div>
            <div>
              <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>No pending drafts</p>
            </div>
          </div>
        ) : (
          drafts.map((d) => (
            <div key={d.id} className="rounded-xl p-4 flex flex-col gap-3"
                 style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
              <div className="flex justify-between items-start">
                <div className="flex items-center gap-2">
                  <ClipboardList size={16} style={{ color: "var(--blue)" }} />
                  <span className="font-semibold text-sm">Work Order Draft - {d.equipment_id}</span>
                </div>
                {approved.has(d.id) ? (
                  <span className="flex items-center gap-1 text-xs font-medium px-2 py-1 rounded"
                        style={{ color: "var(--success)", background: "rgba(16, 185, 129, 0.1)" }}>
                    <Check size={14} /> Approved
                  </span>
                ) : (
                  <button onClick={() => handleApprove(d.id)}
                          className="px-3 py-1.5 rounded text-xs font-medium flex items-center gap-1.5 transition-colors"
                          style={{ background: "var(--blue)", color: "white" }}>
                    <Check size={14} /> Approve
                  </button>
                )}
              </div>
              
              <div className="grid gap-2 text-sm mt-2">
                <div>
                  <span className="font-medium text-xs block mb-1" style={{ color: "var(--muted)" }}>Root Cause</span>
                  <p className="leading-relaxed" style={{ color: "var(--text-md)" }}>{d.root_cause}</p>
                </div>
                <div>
                  <span className="font-medium text-xs block mb-1" style={{ color: "var(--muted)" }}>Recommended Fix</span>
                  <p className="leading-relaxed" style={{ color: "var(--text-md)" }}>{d.recommended_fix}</p>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

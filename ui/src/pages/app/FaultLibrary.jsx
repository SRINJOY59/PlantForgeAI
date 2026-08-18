// Fault Mode Library — the plant's learned fault fingerprints.
//
// Each card is one FaultMode: the known cause (IDV), the equipment it touches,
// the deviation cascade, severity, and linked procedure. Populated by
// build_fault_library or the diagnostics service, stored in Neo4j.

import { useEffect, useMemo, useState } from "react";
import {
  Activity, AlertTriangle, Search, ChevronDown, ChevronUp,
  Cpu, ArrowRight, Loader2, Database,
} from "lucide-react";
import { fetchFaultLibrary } from "../../lib/api";

const SEV_COLORS = {
  critical: { bg: "#fee2e2", border: "#fca5a5", text: "#dc2626", label: "Critical" },
  warning:  { bg: "#fef3c7", border: "#fcd34d", text: "#d97706", label: "Warning" },
  info:     { bg: "#e0f2fe", border: "#7dd3fc", text: "#0284c7", label: "Info" },
};

export default function FaultLibrary() {
  const [library, setLibrary] = useState(null);
  const [error, setError] = useState(null);
  const [search, setSearch] = useState("");
  const [filterSev, setFilterSev] = useState("all");
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    let live = true;
    fetchFaultLibrary()
      .then((d) => live && setLibrary(d))
      .catch((e) => {
        if (!live) return;
        setError("Couldn't load the fault library. Is the backend running?");
      });
    return () => { live = false; };
  }, []);

  const filtered = useMemo(() => {
    if (!library) return [];
    const q = search.trim().toLowerCase();
    return library.filter((fm) =>
      (filterSev === "all" || fm.severity === filterSev) &&
      (q === "" ||
        (fm.cause_label || "").toLowerCase().includes(q) ||
        (fm.cause_id || "").toLowerCase().includes(q) ||
        (fm.lead_tag || "").toLowerCase().includes(q) ||
        (fm.unit_areas || []).some((a) => a.toLowerCase().includes(q))));
  }, [library, search, filterSev]);

  if (error) {
    return (
      <div className="h-full overflow-y-auto flex flex-col items-center justify-center p-8 text-center" style={{ color: "var(--muted)" }}>
        <AlertTriangle size={32} style={{ marginBottom: 8, color: "#d97706" }} />
        <p>{error}</p>
      </div>
    );
  }

  if (!library) {
    return (
      <div className="h-full overflow-y-auto flex flex-col items-center justify-center p-8 text-center" style={{ color: "var(--muted)" }}>
        <Loader2 size={28} className="animate-spin" style={{ margin: "0 auto 8px" }} />
        <p>Loading fault library…</p>
      </div>
    );
  }

  const sevCounts = { critical: 0, warning: 0, info: 0 };
  library.forEach((fm) => { if (sevCounts[fm.severity] !== undefined) sevCounts[fm.severity]++; });

  return (
    <div className="h-full overflow-y-auto" style={{ padding: "24px 32px" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ fontSize: 22, fontWeight: 700, color: "var(--fg)", display: "flex", alignItems: "center", gap: 10 }}>
          <Database size={22} /> Fault Mode Library
        </h1>
        <p style={{ color: "var(--muted)", fontSize: 14, marginTop: 4 }}>
          {library.length} learned fault fingerprints from simulator campaigns
        </p>
      </div>

      {/* Summary cards */}
      <div style={{ display: "flex", gap: 12, marginBottom: 20, flexWrap: "wrap" }}>
        {Object.entries(SEV_COLORS).map(([key, cfg]) => (
          <button
            key={key}
            onClick={() => setFilterSev(filterSev === key ? "all" : key)}
            style={{
              flex: "1 1 140px",
              padding: "14px 16px",
              borderRadius: 10,
              border: `1.5px solid ${filterSev === key ? cfg.text : cfg.border}`,
              background: cfg.bg,
              cursor: "pointer",
              textAlign: "left",
              transition: "all .15s",
              opacity: filterSev !== "all" && filterSev !== key ? 0.5 : 1,
            }}
          >
            <div style={{ fontSize: 24, fontWeight: 700, color: cfg.text }}>{sevCounts[key]}</div>
            <div style={{ fontSize: 12, fontWeight: 600, color: cfg.text, textTransform: "uppercase", letterSpacing: 0.5 }}>
              {cfg.label}
            </div>
          </button>
        ))}
      </div>

      {/* Search */}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        background: "var(--bg-panel)", border: "1px solid var(--border)",
        borderRadius: 8, padding: "8px 14px", marginBottom: 16,
      }}>
        <Search size={16} style={{ color: "var(--muted)" }} />
        <input
          type="text"
          placeholder="Search by cause, tag, or unit area…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          style={{
            flex: 1, border: "none", outline: "none", background: "transparent",
            fontSize: 14, color: "var(--fg)",
          }}
        />
      </div>

      {/* List */}
      {filtered.length === 0 ? (
        <div style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>
          {library.length === 0
            ? "No fault modes stored yet. Run the fault library campaign to populate."
            : "No fault modes match your search."}
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
          {filtered.map((fm) => {
            const isOpen = expanded === fm.id;
            const sev = SEV_COLORS[fm.severity] || SEV_COLORS.warning;
            const sig = fm.signature;
            const deviations = sig?.deviations || [];

            return (
              <div
                key={fm.id}
                style={{
                  background: "var(--bg-panel)",
                  border: `1px solid ${isOpen ? sev.border : "var(--border)"}`,
                  borderRadius: 10,
                  overflow: "hidden",
                  transition: "border-color .15s",
                }}
              >
                {/* Card header */}
                <button
                  onClick={() => setExpanded(isOpen ? null : fm.id)}
                  style={{
                    width: "100%", padding: "14px 18px", cursor: "pointer",
                    display: "flex", alignItems: "center", gap: 12,
                    border: "none", background: "transparent", textAlign: "left",
                  }}
                >
                  <Activity size={18} style={{ color: sev.text, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                      <span style={{ fontWeight: 700, fontSize: 15, color: "var(--fg)" }}>
                        {fm.cause_id || fm.id}
                      </span>
                      <span style={{
                        fontSize: 11, fontWeight: 600, padding: "2px 8px",
                        borderRadius: 6, background: sev.bg, color: sev.text,
                        border: `1px solid ${sev.border}`,
                      }}>
                        {sev.label}
                      </span>
                    </div>
                    <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 2, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                      {fm.cause_label || "Unknown fault mode"}
                    </div>
                  </div>

                  {/* Unit areas pills */}
                  <div style={{ display: "flex", gap: 4, flexWrap: "wrap", flexShrink: 0 }}>
                    {(fm.unit_areas || []).slice(0, 4).map((area) => (
                      <span key={area} style={{
                        fontSize: 11, fontWeight: 500, padding: "2px 8px",
                        borderRadius: 5, background: "var(--bg-main)", color: "var(--fg)",
                        border: "1px solid var(--border)",
                      }}>
                        <Cpu size={10} style={{ marginRight: 3, verticalAlign: -1 }} />
                        {area}
                      </span>
                    ))}
                  </div>

                  {isOpen ? <ChevronUp size={16} style={{ color: "var(--muted)" }} /> :
                            <ChevronDown size={16} style={{ color: "var(--muted)" }} />}
                </button>

                {/* Expanded detail */}
                {isOpen && (
                  <div style={{
                    padding: "0 18px 18px",
                    borderTop: "1px solid var(--border)",
                    paddingTop: 14,
                  }}>
                    {/* Meta row */}
                    <div style={{ display: "flex", gap: 24, fontSize: 13, color: "var(--muted)", marginBottom: 14, flexWrap: "wrap" }}>
                      <span><strong>Lead Tag:</strong> {fm.lead_tag || "—"}</span>
                      <span><strong>Window:</strong> {sig?.window_s ? `${sig.window_s}s` : "—"}</span>
                      <span><strong>Source:</strong> {fm.source || "sim"}</span>
                      {fm.procedure_name && (
                        <span><strong>SOP:</strong> {fm.procedure_name}</span>
                      )}
                    </div>

                    {/* Deviation cascade */}
                    {deviations.length > 0 && (
                      <div>
                        <h4 style={{ fontSize: 13, fontWeight: 600, color: "var(--fg)", marginBottom: 8 }}>
                          Deviation Cascade ({deviations.length} tags)
                        </h4>
                        <div style={{
                          display: "grid",
                          gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))",
                          gap: 8,
                        }}>
                          {deviations.map((d, i) => (
                            <div
                              key={d.tag_id}
                              style={{
                                display: "flex", alignItems: "center", gap: 8,
                                padding: "8px 12px", borderRadius: 7,
                                background: i === 0 ? sev.bg : "var(--bg-main)",
                                border: `1px solid ${i === 0 ? sev.border : "var(--border)"}`,
                                fontSize: 13,
                              }}
                            >
                              <span style={{
                                width: 20, height: 20, borderRadius: "50%",
                                display: "flex", alignItems: "center", justifyContent: "center",
                                fontSize: 10, fontWeight: 700,
                                background: i === 0 ? sev.text : "var(--border)",
                                color: i === 0 ? "#fff" : "var(--fg)",
                                flexShrink: 0,
                              }}>
                                {i + 1}
                              </span>
                              <div style={{ flex: 1, minWidth: 0 }}>
                                <div style={{ fontWeight: 600, color: "var(--fg)" }}>{d.tag_id}</div>
                                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                                  {d.direction === "high" ? "↑" : "↓"} {d.magnitude}σ
                                  {" · "}onset +{d.onset_offset_s}s
                                </div>
                              </div>
                              {i < deviations.length - 1 && (
                                <ArrowRight size={12} style={{ color: "var(--muted)", flexShrink: 0 }} />
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
      </div>
    </div>
  );
}

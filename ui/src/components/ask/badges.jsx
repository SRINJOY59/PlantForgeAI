const MODE_CONFIG = {
  vector: { label: "Vector",  bg: "#ede9fe", color: "#5b21b6" },
  local:  { label: "Local",   bg: "var(--brand-light)", color: "var(--brand-dark)" },
  path:   { label: "PathRAG", bg: "#dcfce7", color: "#166534" },
};
const CONF_CONFIG = {
  high:   { bg: "#dcfce7", color: "#166534" },
  medium: { bg: "#fef3c7", color: "#92400e" },
  low:    { bg: "var(--bg-subtle)", color: "var(--text-md)" },
};

export function ModeBadge({ mode }) {
  const cfg = MODE_CONFIG[mode] ?? { label: mode ?? "—", bg: "var(--bg-subtle)", color: "var(--text-md)" };
  return <span className="badge" style={{ background: cfg.bg, color: cfg.color }}>{cfg.label}</span>;
}

export function ConfidencePill({ confidence }) {
  const cfg = CONF_CONFIG[confidence] ?? CONF_CONFIG.low;
  return <span className="badge" style={{ background: cfg.bg, color: cfg.color }}>{confidence ?? "—"} confidence</span>;
}

const MODE_LABEL = {
  vector: "Vector",
  local: "Local",
  path: "PathRAG",
};

export function ModeBadge({ mode }) {
  return (
    <span className="rounded border border-steel-200 bg-steel-50 px-1.5 py-0.5 text-[11px] font-medium text-steel-700 dark:border-steel-800 dark:bg-steel-950 dark:text-steel-300">
      {MODE_LABEL[mode] ?? mode}
    </span>
  );
}

const CONF_STYLE = {
  high: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300",
  medium: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300",
  low: "bg-gray-100 text-gray-600 dark:bg-slate-800 dark:text-slate-400",
};

export function ConfidencePill({ confidence }) {
  return (
    <span className={`rounded px-1.5 py-0.5 text-[11px] font-medium ${CONF_STYLE[confidence] ?? CONF_STYLE.low}`}>
      {confidence} confidence
    </span>
  );
}

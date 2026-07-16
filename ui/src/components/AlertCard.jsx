import { AlertTriangle, ShieldAlert, Wrench } from "lucide-react";

const SEVERITY = {
  critical: { ring: "border-l-red-500", chip: "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300" },
  warning: { ring: "border-l-amber-500", chip: "bg-amber-50 text-amber-700 dark:bg-amber-950/50 dark:text-amber-300" },
  info: { ring: "border-l-steel-500", chip: "bg-steel-50 text-steel-700 dark:bg-steel-950 dark:text-steel-300" },
};

export default function AlertCard({ alert }) {
  const s = SEVERITY[alert.severity] ?? SEVERITY.info;
  const Icon = alert.kind === "compliance" ? ShieldAlert : Wrench;
  return (
    <div className={`surface rounded-lg border-l-4 p-4 ${s.ring}`}>
      <div className="flex items-center gap-2">
        <Icon size={16} className="text-gray-500" />
        <span className="font-medium">{alert.title}</span>
        <span className={`ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium capitalize ${s.chip}`}>
          {alert.severity}
        </span>
      </div>
      {alert.equipment && (
        <div className="mt-1 tag text-xs muted">{alert.equipment}</div>
      )}
      <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-slate-300">
        {alert.body}
      </p>
      {alert.verified === false && (
        <div className="mt-2 flex items-center gap-1 text-[11px] text-red-600">
          <AlertTriangle size={11} /> unverified — some claims not grounded in evidence
        </div>
      )}
      {alert.citations?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {alert.citations.map((c, i) => (
            <span key={i} className="tag rounded bg-gray-100 px-1.5 py-0.5 text-[11px] muted dark:bg-slate-800">
              {c.doc_id}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

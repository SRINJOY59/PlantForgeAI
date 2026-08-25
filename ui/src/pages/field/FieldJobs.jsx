// The far end of the loop that starts with an engineer pressing Schedule Work.
//
// By the time a card appears on this screen, three things have already
// happened: an engineer proposed a slot, somebody authorised it in Slack, and
// the order was rewritten into a job card in this worker's own language. So
// this screen has exactly one job — make that card readable one-handed, at the
// equipment, in poor light, by someone wearing gloves.
//
// Which means it is built the opposite way to the engineer's console. No
// evidence chips, no grounding banner, no citations: none of that helps the
// person holding the spanner, and a screen full of it is how a safety line
// gets scrolled past. Safety comes FIRST, before the steps, because it is the
// part that must be read before anything is touched.
//
// The original English travels with every card and is one tap away. When a
// translation reads oddly — and eventually one will — a worker needs to be
// able to see what it was translated from, and show it to somebody, without
// waiting on a round trip.

import { useEffect, useState } from "react";
import {
  ClipboardList, ShieldAlert, HardHat, Check, Play, Clock, RefreshCw,
  ChevronDown, ChevronUp, Languages, AlertTriangle, FileText,
} from "lucide-react";
import { getMyAssignments, updateAssignmentStatus } from "../../lib/api";
import { t } from "../../lib/i18n";
import { useFieldLang } from "../../components/field/FieldShell";

const PRIORITY = {
  immediate: { color: "#dc2626", bg: "#fee2e2" },
  high:      { color: "#c2410c", bg: "#ffedd5" },
  medium:    { color: "#a16207", bg: "#fef3c7" },
  low:       { color: "#0369a1", bg: "#e0f2fe" },
};

// What a worker can do to a job, and what it looks like when they have.
// Forward-only: there is no button here that un-does a state, because the
// record is evidence about work on live plant rather than a to-do list.
const FLOW = {
  assigned:     { next: "acknowledged", labelKey: "job_accept",   icon: Check },
  acknowledged: { next: "in_progress",  labelKey: "job_start",    icon: Play },
  in_progress:  { next: "done",         labelKey: "job_done",     icon: Check },
  done:         { next: null },
};

export default function FieldJobs() {
  const { lang } = useFieldLang();
  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(null);

  async function load() {
    setError(null);
    try {
      setJobs(await getMyAssignments());
    } catch {
      setError(t("offline", lang));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // A dispatch can land while the phone is sitting in a pocket, and there is
    // no push channel on this persona. A slow poll costs one small request a
    // minute and means a worker does not have to know to pull-to-refresh.
    const timer = setInterval(load, 60000);
    return () => clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function advance(job) {
    const step = FLOW[job.status ?? "assigned"];
    if (!step?.next) return;
    setBusy(job.id);
    try {
      const updated = await updateAssignmentStatus(job.id, step.next);
      setJobs((prev) => prev.map((j) => (j.id === job.id ? updated : j)));
    } catch {
      setError(t("offline", lang));
    } finally {
      setBusy(null);
    }
  }

  const open = jobs.filter((j) => (j.status ?? "assigned") !== "done");
  const closed = jobs.filter((j) => (j.status ?? "assigned") === "done");

  return (
    <div className="flex h-full flex-col overflow-y-auto px-4 py-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold" style={{ color: "var(--text)" }}>
          {t("jobs_title", lang)}
        </h2>
        <button onClick={load} aria-label={t("jobs_refresh", lang)}
          className="btn-ghost grid h-8 w-8 place-items-center rounded-lg">
          <RefreshCw size={14} />
        </button>
      </div>

      {error && (
        <div className="mb-3 rounded-xl px-3 py-2 text-xs"
          style={{ background: "#fee2e2", color: "#991b1b",
                   border: "1px solid #fca5a5" }}>
          {error}
        </div>
      )}

      {loading ? (
        <p className="text-xs italic" style={{ color: "var(--muted)" }}>
          {t("thinking", lang)}
        </p>
      ) : jobs.length === 0 ? (
        <Empty lang={lang} />
      ) : (
        <div className="space-y-3 pb-4">
          {open.map((j) => (
            <JobCard key={j.id} job={j} lang={lang} busy={busy === j.id}
              onAdvance={() => advance(j)} />
          ))}
          {closed.length > 0 && (
            <>
              <div className="pt-2 text-[10px] font-semibold uppercase tracking-widest"
                style={{ color: "var(--muted-lt)" }}>
                {t("jobs_completed", lang)}
              </div>
              {closed.map((j) => (
                <JobCard key={j.id} job={j} lang={lang} busy={false}
                  onAdvance={() => {}} />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function JobCard({ job, lang, busy, onAdvance }) {
  const [showEnglish, setShowEnglish] = useState(false);
  const [expanded, setExpanded] = useState(true);

  const p = PRIORITY[job.priority] ?? PRIORITY.medium;
  const status = job.status ?? "assigned";
  const step = FLOW[status] ?? FLOW.assigned;
  const StepIcon = step.icon;

  // The worker's own language by default. The English source is not a second
  // job — it is the same one, shown for checking, so it swaps in place rather
  // than opening anywhere.
  const translated = job.brief || {};
  const original = job.brief_en || {};
  const brief = showEnglish ? original : translated;
  const canCompare = original.title && (translated.lang || "en") !== "en";

  return (
    <div className="overflow-hidden rounded-xl"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)",
               borderLeft: `4px solid ${p.color}` }}>

      <button onClick={() => setExpanded((v) => !v)}
        className="flex w-full items-start gap-2 px-4 pt-3 text-left">
        <ClipboardList size={16} className="mt-0.5 flex-shrink-0"
          style={{ color: p.color }} />
        <div className="min-w-0 flex-1">
          <h3 className="text-sm font-semibold leading-snug"
            style={{ color: "var(--text)" }}>
            {brief.title || job.equipment}
          </h3>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <span className="rounded px-1.5 py-0.5 font-mono text-[10px]"
              style={{ background: p.bg, color: p.color }}>
              {job.equipment}
            </span>
            <StatusChip status={status} lang={lang} />
          </div>
        </div>
        {expanded ? <ChevronUp size={16} style={{ color: "var(--muted)" }} />
                  : <ChevronDown size={16} style={{ color: "var(--muted)" }} />}
      </button>

      {expanded && (
        <div className="space-y-3 px-4 pb-4 pt-3">
          {job.window_start && (
            <div className="flex items-center gap-1.5 text-[11px]"
              style={{ color: "var(--muted)" }}>
              <Clock size={11} />
              {String(job.window_start).replace("T", " ")}
              {job.window_end ? ` → ${String(job.window_end).replace("T", " ")}` : ""}
            </div>
          )}

          {brief.summary && (
            <p className="text-[13px] leading-relaxed" style={{ color: "var(--text-md)" }}>
              {brief.summary}
            </p>
          )}

          {/* Safety before steps, always. Nothing on this card matters if this
              part is not read first. */}
          <SafetyBlock items={brief.safety} ppe={brief.ppe} lang={lang} />

          {brief.steps?.length > 0 && (
            <div>
              <SectionLabel>{t("job_steps", lang)}</SectionLabel>
              <ol className="space-y-1.5">
                {brief.steps.map((s, i) => (
                  <li key={i} className="flex gap-2.5 text-[13px] leading-relaxed"
                    style={{ color: "var(--text-md)" }}>
                    <span className="grid h-5 w-5 flex-shrink-0 place-items-center rounded-full text-[10px] font-bold"
                      style={{ background: "var(--brand-light)", color: "var(--blue)" }}>
                      {i + 1}
                    </span>
                    <span>{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}

          {brief.references?.length > 0 && (
            <div>
              <SectionLabel>{t("job_references", lang)}</SectionLabel>
              <div className="flex flex-wrap gap-1.5">
                {brief.references.map((r, i) => (
                  <span key={i}
                    className="flex items-center gap-1 rounded px-1.5 py-0.5 font-mono text-[11px]"
                    style={{ background: "var(--bg-subtle)", color: "var(--text-md)",
                             border: "1px solid var(--border)" }}>
                    <FileText size={9} style={{ color: "var(--brand)" }} />
                    {r}
                  </span>
                ))}
              </div>
            </div>
          )}

          {job.notes && (
            <div className="rounded-lg px-3 py-2 text-[12px]"
              style={{ background: "var(--bg-subtle)", color: "var(--text-md)",
                       border: "1px solid var(--border)" }}>
              {job.notes}
            </div>
          )}

          <div className="flex flex-wrap items-center gap-2 border-t pt-3"
            style={{ borderColor: "var(--border)" }}>
            {step.next && (
              <button onClick={onAdvance} disabled={busy}
                className="btn-primary flex flex-1 items-center justify-center gap-1.5 px-3 py-2.5 text-sm disabled:opacity-40">
                <StepIcon size={14} />
                {busy ? "…" : t(step.labelKey, lang)}
              </button>
            )}
            {canCompare && (
              <button onClick={() => setShowEnglish((v) => !v)}
                className="btn-ghost flex items-center gap-1.5 px-3 py-2.5 text-xs">
                <Languages size={13} />
                {showEnglish ? t("job_show_mine", lang) : t("job_show_english", lang)}
              </button>
            )}
          </div>

          {job.approved_by && (
            <p className="text-[10px]" style={{ color: "var(--muted-lt)" }}>
              {t("job_authorised_by", lang)} {job.approved_by}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function SafetyBlock({ items, ppe, lang }) {
  const hasSafety = items?.length > 0;
  const hasPpe = ppe?.length > 0;
  if (!hasSafety && !hasPpe) {
    // Said out loud rather than left blank. An empty safety section reads as
    // "nothing to worry about"; this says "we were not told", which is a
    // different and more useful thing for a worker to know.
    return (
      <div className="flex items-start gap-2 rounded-lg px-3 py-2"
        style={{ background: "#fef3c7", border: "1px solid #fde68a" }}>
        <AlertTriangle size={13} className="mt-0.5 flex-shrink-0"
          style={{ color: "#a16207" }} />
        <p className="text-[11px] leading-relaxed" style={{ color: "#854d0e" }}>
          {t("job_no_safety", lang)}
        </p>
      </div>
    );
  }
  return (
    <div className="rounded-lg px-3 py-2.5"
      style={{ background: "#fef2f2", border: "1px solid #fecaca" }}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <ShieldAlert size={12} style={{ color: "#dc2626" }} />
        <span className="text-[10px] font-bold uppercase tracking-widest"
          style={{ color: "#991b1b" }}>{t("job_safety", lang)}</span>
      </div>
      {hasSafety && (
        <ul className="space-y-1">
          {items.map((s, i) => (
            <li key={i} className="flex gap-2 text-[12px] leading-relaxed"
              style={{ color: "#7f1d1d" }}>
              <span aria-hidden="true">•</span><span>{s}</span>
            </li>
          ))}
        </ul>
      )}
      {hasPpe && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <HardHat size={11} style={{ color: "#991b1b" }} />
          {ppe.map((item, i) => (
            <span key={i} className="rounded px-1.5 py-0.5 text-[11px]"
              style={{ background: "#fee2e2", color: "#991b1b" }}>
              {item}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function StatusChip({ status, lang }) {
  const styles = {
    assigned:     { bg: "var(--bg-subtle)", color: "var(--muted)" },
    acknowledged: { bg: "#e0f2fe", color: "#0369a1" },
    in_progress:  { bg: "#fef3c7", color: "#a16207" },
    done:         { bg: "#dcfce7", color: "#166534" },
  }[status] ?? { bg: "var(--bg-subtle)", color: "var(--muted)" };

  return (
    <span className="rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
      style={{ background: styles.bg, color: styles.color }}>
      {t(`job_status_${status}`, lang)}
    </span>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="mb-1.5 text-[9px] font-semibold uppercase tracking-widest"
      style={{ color: "var(--muted-lt)" }}>{children}</div>
  );
}

function Empty({ lang }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
      <div className="grid h-14 w-14 place-items-center rounded-2xl"
        style={{ background: "var(--bg-subtle)", border: "1px solid var(--border)" }}>
        <ClipboardList size={24} style={{ color: "var(--muted-lt)" }} />
      </div>
      <div>
        <p className="text-sm font-medium" style={{ color: "var(--text-md)" }}>
          {t("jobs_empty", lang)}
        </p>
        <p className="mt-0.5 px-6 text-xs" style={{ color: "var(--muted)" }}>
          {t("jobs_empty_hint", lang)}
        </p>
      </div>
    </div>
  );
}

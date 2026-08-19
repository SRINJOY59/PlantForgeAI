// Permit-to-Work for the field worker. A worker standing at an asset describes
// the job (by voice or text) and gets a drafted permit - LOTO isolation points,
// hazards, PPE, procedures, governing clauses - drawn from the plant graph.
//
// The one thing this screen must never blur: a worker REQUESTS a permit here,
// they do not authorize one. The draft is a proposal; a permit authority
// (supervisor/engineer) reviews and signs before any work begins. That boundary
// is stated in a banner the worker cannot miss, and there is deliberately no
// "approve" control on this page - approval is a human act made elsewhere.

import { useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, FileSignature, ShieldAlert, Key, HardHat, ClipboardCheck,
  Loader2, Check, AlertTriangle, ChevronDown,
} from "lucide-react";
import { fieldAssets, draftPermitStream } from "../../lib/api";
import { useAuth } from "../../auth/AuthProvider";
import { useFieldLang } from "../../components/field/FieldShell";
import { t, speechLang } from "../../lib/i18n";
import { createRecognizer, recognitionSupported, stopSpeaking } from "../../lib/voice";

const STEP_LABEL = {
  get_connected_equipment: "Process connections (LOTO)",
  get_failure_history: "Operating hazard history",
  get_governing_clauses: "Governing safety clauses",
  get_fix_procedures: "Maintenance procedures",
  get_work_orders: "Historical work orders",
  get_documents_mentioning: "Reference documentation",
};

export default function FieldPermit() {
  const { lang } = useFieldLang();
  const { user } = useAuth();
  const [assets, setAssets] = useState([]);
  const [tag, setTag] = useState("");
  const [work, setWork] = useState("");
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState([]);
  const [body, setBody] = useState("");
  const [permit, setPermit] = useState(null);
  const [error, setError] = useState(null);
  const [listening, setListening] = useState(false);
  const recRef = useRef(null);
  const canListen = recognitionSupported();

  useEffect(() => { fieldAssets().then(setAssets).catch(() => setAssets([])); }, []);
  useEffect(() => () => { stopSpeaking(); recRef.current?.abort(); }, []);

  function toggleMic() {
    if (listening) { recRef.current?.stop(); return; }
    if (!canListen) return;
    const rec = createRecognizer(speechLang(lang), {
      onResult: (text) => setWork(text),
      onEnd: () => setListening(false),
      onError: () => setListening(false),
    });
    recRef.current = rec; rec?.start(); setListening(true);
  }

  async function submit(e) {
    e?.preventDefault();
    if (!tag.trim() || !work.trim() || busy) return;
    setBusy(true); setError(null); setPermit(null); setSteps([]); setBody("");
    try {
      const data = await draftPermitStream(
        { tag: tag.toUpperCase().trim(), workDescription: work,
          requestedBy: user?.email || "field worker" },
        { onStep: (tool) => setSteps((s) => (s.includes(tool) ? s : [...s, tool])),
          onToken: (tok) => setBody((b) => b + tok) });
      if (!data) { setError(t("permit_failed", lang)); return; }
      setPermit(data);
    } catch {
      setError(t("permit_failed", lang));
    } finally { setBusy(false); }
  }

  const units = [...new Set(assets.map((a) => a.unit))].sort();

  return (
    <div className="flex h-full flex-col overflow-y-auto">
      {/* Request form */}
      <form onSubmit={submit} className="flex-shrink-0 space-y-3 px-4 pt-4"
        style={{ borderBottom: "1px solid var(--border)", paddingBottom: "1rem" }}>
        <div className="relative">
          <select value={tag} onChange={(e) => setTag(e.target.value)} disabled={busy}
            className="w-full appearance-none rounded-xl px-4 py-3 pr-10 text-sm font-medium outline-none"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border-md)", color: "var(--text)" }}>
            <option value="">{t("permit_pick_asset", lang)}</option>
            {units.map((u) => (
              <optgroup key={u} label={u}>
                {assets.filter((a) => a.unit === u).map((a) => (
                  <option key={a.tag} value={a.tag}>{a.tag}</option>
                ))}
              </optgroup>
            ))}
          </select>
          <ChevronDown size={16} className="pointer-events-none absolute right-3 top-3.5" style={{ color: "var(--muted)" }} />
        </div>

        <div className="flex items-end gap-2">
          {canListen && (
            <button type="button" onClick={toggleMic} aria-label={t("tap_to_talk", lang)}
              className="grid h-11 w-11 flex-shrink-0 place-items-center rounded-full"
              style={{ background: listening ? "#ef4444" : "var(--brand-light)", color: listening ? "#fff" : "var(--blue)", border: listening ? "none" : "1px solid var(--brand-mid)" }}>
              {listening ? <MicOff size={18} /> : <Mic size={18} />}
            </button>
          )}
          <textarea value={work} onChange={(e) => setWork(e.target.value)} disabled={busy} rows={2}
            placeholder={listening ? t("listening", lang) : t("permit_describe", lang)}
            className="max-h-28 flex-1 resize-none rounded-xl px-3 py-2.5 text-sm outline-none"
            style={{ border: "1px solid var(--border-md)", background: "var(--bg-surface)", color: "var(--text)" }} />
        </div>

        <button type="submit" disabled={busy || !tag.trim() || !work.trim()}
          className="flex w-full items-center justify-center gap-2 rounded-xl py-3 text-sm font-semibold text-white"
          style={{ background: "var(--blue)", opacity: busy || !tag.trim() || !work.trim() ? 0.5 : 1 }}>
          {busy ? <><Loader2 size={16} className="animate-spin" /> {t("permit_drafting", lang)}</>
                : <><FileSignature size={16} /> {t("permit_request", lang)}</>}
        </button>
      </form>

      <div className="min-h-0 flex-1 px-4 py-4">
        {busy && <Streaming steps={steps} body={body} lang={lang} />}
        {error && !busy && (
          <div className="rounded-xl px-4 py-3 text-sm" style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
            {error}
          </div>
        )}
        {permit && !busy && <FieldPermitCard permit={permit} lang={lang} />}
        {!permit && !busy && !error && (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl"
              style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
              <FileSignature size={24} style={{ color: "var(--blue)" }} />
            </div>
            <p className="text-sm" style={{ color: "var(--muted)" }}>{t("permit_empty", lang)}</p>
          </div>
        )}
      </div>
    </div>
  );
}

function Streaming({ steps, body, lang }) {
  return (
    <div className="space-y-3">
      <div className="rounded-xl p-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--muted)" }}>
          {t("permit_gathering", lang)}
        </p>
        {steps.length === 0 ? (
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--muted)" }}>
            <Loader2 size={13} className="animate-spin" style={{ color: "var(--blue)" }} /> …
          </div>
        ) : steps.map((tool) => (
          <div key={tool} className="flex items-center gap-2 text-xs" style={{ color: "var(--text-md)" }}>
            <Check size={13} style={{ color: "#16a34a" }} /> {STEP_LABEL[tool] || tool}
          </div>
        ))}
      </div>
      {body && (
        <div className="rounded-xl p-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
          <p className="whitespace-pre-wrap text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>{body}</p>
        </div>
      )}
    </div>
  );
}

function FieldPermitCard({ permit, lang }) {
  return (
    <div className="space-y-4">
      {/* The boundary a worker must never miss: this is a REQUEST, not sign-off. */}
      <div className="flex items-start gap-2 rounded-xl px-4 py-3"
        style={{ background: "#fef3c7", border: "1px solid #fcd34d", color: "#92400e" }}>
        <AlertTriangle size={16} className="mt-0.5 flex-shrink-0" />
        <p className="text-xs font-medium leading-relaxed">{t("permit_pending_auth", lang)}</p>
      </div>

      <div className="rounded-xl p-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-bold" style={{ color: "var(--text)" }}>{permit.request?.tag}</h3>
            <p className="mt-0.5 text-xs" style={{ color: "var(--muted)" }}>{permit.request?.work_description}</p>
          </div>
          <span className="rounded-full px-2.5 py-1 text-[11px] font-semibold"
            style={{ background: "#fee2e2", color: "#991b1b", border: "1px solid #fca5a5" }}>
            {permit.permit_type}
          </span>
        </div>
      </div>

      <Section icon={Key} color="var(--blue)" title={t("permit_isolations", lang)}
        items={permit.isolation_points} empty={t("permit_none_isolation", lang)} mono />
      <Section icon={ShieldAlert} color="#dc2626" title={t("permit_hazards", lang)}
        items={permit.identified_hazards} empty={t("permit_none_hazard", lang)} />
      <Section icon={HardHat} color="#eab308" title={t("permit_ppe", lang)}
        items={permit.required_ppe} empty="—" />
      <Section icon={ClipboardCheck} color="var(--blue)" title={t("permit_procedures", lang)}
        items={permit.procedures_to_follow} empty={t("permit_none_proc", lang)} />
      <Section icon={ClipboardCheck} color="var(--brand-mid)" title={t("permit_standards", lang)}
        items={permit.governing_clauses} empty="—" />
    </div>
  );
}

function Section({ icon: Icon, color, title, items, empty, mono }) {
  const list = items || [];
  return (
    <div className="rounded-xl p-4" style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      <h4 className="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider" style={{ color: "var(--text)" }}>
        <Icon size={14} style={{ color }} /> {title}
      </h4>
      {list.length === 0 ? (
        <p className="text-xs italic" style={{ color: "var(--muted)" }}>{empty}</p>
      ) : mono ? (
        <div className="flex flex-wrap gap-2">
          {list.map((pt) => (
            <span key={pt} className="rounded-lg px-2.5 py-1 font-mono text-xs"
              style={{ background: "var(--bg-surface)", border: "1px solid var(--border)", color: "var(--text)" }}>{pt}</span>
          ))}
        </div>
      ) : (
        <ul className="space-y-1.5">
          {list.map((x, i) => (
            <li key={i} className="flex items-start gap-2 text-xs" style={{ color: "var(--text-md)" }}>
              <span style={{ color }}>•</span> {x}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

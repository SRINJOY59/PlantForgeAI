// The Field Copilot: one screen, built for a worker at the equipment.
//
//   1. Scope to an asset (or leave it plant-wide).
//   2. See that asset's live state — current reading (off the telemetry
//      WebSocket), standing alarms and the last diagnosis (off the backend).
//   3. Ask by voice or text, in the language chosen in the shell.
//   4. Hear the answer spoken back.
//
// Answers stream through the same grounded pipeline the engineer console uses,
// scoped and translated server-side. Voice is browser-native (see lib/voice).

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Mic, MicOff, Send, Volume2, Square, ChevronDown, Radio, AlertTriangle, Stethoscope,
} from "lucide-react";
import { fieldAssets, fieldAssetContext, fieldAskStream, subscribeSimTelemetry } from "../../lib/api";
import { useFieldLang } from "../../components/field/FieldShell";
import { t, speechLang } from "../../lib/i18n";
import {
  speak, stopSpeaking, createRecognizer, recognitionSupported, speechSupported,
} from "../../lib/voice";
import { cleanForField } from "./fieldText";

const HISTORY_TURNS = 4;
function toHistory(turns) {
  return turns
    .filter((t) => t.answer && !t.error)
    .slice(-HISTORY_TURNS)
    .map((t) => ({ question: t.question, answer: t.text }));
}

export default function FieldCopilot() {
  const { lang } = useFieldLang();
  const [assets, setAssets] = useState([]);
  const [tag, setTag] = useState(null);          // null = plant-wide
  const [ctx, setCtx] = useState(null);          // asset live state (alarms/diag)
  const [live, setLive] = useState(null);        // latest numeric reading
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [autoSpeak, setAutoSpeak] = useState(true);
  const [speakingIdx, setSpeakingIdx] = useState(null);
  const scroller = useRef(null);
  const recRef = useRef(null);

  const canListen = recognitionSupported();
  const canSpeak = speechSupported();

  // --- asset universe ------------------------------------------------------
  useEffect(() => {
    fieldAssets().then(setAssets).catch(() => setAssets([]));
  }, []);

  // --- asset live state (alarms + last diagnosis) --------------------------
  useEffect(() => {
    setCtx(null); setLive(null);
    if (!tag) return;
    let live = true;
    fieldAssetContext(tag).then((c) => { if (live) setCtx(c); }).catch(() => {});
    return () => { live = false; };
  }, [tag]);

  // --- live reading off the telemetry WebSocket ----------------------------
  useEffect(() => {
    if (!tag) return;
    const unit = tag.includes(".") ? tag.split(".")[0] : tag;
    const unsub = subscribeSimTelemetry((msg) => {
      if (msg?.type === "telemetry" && msg.tag_id === tag) {
        const y = parseFloat(msg.value);
        if (!Number.isNaN(y)) setLive({ value: y, ts: msg.timestamp });
      }
    }, unit);
    return unsub;
  }, [tag]);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [turns]);

  // clean up voice on unmount
  useEffect(() => () => { stopSpeaking(); recRef.current?.abort(); }, []);

  // --- asking --------------------------------------------------------------
  const send = useCallback(async (question) => {
    if (!question.trim() || busy) return;
    stopSpeaking(); setSpeakingIdx(null);
    setInput(""); setBusy(true);
    const history = toHistory(turns);
    const idx = turns.length;
    setTurns((ts) => [...ts, { question, text: "", answer: null }]);

    try {
      let streamed = "";
      const done = await fieldAskStream(question, (delta) => {
        streamed += delta;
        setTurns((ts) => {
          const c = [...ts];
          c[idx] = { ...c[idx], text: c[idx].text + delta };
          return c;
        });
      }, { asset: tag, lang, history });

      setTurns((ts) => { const c = [...ts]; c[idx] = { ...c[idx], answer: done ?? {} }; return c; });

      if (autoSpeak && canSpeak && streamed) {
        setSpeakingIdx(idx);
        speak(cleanForField(streamed), speechLang(lang), { onEnd: () => setSpeakingIdx(null) });
      }
    } catch {
      setTurns((ts) => {
        const c = [...ts];
        c[idx] = { ...c[idx], text: t("offline", lang), error: true };
        return c;
      });
    } finally {
      setBusy(false);
    }
  }, [busy, turns, tag, lang, autoSpeak, canSpeak]);

  // --- voice input ---------------------------------------------------------
  function toggleMic() {
    if (listening) { recRef.current?.stop(); return; }
    if (!canListen) return;
    stopSpeaking();
    const rec = createRecognizer(speechLang(lang), {
      onResult: (text, isFinal) => {
        setInput(text);
        if (isFinal) { setListening(false); send(text); }
      },
      onEnd: () => setListening(false),
      onError: () => setListening(false),
    });
    recRef.current = rec;
    rec?.start();
    setListening(true);
  }

  function speakTurn(i, text) {
    if (speakingIdx === i) { stopSpeaking(); setSpeakingIdx(null); return; }
    setSpeakingIdx(i);
    speak(cleanForField(text), speechLang(lang), { onEnd: () => setSpeakingIdx(null) });
  }

  const grouped = groupByUnit(assets);

  return (
    <div className="flex h-full flex-col">
      {/* Asset scope + live state */}
      <div className="flex-shrink-0 px-4 pt-3" style={{ borderBottom: "1px solid var(--border)" }}>
        <AssetPicker grouped={grouped} tag={tag} onPick={setTag} lang={lang} />
        {tag && <LiveState ctx={ctx} live={live} lang={lang} />}
      </div>

      {/* Conversation */}
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <EmptyState tag={tag} lang={lang} />
        ) : (
          <div className="space-y-4">
            {turns.map((turn, i) => (
              <TurnCard
                key={i} turn={turn} lang={lang}
                speaking={speakingIdx === i}
                canSpeak={canSpeak}
                onSpeak={() => speakTurn(i, turn.text)}
              />
            ))}
            {busy && <Thinking lang={lang} />}
          </div>
        )}
      </div>

      {/* Composer */}
      <Composer
        input={input} setInput={setInput}
        onSend={() => send(input)}
        busy={busy} listening={listening} canListen={canListen}
        onMic={toggleMic}
        autoSpeak={autoSpeak} setAutoSpeak={setAutoSpeak} canSpeak={canSpeak}
        placeholder={tag ? t("ask_placeholder", lang) : t("ask_generic", lang)}
        lang={lang}
      />
    </div>
  );
}

function groupByUnit(assets) {
  const g = {};
  for (const a of assets) (g[a.unit] ||= []).push(a);
  return g;
}

function AssetPicker({ grouped, tag, onPick, lang }) {
  const units = Object.keys(grouped).sort();
  return (
    <div className="relative pb-2">
      <select
        value={tag ?? ""}
        onChange={(e) => onPick(e.target.value || null)}
        className="w-full appearance-none rounded-xl px-4 py-3 pr-10 text-sm font-medium outline-none"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border-md)", color: "var(--text)" }}
      >
        <option value="">{t("all_assets", lang)}</option>
        {units.map((u) => (
          <optgroup key={u} label={u}>
            {grouped[u].map((a) => (
              <option key={a.tag} value={a.tag}>{a.tag}</option>
            ))}
          </optgroup>
        ))}
      </select>
      <ChevronDown size={16} className="pointer-events-none absolute right-3 top-3.5" style={{ color: "var(--muted)" }} />
    </div>
  );
}

function LiveState({ ctx, live, lang }) {
  const alarms = ctx?.active_alarms || [];
  const candidates = ctx?.diagnosis?.candidates || [];
  return (
    <div className="flex flex-wrap items-center gap-2 pb-3 text-xs">
      <span className="inline-flex items-center gap-1.5 rounded-full px-2.5 py-1"
        style={{ background: "var(--brand-light)", color: "var(--blue)" }}>
        <Radio size={12} /> {t("live", lang)}: {live ? live.value.toFixed(2) : "—"}
      </span>
      {alarms.length === 0 ? (
        <span className="rounded-full px-2.5 py-1" style={{ background: "#dcfce7", color: "#166534" }}>
          {t("no_alarms", lang)}
        </span>
      ) : (
        alarms.map((a, i) => (
          <span key={i} className="inline-flex items-center gap-1 rounded-full px-2.5 py-1"
            style={{ background: "#fee2e2", color: "#991b1b" }}>
            <AlertTriangle size={12} /> {a.level} · {a.value}
          </span>
        ))
      )}
      {candidates.length > 0 && (
        <span className="inline-flex items-center gap-1 rounded-full px-2.5 py-1"
          style={{ background: "#fef3c7", color: "#92400e" }}>
          <Stethoscope size={12} /> {candidates[0].label}
        </span>
      )}
    </div>
  );
}

function EmptyState({ tag, lang }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl"
        style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
        <Mic size={24} style={{ color: "var(--blue)" }} />
      </div>
      <p className="text-sm" style={{ color: "var(--muted)" }}>
        {tag ? `${t("scoped_to", lang)}: ${tag}` : t("ask_generic", lang)}
      </p>
    </div>
  );
}

function TurnCard({ turn, lang, speaking, canSpeak, onSpeak }) {
  return (
    <div className="rounded-2xl overflow-hidden"
      style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
      <div className="px-4 py-3" style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border)" }}>
        <p className="text-sm font-medium" style={{ color: "var(--text)" }}>{turn.question}</p>
      </div>
      <div className="px-4 py-3">
        <p className="whitespace-pre-wrap text-sm leading-relaxed"
          style={{ color: turn.error ? "#991b1b" : "var(--text-md)" }}>
          {turn.text ? cleanForField(turn.text) : <span style={{ color: "var(--muted)" }}>{t("thinking", lang)}</span>}
        </p>
        {canSpeak && turn.text && !turn.error && (
          <button onClick={onSpeak}
            className="btn-ghost mt-2 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs">
            {speaking ? <><Square size={12} /> {t("stop", lang)}</> : <><Volume2 size={13} /> {t("speak", lang)}</>}
          </button>
        )}
      </div>
    </div>
  );
}

function Thinking({ lang }) {
  return (
    <div className="flex items-center gap-2 px-1 py-2">
      {[0, 1, 2].map((i) => (
        <span key={i} className="h-2 w-2 rounded-full"
          style={{ background: "var(--blue)", opacity: 0.4, animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite` }} />
      ))}
      <span className="text-xs" style={{ color: "var(--muted)" }}>{t("thinking", lang)}</span>
    </div>
  );
}

function Composer({ input, setInput, onSend, busy, listening, canListen, onMic,
                    autoSpeak, setAutoSpeak, canSpeak, placeholder, lang }) {
  return (
    <div className="flex-shrink-0 px-3 py-3"
      style={{ background: "var(--bg-panel)", borderTop: "1px solid var(--border)" }}>
      {canSpeak && (
        <label className="mb-2 flex items-center gap-2 px-1 text-xs" style={{ color: "var(--muted)" }}>
          <input type="checkbox" checked={autoSpeak} onChange={(e) => setAutoSpeak(e.target.checked)} />
          <Volume2 size={12} /> {t("speak", lang)}
        </label>
      )}
      <div className="flex items-end gap-2">
        {/* Mic — the big field-friendly target */}
        {canListen && (
          <button onClick={onMic} aria-label={t("tap_to_talk", lang)}
            className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-full transition-colors"
            style={{
              background: listening ? "#ef4444" : "var(--brand-light)",
              color: listening ? "#fff" : "var(--blue)",
              border: listening ? "none" : "1px solid var(--brand-mid)",
            }}>
            {listening ? <MicOff size={20} /> : <Mic size={20} />}
          </button>
        )}
        <div className="flex flex-1 items-end rounded-2xl overflow-hidden"
          style={{ border: "1px solid var(--border-md)", background: "var(--bg-surface)" }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            rows={1}
            placeholder={listening ? t("listening", lang) : placeholder}
            className="max-h-32 w-full resize-none bg-transparent px-3 py-3 text-sm outline-none"
            style={{ color: "var(--text)" }}
          />
        </div>
        <button onClick={onSend} disabled={busy || !input.trim()}
          aria-label={t("send", lang)}
          className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-full"
          style={{ background: "var(--blue)", color: "#fff", opacity: busy || !input.trim() ? 0.5 : 1 }}>
          {busy
            ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            : <Send size={18} />}
        </button>
      </div>
    </div>
  );
}

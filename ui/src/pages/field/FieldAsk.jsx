// The worker's general "ask the plant anything" tab - the same grounded Q&A the
// engineers get, but pitched for a field worker (persona="worker", set by the
// backend) and voice-first. Deliberately leaner than the Copilot: no asset
// picker, no live-state chips - just ask, by voice or text, and hear the answer.
//
// Shares the field conventions with FieldCopilot: answers are cleaned of
// citation markers before they are shown or spoken (see cleanForField).

import { useCallback, useEffect, useRef, useState } from "react";
import { Mic, MicOff, Send, Volume2, Square } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { fieldAskStream } from "../../lib/api";
import { useFieldLang } from "../../components/field/FieldShell";
import { t, speechLang } from "../../lib/i18n";
import {
  speak, stopSpeaking, createRecognizer, recognitionSupported, speechSupported,
} from "../../lib/voice";
import { cleanForField } from "./fieldText";

const HISTORY_TURNS = 4;
const toHistory = (turns) => turns
  .filter((x) => x.answer && !x.error)
  .slice(-HISTORY_TURNS)
  .map((x) => ({ question: x.question, answer: x.text }));

export default function FieldAsk() {
  const { lang } = useFieldLang();
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

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [turns]);
  useEffect(() => () => { stopSpeaking(); recRef.current?.abort(); }, []);

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
        setTurns((ts) => { const c = [...ts]; c[idx] = { ...c[idx], text: c[idx].text + delta }; return c; });
      }, { asset: null, lang, history });
      setTurns((ts) => { const c = [...ts]; c[idx] = { ...c[idx], answer: done ?? {} }; return c; });
      if (autoSpeak && canSpeak && streamed) {
        setSpeakingIdx(idx);
        speak(cleanForField(streamed), speechLang(lang), { onEnd: () => setSpeakingIdx(null) });
      }
    } catch {
      setTurns((ts) => { const c = [...ts]; c[idx] = { ...c[idx], text: t("offline", lang), error: true }; return c; });
    } finally { setBusy(false); }
  }, [busy, turns, lang, autoSpeak, canSpeak]);

  function toggleMic() {
    if (listening) { recRef.current?.stop(); return; }
    if (!canListen) return;
    stopSpeaking();
    const rec = createRecognizer(speechLang(lang), {
      onResult: (text, isFinal) => { setInput(text); if (isFinal) { setListening(false); send(text); } },
      onEnd: () => setListening(false),
      onError: () => setListening(false),
    });
    recRef.current = rec; rec?.start(); setListening(true);
  }

  function speakTurn(i, text) {
    if (speakingIdx === i) { stopSpeaking(); setSpeakingIdx(null); return; }
    setSpeakingIdx(i);
    speak(cleanForField(text), speechLang(lang), { onEnd: () => setSpeakingIdx(null) });
  }

  return (
    <div className="flex h-full flex-col">
      <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto px-4 py-4">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center px-6 text-center">
            <div className="mb-4 grid h-14 w-14 place-items-center rounded-2xl"
              style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}>
              <Mic size={24} style={{ color: "var(--blue)" }} />
            </div>
            <p className="text-sm" style={{ color: "var(--muted)" }}>{t("ask_generic", lang)}</p>
          </div>
        ) : (
          <div className="space-y-4">
            {turns.map((turn, i) => (
              <div key={i} className="rounded-2xl overflow-hidden"
                style={{ background: "var(--bg-panel)", border: "1px solid var(--border)" }}>
                <div className="px-4 py-3" style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border)" }}>
                  <p className="text-sm font-medium" style={{ color: "var(--text)" }}>{turn.question}</p>
                </div>
                <div className="px-4 py-3">
                  {turn.text ? (
                    <div className="prose prose-sm max-w-none text-sm leading-relaxed dark:prose-invert prose-p:my-1.5 prose-strong:text-[var(--text)] prose-strong:font-bold prose-headings:font-bold prose-headings:my-2 prose-ol:my-1.5 prose-ol:pl-5 prose-ul:my-1.5 prose-ul:pl-5 prose-li:my-1"
                      style={{ color: turn.error ? "#991b1b" : "var(--text-md)" }}>
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>{cleanForField(turn.text)}</ReactMarkdown>
                    </div>
                  ) : (
                    <span style={{ color: "var(--muted)" }}>{t("thinking", lang)}</span>
                  )}
                  {canSpeak && turn.text && !turn.error && (
                    <button onClick={() => speakTurn(i, turn.text)}
                      className="btn-ghost mt-2 inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs">
                      {speakingIdx === i ? <><Square size={12} /> {t("stop", lang)}</> : <><Volume2 size={13} /> {t("speak", lang)}</>}
                    </button>
                  )}
                </div>
              </div>
            ))}
            {busy && <p className="px-1 py-2 text-xs" style={{ color: "var(--muted)" }}>{t("thinking", lang)}</p>}
          </div>
        )}
      </div>

      <div className="flex-shrink-0 px-3 py-3" style={{ background: "var(--bg-panel)", borderTop: "1px solid var(--border)" }}>
        <div className="flex items-end gap-2">
          {canListen && (
            <button onClick={toggleMic} aria-label={t("tap_to_talk", lang)}
              className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-full"
              style={{ background: listening ? "#ef4444" : "var(--brand-light)", color: listening ? "#fff" : "var(--blue)", border: listening ? "none" : "1px solid var(--brand-mid)" }}>
              {listening ? <MicOff size={20} /> : <Mic size={20} />}
            </button>
          )}
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(input); } }}
            rows={1}
            placeholder={listening ? t("listening", lang) : t("ask_generic", lang)}
            className="max-h-32 flex-1 resize-none rounded-2xl px-3 py-3 text-sm outline-none"
            style={{ border: "1px solid var(--border-md)", background: "var(--bg-surface)", color: "var(--text)" }}
          />
          <button onClick={() => send(input)} disabled={busy || !input.trim()} aria-label={t("send", lang)}
            className="grid h-12 w-12 flex-shrink-0 place-items-center rounded-full"
            style={{ background: "var(--blue)", color: "#fff", opacity: busy || !input.trim() ? 0.5 : 1 }}>
            {busy ? <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/40 border-t-white" /> : <Send size={18} />}
          </button>
        </div>
      </div>
    </div>
  );
}

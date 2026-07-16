import { useRef, useState } from "react";
import { ArrowUp, ShieldAlert, ShieldCheck, Sparkles } from "lucide-react";
import { askStream } from "../../lib/api";
import AnswerText from "../../components/ask/answerText";
import EvidencePanel from "../../components/ask/EvidencePanel";
import { ConfidencePill, ModeBadge } from "../../components/ask/badges";

const SUGGESTIONS = [
  "How many seal failures has P-101A had and what is the root cause?",
  "Explain how a trip of K-301 can cause PSV-204 to lift.",
  "Which statutory inspections are overdue?",
  "What is the process flow through Unit 200 from K-301?",
];

export default function Ask() {
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [focused, setFocused] = useState(null); // turn index for evidence
  const [activeDoc, setActiveDoc] = useState(null);
  const scroller = useRef(null);

  async function send(question) {
    if (!question.trim() || busy) return;
    setInput("");
    setBusy(true);
    const idx = turns.length;
    setTurns((t) => [...t, { question, text: "", answer: null }]);
    setFocused(idx);
    setActiveDoc(null);

    try {
      const done = await askStream(question, (delta) => {
        setTurns((t) => {
          const copy = [...t];
          copy[idx] = { ...copy[idx], text: copy[idx].text + delta };
          return copy;
        });
        scroller.current?.scrollTo(0, scroller.current.scrollHeight);
      });
      setTurns((t) => {
        const copy = [...t];
        copy[idx] = { ...copy[idx], answer: done };
        return copy;
      });
    } catch {
      setTurns((t) => {
        const copy = [...t];
        copy[idx] = { ...copy[idx], text: "Couldn't reach the brain. Is the gateway running?" };
        return copy;
      });
    } finally {
      setBusy(false);
    }
  }

  const focusedTurn = focused != null ? turns[focused] : null;

  return (
    <div className="flex h-full">
      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          {turns.length === 0 ? (
            <Welcome onPick={send} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-6 px-6 py-6">
              {turns.map((turn, i) => (
                <Turn
                  key={i}
                  turn={turn}
                  active={i === focused}
                  onFocus={() => { setFocused(i); setActiveDoc(null); }}
                  onCite={(doc) => { setFocused(i); setActiveDoc(doc); }}
                />
              ))}
            </div>
          )}
        </div>

        <Composer input={input} setInput={setInput} onSend={() => send(input)} busy={busy} />
      </div>

      <EvidencePanel
        answer={focusedTurn?.answer}
        activeDoc={activeDoc}
        onClose={() => setActiveDoc(null)}
      />
    </div>
  );
}

function Turn({ turn, active, onFocus, onCite }) {
  const a = turn.answer;
  return (
    <div onClick={onFocus} className={`rounded-xl p-4 transition-colors ${active ? "surface" : "cursor-pointer hover:bg-gray-50 dark:hover:bg-slate-900/50"}`}>
      <div className="mb-2 font-medium">{turn.question}</div>
      {a && (
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <ModeBadge mode={a.mode} />
          <ConfidencePill confidence={a.confidence} />
          <Verified answer={a} />
        </div>
      )}
      <div className="text-[15px] text-gray-800 dark:text-slate-200">
        {turn.text ? (
          <AnswerText text={turn.text} onCite={onCite} />
        ) : (
          <span className="inline-flex items-center gap-2 muted text-sm">
            <Sparkles size={14} className="animate-pulse" /> thinking…
          </span>
        )}
      </div>
    </div>
  );
}

function Verified({ answer }) {
  const bad = answer.verified === false;
  return (
    <span className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ${bad ? "bg-red-50 text-red-700 dark:bg-red-950/50 dark:text-red-300" : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300"}`}>
      {bad ? <ShieldAlert size={11} /> : <ShieldCheck size={11} />}
      {bad ? "unverified" : "grounded"}
    </span>
  );
}

function Welcome({ onPick }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center px-6 text-center">
      <div className="grid h-12 w-12 place-items-center rounded-xl bg-steel-600 text-white">
        <Sparkles size={22} />
      </div>
      <h1 className="mt-4 text-2xl font-semibold">Ask the plant anything</h1>
      <p className="mt-1.5 muted">Every answer is cited and shows its reasoning.</p>
      <div className="mt-6 grid w-full gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => onPick(s)} className="surface rounded-lg p-3 text-left text-sm hover:border-steel-300">
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({ input, setInput, onSend, busy }) {
  return (
    <div className="border-t border-gray-200 bg-white px-4 py-3 dark:border-slate-800 dark:bg-slate-900">
      <form
        onSubmit={(e) => { e.preventDefault(); onSend(); }}
        className="mx-auto flex max-w-3xl items-end gap-2"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); }
          }}
          rows={1}
          placeholder="Ask about equipment, failures, procedures, compliance…"
          className="input max-h-40 resize-none py-2.5"
        />
        <button type="submit" className="btn-primary h-10 px-3" disabled={busy}>
          <ArrowUp size={18} />
        </button>
      </form>
    </div>
  );
}

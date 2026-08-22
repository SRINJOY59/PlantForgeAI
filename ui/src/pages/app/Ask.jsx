import { useRef, useState, useEffect, useCallback } from "react";
import { ArrowUp, BookOpen, ShieldAlert, ShieldCheck, Sparkles, RotateCcw, Copy, CheckCheck } from "lucide-react";
import { askStream, toHistory } from "../../lib/api";
import AnswerText from "../../components/ask/answerText";
import CorrectPanel from "../../components/ask/CorrectPanel";
import CorrectionNotice from "../../components/ask/CorrectionNotice";
import EvidencePanel from "../../components/ask/EvidencePanel";
import HistoryPanel from "../../components/ask/HistoryPanel";
import { ConfidencePill, ModeBadge } from "../../components/ask/badges";
import { useAuth } from "../../auth/AuthProvider";
import { useProfile } from "../../state/ProfileContext";
import {
  createConversation, deleteConversation, listConversations, loadTurns,
  saveTurn, titleFor,
} from "../../lib/history";

const SUGGESTIONS = [
  { icon: "🔧", text: "How many seal failures has P-101A had and what is the root cause?" },
  { icon: "⚡", text: "Explain how a trip of K-301 can cause PSV-204 to lift." },
  { icon: "📋", text: "Which statutory inspections are overdue?" },
  { icon: "🔄", text: "What is the process flow through Unit 200 from K-301?" },
];

export default function Ask() {
  const { user } = useAuth();
  const { profile } = useProfile();
  const [turns, setTurns] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [focused, setFocused] = useState(null);
  const [activeDoc, setActiveDoc] = useState(null);
  const [conversations, setConversations] = useState([]);
  const [activeId, setActiveId] = useState(null);
  const [loadingHistory, setLoadingHistory] = useState(true);
  const scroller = useRef(null);
  // a ref, not state: the first question of a thread creates the conversation
  // and then saves against it in the same call, before any re-render
  const conversationId = useRef(null);

  const refreshHistory = useCallback(() => {
    listConversations()
      .then(setConversations)
      .catch(() => {})           // history is a convenience; never break asking
      .finally(() => setLoadingHistory(false));
  }, []);

  useEffect(refreshHistory, [refreshHistory]);

  useEffect(() => {
    if (scroller.current) scroller.current.scrollTop = scroller.current.scrollHeight;
  }, [turns]);

  function startNew() {
    conversationId.current = null;
    setActiveId(null);
    setTurns([]);
    setFocused(null);
    setActiveDoc(null);
  }

  async function openConversation(id) {
    conversationId.current = id;
    setActiveId(id);
    setActiveDoc(null);
    try {
      const past = await loadTurns(id);
      setTurns(past);
      setFocused(past.length ? past.length - 1 : null);
    } catch {
      setTurns([]);
      setFocused(null);
    }
  }

  async function removeConversation(id) {
    await deleteConversation(id).catch(() => {});
    if (id === conversationId.current) startNew();
    refreshHistory();
  }

  async function send(question) {
    if (!question.trim() || busy) return;
    setInput(""); setBusy(true);
    // snapshot before the optimistic turn goes in, or the question would
    // arrive as its own context
    const history = toHistory(turns);
    const idx = turns.length;
    setTurns(t => [...t, { question, text: "", answer: null }]);
    setFocused(idx); setActiveDoc(null);

    // a thread is created by its first question, so that question is its title
    if (!conversationId.current) {
      const created = await createConversation(user?.id, titleFor(question))
        .catch(() => null);
      if (created) {
        conversationId.current = created.id;
        setActiveId(created.id);
      }
    }

    try {
      let streamed = "";
      const persona = profile?.job_title || profile?.app_role;
      const done = await askStream(question, delta => {
        streamed += delta;
        setTurns(t => { const c = [...t]; c[idx] = { ...c[idx], text: c[idx].text + delta }; return c; });
      }, history, null, null, persona);
      setTurns(t => { const c = [...t]; c[idx] = { ...c[idx], answer: done }; return c; });
      // only once the answer is whole - a half-streamed turn is never written
      saveTurn(conversationId.current, question, streamed, done)
        .then(refreshHistory)
        .catch(() => {});
    } catch {
      setTurns(t => { const c = [...t]; c[idx] = { ...c[idx], text: "⚠️ Couldn't reach the gateway. Is the backend running on port 8000?", error: true }; return c; });
    } finally { setBusy(false); }
  }

  const focusedTurn = focused != null ? turns[focused] : null;

  return (
    <div className="flex h-full" style={{ background: "var(--bg-surface)" }}>
      <HistoryPanel conversations={conversations} activeId={activeId}
        onSelect={openConversation} onNew={startNew} onDelete={removeConversation}
        loading={loadingHistory} />
      <div className="flex min-w-0 flex-1 flex-col">
        <div ref={scroller} className="min-h-0 flex-1 overflow-y-auto">
          {turns.length === 0
            ? <Welcome onPick={send} />
            : (
              <div className="mx-auto max-w-3xl space-y-4 px-4 py-5 sm:px-6 sm:py-6">
                {turns.map((turn, i) => (
                  <Turn key={i} turn={turn} active={i === focused}
                    onFocus={() => { setFocused(i); setActiveDoc(null); }}
                    onCite={doc => { setFocused(i); setActiveDoc(doc); }} />
                ))}
                {busy && (
                  <div className="flex items-center gap-2 px-1 py-2">
                    {[0,1,2].map(i => (
                      <span key={i} className="h-2 w-2 rounded-full" style={{
                        background: "var(--blue)", opacity: 0.4,
                        animation: `pulse 1.2s ease-in-out ${i * 0.2}s infinite`,
                      }} />
                    ))}
                    <span className="text-xs" style={{ color: "var(--muted)" }}>Thinking…</span>
                  </div>
                )}
              </div>
            )
          }
        </div>
        <Composer input={input} setInput={setInput} onSend={() => send(input)} busy={busy}
          onClear={startNew} hasTurns={turns.length > 0} />
      </div>
      <EvidencePanel answer={focusedTurn?.answer} activeDoc={activeDoc}
        onSelect={doc => setActiveDoc(doc)} onClose={() => setActiveDoc(null)} />
    </div>
  );
}

function Turn({ turn, active, onFocus, onCite }) {
  const a = turn.answer;
  const [copied, setCopied] = useState(false);
  function copyText() { navigator.clipboard.writeText(turn.text); setCopied(true); setTimeout(() => setCopied(false), 2000); }

  return (
    <div
      className="animate-slide-up rounded-2xl overflow-hidden transition-all duration-200"
      onClick={onFocus}
      style={{
        background: "var(--bg-panel)",
        border: active ? "1px solid var(--brand-mid)" : "1px solid var(--border)",
        boxShadow: active ? "0 0 0 3px rgba(122,84,160,0.06), 0 2px 8px rgba(0,0,0,0.04)" : "0 1px 3px rgba(0,0,0,0.04)",
        cursor: active ? "default" : "pointer",
      }}
    >
      {/* Question */}
      <div className="px-5 py-4" style={{ background: "var(--bg-surface)", borderBottom: "1px solid var(--border)" }}>
        <div className="flex items-start gap-3">
          <div
            className="mt-0.5 grid h-6 w-6 flex-shrink-0 place-items-center rounded-full text-[11px] font-bold"
            style={{ background: "var(--brand-light)", color: "var(--blue)" }}
          >
            Q
          </div>
          <p className="text-sm font-medium leading-relaxed" style={{ color: "var(--text)" }}>
            {turn.question}
          </p>
        </div>
      </div>

      {/* Answer */}
      <div className="px-5 py-4">
        {a && (
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <ModeBadge mode={a.mode} />
            <ConfidencePill confidence={a.confidence} />
            <Verified answer={a} />
            <div className="ml-auto flex items-center gap-1">
              <CorrectPanel turn={turn} />
              <button onClick={e => { e.stopPropagation(); copyText(); }} className="btn-ghost px-2 py-1 text-xs">
                {copied ? <CheckCheck size={13} style={{ color: "var(--success)" }} /> : <Copy size={13} />}
              </button>
            </div>
          </div>
        )}
        <div className="text-sm leading-relaxed" style={{ color: "var(--text-md)" }}>
          {turn.text
            ? <AnswerText text={turn.text} onCite={onCite} names={citationNames(a)} />
            : <span className="flex items-center gap-2" style={{ color: "var(--muted)" }}>
                <Sparkles size={13} className="animate-pulse" style={{ color: "var(--blue)" }} />
                Thinking through the plant graph…
              </span>
          }
        </div>

        <CorrectionNotice corrections={a?.corrections} />
      </div>
    </div>
  );
}

// doc_id -> filename, for showing citation labels a person can read instead of
// a content hash. Built from the answer's own citations.
function citationNames(answer) {
  const map = {};
  for (const c of answer?.citations || []) {
    if (c.filename) map[c.doc_id] = c.filename;
  }
  return map;
}

// Read off the answer's own citations, checked against the evidence it was
// given. Previously this looked at answer.verified - a field that only exists
// on Alert - so undefined === false was always false and every answer ever
// shown claimed to be grounded.
const GROUNDING = {
  documents: {
    icon: ShieldCheck, label: "grounded",
    style: { background: "#dcfce7", color: "#166534" },
    title: "Every claim is cited to a document in your plant",
  },
  general: {
    icon: BookOpen, label: "general knowledge",
    style: { background: "#fef3c7", color: "#92400e" },
    title: "Answered from general engineering knowledge — not from your documents",
  },
  unverified: {
    icon: ShieldAlert, label: "unverified",
    style: { background: "#fee2e2", color: "#991b1b" },
    title: "Cited a document that was not in its evidence — treat with suspicion",
  },
};

function Verified({ answer }) {
  const g = GROUNDING[answer.grounding] ?? GROUNDING.documents;
  const Icon = g.icon;
  return (
    <span className="badge" style={g.style} title={g.title}>
      <Icon size={10} /> {g.label}
    </span>
  );
}

function Welcome({ onPick }) {
  return (
    <div className="mx-auto flex h-full max-w-2xl flex-col items-center justify-center overflow-y-auto px-4 py-10 text-center sm:px-6 sm:py-12">
      <div
        className="mb-6 grid h-16 w-16 place-items-center rounded-2xl"
        style={{ background: "var(--brand-light)", border: "1px solid var(--brand-mid)" }}
      >
        <Sparkles size={28} style={{ color: "var(--blue)" }} />
      </div>
      <h1
        className="text-2xl font-bold"
        style={{ fontFamily: "'Plus Jakarta Sans', sans-serif", color: "var(--text)" }}
      >
        Ask the plant anything
      </h1>
      <p className="mt-2 text-sm" style={{ color: "var(--muted)" }}>
        Every answer is cited, grounded in your documents, and shows its reasoning path.
      </p>
      <div className="mt-8 grid w-full gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map(s => (
          <button key={s.text} onClick={() => onPick(s.text)}
            className="group text-left rounded-xl px-4 py-4 transition-all duration-150"
            style={{ background: "var(--bg-panel)", border: "1px solid var(--border)", boxShadow: "0 1px 2px rgba(0,0,0,0.04)" }}
            onMouseEnter={e => { e.currentTarget.style.borderColor = "var(--blue-mid)"; e.currentTarget.style.boxShadow = "0 4px 12px rgba(122,84,160,0.08)"; }}
            onMouseLeave={e => { e.currentTarget.style.borderColor = "var(--border)"; e.currentTarget.style.boxShadow = "0 1px 2px rgba(0,0,0,0.04)"; }}
          >
            <span className="mr-2 text-base">{s.icon}</span>
            <span className="text-xs leading-relaxed" style={{ color: "var(--text-md)" }}>{s.text}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function Composer({ input, setInput, onSend, busy, onClear, hasTurns }) {
  return (
    <div
      className="flex-shrink-0 px-4 py-4"
      style={{ background: "var(--bg-panel)", borderTop: "1px solid var(--border)", boxShadow: "0 -1px 4px rgba(0,0,0,0.03)" }}
    >
      <div
        className="mx-auto max-w-3xl rounded-2xl overflow-hidden"
        style={{ border: "1px solid var(--border-md)", background: "var(--bg-panel)", boxShadow: "0 2px 8px rgba(0,0,0,0.06)" }}
      >
        <form onSubmit={e => { e.preventDefault(); onSend(); }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
            rows={Math.min(5, Math.max(1, input.split("\n").length))}
            placeholder="Ask about equipment, failures, procedures, compliance…"
            className="w-full resize-none bg-transparent px-4 py-4 text-sm outline-none"
            style={{ color: "var(--text)", minHeight: "52px" }}
          />
          <div
            className="flex items-center gap-2 px-3 pb-3"
            style={{ borderTop: "1px solid var(--border)" }}
          >
            {hasTurns && (
              <button type="button" onClick={onClear} className="btn-ghost px-2 py-1.5 text-xs gap-1.5">
                <RotateCcw size={12} /> Clear
              </button>
            )}
            {/* Keyboard hint, and only a keyboard has those keys - on a phone
                it is advice you cannot take, and it was squeezing Send. */}
            <span className="hidden flex-1 text-xs sm:block" style={{ color: "var(--muted-lt)" }}>
              Enter to send · Shift+Enter for newline
            </span>
            <span className="flex-1 sm:hidden" />
            <button type="submit" className="btn-primary px-4 py-2 text-xs" disabled={busy || !input.trim()}>
              {busy
                ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
                : <ArrowUp size={14} />
              }
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

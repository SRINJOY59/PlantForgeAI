import { useState } from "react";
import { Check, PencilLine, Send, X } from "lucide-react";
import { submitCorrection } from "../../lib/api";

// The one place a person writes into the brain. Everything else in the app
// reads what documents already said; this is an engineer telling the plant
// something no document contains.
export default function CorrectPanel({ turn }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState("");

  async function submit(e) {
    e.preventDefault();
    e.stopPropagation();
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    try {
      await submitCorrection({
        question: turn.question,
        answer: turn.text,
        correction: text.trim(),
        citedDocs: [...new Set((turn.answer?.citations ?? []).map(c => c.doc_id))],
      });
      setDone(true);
      setOpen(false);
      setText("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (done) {
    return (
      <span className="flex items-center gap-1.5 text-xs" style={{ color: "var(--success)" }}>
        <Check size={12} /> Correction submitted — it'll be in the graph shortly
      </span>
    );
  }

  if (!open) {
    return (
      <button onClick={e => { e.stopPropagation(); setOpen(true); }}
        className="btn-ghost px-2 py-1 text-xs gap-1.5" title="Tell us what's wrong">
        <PencilLine size={12} /> Correct
      </button>
    );
  }

  return (
    <form onSubmit={submit} onClick={e => e.stopPropagation()}
      className="mt-3 w-full rounded-xl p-3"
      style={{ background: "var(--bg-surface)", border: "1px solid var(--border-md)" }}>
      <div className="mb-2 flex items-center gap-2">
        <PencilLine size={12} style={{ color: "var(--blue)" }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted)" }}>
          What's actually correct?
        </span>
        <button type="button" onClick={() => { setOpen(false); setError(""); }}
          className="btn-ghost ml-auto px-1 py-0.5">
          <X size={12} />
        </button>
      </div>

      <textarea
        autoFocus
        rows={3}
        value={text}
        onChange={e => setText(e.target.value)}
        placeholder="Only 2 of those were cavitation — the January failure was misalignment after the coupling change."
        className="w-full resize-y rounded-lg px-3 py-2 text-xs outline-none"
        style={{ background: "var(--bg-panel)", border: "1px solid var(--border)",
                 color: "var(--text)" }}
      />

      <p className="mt-1.5 text-[10px] leading-relaxed" style={{ color: "var(--muted-lt)" }}>
        Signed with your account and stored as a correction record. It enters the
        graph at the human tier — it outranks the documents it contradicts, and
        nothing overwrites it.
      </p>

      {error && (
        <p className="mt-2 text-[10px]" style={{ color: "var(--danger)" }}>{error}</p>
      )}

      <button type="submit" className="btn-primary mt-2 px-3 py-1.5 text-xs"
        disabled={busy || !text.trim()}>
        {busy
          ? <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
          : <><Send size={11} /> Submit correction</>}
      </button>
    </form>
  );
}

import { useState } from "react";
import { GitPullRequestArrow, Send } from "lucide-react";

// A change is a tag and a sentence. The plant's own MOC form has thirty fields;
// none of them help the graph decide what a change touches, and demanding them
// up front is how the tool goes unused. Keep the door low.
const EXAMPLES = [
  { tag: "P-101A", summary: "Replace the mechanical seal with a different seal type." },
  { tag: "V-203", summary: "Raise the design pressure from 10 to 12 barg." },
  { tag: "PSV-204", summary: "Increase the set pressure by 0.5 barg." },
];

export default function ProposalForm({ onSubmit, busy }) {
  const [tag, setTag] = useState("");
  const [summary, setSummary] = useState("");

  const ready = tag.trim() && summary.trim() && !busy;

  function submit(e) {
    e?.preventDefault();
    if (!ready) return;
    onSubmit({ tag: tag.trim(), summary: summary.trim() });
  }

  return (
    <form onSubmit={submit} className="card p-5">
      <div className="mb-4 flex items-center gap-2">
        <GitPullRequestArrow size={16} style={{ color: "var(--blue)" }} />
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Propose a change
        </h2>
      </div>

      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest"
        style={{ color: "var(--muted)" }}>
        Equipment tag
      </label>
      <input
        className="input mb-4 font-mono"
        placeholder="P-101A"
        value={tag}
        onChange={(e) => setTag(e.target.value.toUpperCase())}
        disabled={busy}
      />

      <label className="mb-1 block text-[11px] font-semibold uppercase tracking-widest"
        style={{ color: "var(--muted)" }}>
        What is changing
      </label>
      <textarea
        className="input mb-4 resize-none"
        rows={3}
        placeholder="Replace the mechanical seal with a different seal type."
        value={summary}
        onChange={(e) => setSummary(e.target.value)}
        disabled={busy}
        onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submit(e); }}
      />

      <button type="submit" className="btn-primary w-full justify-center gap-2"
        disabled={!ready}>
        <Send size={13} />
        {busy ? "Assessing…" : "Assess impact"}
      </button>

      <div className="mt-4 border-t pt-3" style={{ borderColor: "var(--border)" }}>
        <p className="mb-2 text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--muted-lt)" }}>
          Try one
        </p>
        <div className="flex flex-col gap-1.5">
          {EXAMPLES.map((ex, i) => (
            <button key={i} type="button" disabled={busy}
              onClick={() => { setTag(ex.tag); setSummary(ex.summary); }}
              className="rounded-lg px-2.5 py-1.5 text-left text-[11px] transition-colors"
              style={{ background: "var(--bg-subtle)", color: "var(--muted)" }}
              onMouseEnter={(e) => { e.currentTarget.style.background = "var(--brand-light)"; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = "var(--bg-subtle)"; }}>
              <span className="tag">{ex.tag}</span>
              <span className="ml-1.5">{ex.summary}</span>
            </button>
          ))}
        </div>
      </div>
    </form>
  );
}

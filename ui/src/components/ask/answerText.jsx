// Renders answer text with [doc:id] / [doc:id p3] citation markers turned
// into clickable chips. onCite(docId) opens the source in the evidence panel.

const CITE_RE = /\[doc:([a-zA-Z0-9_-]+)(?:\s*p(\d+))?\]/g;

export default function AnswerText({ text, onCite }) {
  const parts = [];
  let last = 0;
  let m;
  let key = 0;
  while ((m = CITE_RE.exec(text)) !== null) {
    if (m.index > last) parts.push(text.slice(last, m.index));
    const [, docId, page] = m;
    parts.push(
      <button
        key={`c${key++}`}
        onClick={() => onCite(docId)}
        className="mx-0.5 rounded bg-steel-100 px-1 py-px align-baseline font-mono text-[11px] text-steel-700 hover:bg-steel-200 dark:bg-steel-900 dark:text-steel-300"
      >
        {docId.slice(0, 6)}{page ? `·p${page}` : ""}
      </button>
    );
    last = m.index + m[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));

  return <p className="whitespace-pre-wrap leading-relaxed">{parts}</p>;
}

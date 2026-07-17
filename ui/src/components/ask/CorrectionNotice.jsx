import { PencilLine } from "lucide-react";

// Shown when a source behind this answer has been overturned by someone at the
// plant. The correction is already in the model's prompt, so the prose should
// mention it - but "trust me, I read it" is not something a reader can check.
// This is the receipt.
export default function CorrectionNotice({ corrections }) {
  if (!corrections?.length) return null;

  return (
    <div className="mt-3 rounded-lg px-3 py-2.5"
      style={{ background: "rgba(37,99,235,0.05)",
               border: "1px solid rgba(37,99,235,0.2)" }}>
      <div className="mb-1.5 flex items-center gap-1.5">
        <PencilLine size={11} style={{ color: "var(--blue)" }} />
        <span className="text-[10px] font-semibold uppercase tracking-widest"
          style={{ color: "var(--blue)" }}>
          {corrections.length === 1
            ? "A source here was corrected"
            : `${corrections.length} sources here were corrected`}
        </span>
      </div>
      <div className="space-y-1.5">
        {corrections.map((c, i) => (
          <div key={i} className="text-[11px] leading-relaxed"
            style={{ color: "var(--muted)" }}>
            <span className="tag text-[10px]">{c.doc_id}</span>
            <span className="mx-1">was corrected by</span>
            <span style={{ color: "var(--text-md)" }}>{c.author}</span>
            {c.text && (
              <p className="mt-0.5 border-l-2 pl-2 italic"
                style={{ borderColor: "rgba(37,99,235,0.3)" }}>
                "{c.text}"
              </p>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-[10px]" style={{ color: "var(--muted-lt)" }}>
        The correction outranks the document — this answer follows it.
      </p>
    </div>
  );
}

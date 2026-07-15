"""Turns pruned paths into what the LLM reads: the structured relation
chains (what is connected to what) plus the source passages behind those
edges (what the documents actually say), resolved through each edge's
provenance. Paths are ordered weakest-first so the strongest sits nearest
the question."""

from retrieval.models import Evidence

MAX_EVIDENCE = 8
STEP_NOTE_PROPS = ("cause", "wo_id", "date", "next_due", "result")


class ContextAssembler:
    def __init__(self, reader):
        self._reader = reader
        self._doc_cache = {}

    def build(self, paths: list) -> tuple:
        """-> (context_text, [Evidence])"""
        self._doc_cache.clear()
        evidence, seen_chunks = [], set()

        lines = []
        for path in sorted(paths, key=lambda p: p.score):
            lines.append(self._textualize(path))
            for step in path.steps:
                if len(evidence) >= MAX_EVIDENCE:
                    break
                ev = self._evidence_for(step)
                if ev and ev.chunk_id not in seen_chunks:
                    seen_chunks.add(ev.chunk_id)
                    evidence.append(ev)

        context = "GRAPH PATHS (weakest to strongest):\n" + "\n".join(lines)
        if evidence:
            context += "\n\nSOURCE PASSAGES:\n" + "\n\n".join(
                f"[{e.doc_id}" + (f" p{e.page}" if e.page else "") + "]\n"
                + (e.context or "") + e.text[:600]
                for e in evidence)
        return context, evidence

    def _textualize(self, path) -> str:
        parts = []
        for i, step in enumerate(path.steps):
            src = path.nodes.get(step.src, {}).get("surface", step.src)
            dst = path.nodes.get(step.dst, {}).get("surface", step.dst)
            notes = ", ".join(f"{k}: {step.props[k]}" for k in STEP_NOTE_PROPS
                              if step.props.get(k))
            arrow = f" -{step.type}" + (f" ({notes})" if notes else "") + "-> "
            if i == 0:
                parts.append(f"({src})")
            parts.append(arrow + f"({dst})")
        return "  " + "".join(parts) + f"   [score {path.score:.3f}]"

    def _evidence_for(self, step) -> Evidence:
        doc_id = step.props.get("doc_id")
        if not doc_id:
            return None
        chunks = self._doc_cache.setdefault(
            doc_id, self._reader.chunks_of_doc(doc_id))
        if not chunks:
            return None

        best = self._best_chunk(chunks, step.props)
        return Evidence(doc_id=doc_id, text=best["text"],
                        context=best.get("context") or "",
                        page=best.get("page"), chunk_id=best["id"])

    @staticmethod
    def _best_chunk(chunks, props):
        page = props.get("page")
        if page is not None:
            same_page = [c for c in chunks if c.get("page") == page]
            if same_page:
                return same_page[0]
        return chunks[0]

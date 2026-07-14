from dataclasses import dataclass, field


@dataclass
class Chunk:
    index: int          # global across the document
    text: str
    start: int          # exact char offsets: doc[start:end] == text
    end: int


@dataclass
class Section:
    index: int
    title: str
    start: int
    end: int
    chunks: list[Chunk] = field(default_factory=list)


class SectionChunker:
    """Markdown-aware two-level chunking: sections along headers, then
    paragraph-packed chunks inside each section. Offsets always point into
    the original text so provenance spans stay exact - retrieval searches
    the small chunks but reads their parent section."""

    def __init__(self, max_chars: int = 2400):
        self.max_chars = max_chars

    def split(self, text: str) -> list[Section]:
        sections = []
        chunk_counter = 0
        for title, lo, hi in self._section_spans(text):
            chunks = []
            for span_group in self._packed_paragraphs(text, lo, hi):
                start, end = span_group[0][0], span_group[-1][1]
                tight_start, tight_end = _tighten(text, start, end)
                if tight_start >= tight_end:
                    continue
                chunks.append(Chunk(index=chunk_counter,
                                    text=text[tight_start:tight_end],
                                    start=tight_start, end=tight_end))
                chunk_counter += 1
            if chunks:
                sections.append(Section(index=len(sections), title=title,
                                        start=chunks[0].start,
                                        end=chunks[-1].end, chunks=chunks))
        return sections

    @staticmethod
    def _section_spans(text: str):
        title, body_lo, pos = "", 0, 0
        for line in text.splitlines(keepends=True):
            if line.lstrip().startswith("#"):
                yield title, body_lo, pos
                title = line.strip().lstrip("#").strip()
                body_lo = pos + len(line)
            pos += len(line)
        yield title, body_lo, pos

    def _packed_paragraphs(self, text: str, lo: int, hi: int):
        """Group consecutive paragraphs up to max_chars; a paragraph is a
        run of non-blank lines. Never cuts mid-paragraph."""
        group, size = [], 0
        for start, end in self._paragraphs(text, lo, hi):
            if group and size + (end - start) > self.max_chars:
                yield group
                group, size = [], 0
            group.append((start, end))
            size += end - start
        if group:
            yield group

    @staticmethod
    def _paragraphs(text: str, lo: int, hi: int):
        pos, para_start = lo, None
        for line in text[lo:hi].splitlines(keepends=True):
            if not line.strip():
                if para_start is not None:
                    yield para_start, pos
                    para_start = None
            elif para_start is None:
                para_start = pos
            pos += len(line)
        if para_start is not None:
            yield para_start, pos


def _tighten(text: str, start: int, end: int):
    """Shrink a span to its stripped content so doc[start:end] == chunk.text."""
    raw = text[start:end]
    return (start + len(raw) - len(raw.lstrip()),
            end - (len(raw) - len(raw.rstrip())))


def main():
    """usage (from plantmind/services):
    ../.venv/Scripts/python -m extraction.text.chunker ../data/samples/sop_pump_seal_replacement.md"""
    import sys

    from plantmind_core.devtools import find_file

    for arg in sys.argv[1:]:
        text = find_file(arg).read_text(encoding="utf-8")
        for section in SectionChunker().split(text):
            print(f"\n== [{section.index}] {section.title or '(start)'} "
                  f"({section.start}-{section.end})")
            for c in section.chunks:
                print(f"   chunk {c.index}: ", c.text.replace("\n", " "))


if __name__ == "__main__":
    main()

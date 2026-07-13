from dataclasses import dataclass


@dataclass
class Chunk:
    index: int
    text: str
    section: str
    start: int          # char offsets into the original document
    end: int


class SectionChunker:
    """Splits prose along markdown headers first, then caps chunk size on
    paragraph boundaries. Offsets always point back into the original text
    so provenance spans survive chunking."""

    def __init__(self, max_chars: int = 2400):
        self.max_chars = max_chars

    def split(self, text: str) -> list[Chunk]:
        chunks = []
        section = ""
        buf_start = None
        buf_parts = []

        def flush(end_pos):
            nonlocal buf_start, buf_parts
            body = "".join(buf_parts).strip()
            if body:
                chunks.append(Chunk(index=len(chunks), text=body,
                                    section=section, start=buf_start,
                                    end=end_pos))
            buf_start, buf_parts = None, []

        pos = 0
        for line in text.splitlines(keepends=True):
            stripped = line.strip()
            if stripped.startswith("#"):
                flush(pos)
                section = stripped.lstrip("#").strip()
            else:
                if buf_start is None:
                    buf_start = pos
                if sum(len(p) for p in buf_parts) + len(line) > self.max_chars \
                        and stripped == "":
                    flush(pos)          # cut on a blank line, never mid-paragraph
                else:
                    buf_parts.append(line)
            pos += len(line)
        flush(pos)
        return chunks

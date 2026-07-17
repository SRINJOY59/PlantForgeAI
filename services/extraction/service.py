import asyncio

from plantmind_core import corrections
from plantmind_core.schemas import CandidateSubgraph
from plantmind_core.storage import ObjectStore

from extraction.manual.pdfio import read_pdf_pages


class ExtractionService:
    """One handler per document lane, every handler the same shape: fetch
    the bytes the payload points at, run its lane, return the
    CandidateSubgraph. Pure logic - what happens to the subgraph next is
    the pipeline topology's decision, applied by the task adapter."""

    def __init__(self, store: ObjectStore, table=None, text=None,
                 pnid=None, manual=None, email=None, image=None,
                 correction=None):
        self._store = store
        self._table = table
        self._text = text
        self._pnid = pnid
        self._manual = manual
        self._email = email
        self._image = image
        self._correction = correction

    @classmethod
    def from_settings(cls) -> "ExtractionService":
        from plantmind_core.llm import get_embedder, get_llm

        from extraction.correction.extractor import CorrectionExtractor
        from extraction.imaging.extractor import ImageLane
        from extraction.mail.extractor import EmailExtractor
        from extraction.manual.extractor import ManualExtractor
        from extraction.pnid.extractor import PnidExtractor
        from extraction.text.extractor import TextExtractor
        from extraction.workorder.parser import TableParser

        llm, embedder = get_llm(), get_embedder()
        text = TextExtractor(llm, embedder)
        pnid = PnidExtractor(llm)
        return cls(
            store=ObjectStore.from_settings(),
            table=TableParser(llm), text=text, pnid=pnid,
            manual=ManualExtractor(llm, embedder),
            email=EmailExtractor(text),
            image=ImageLane(llm, embedder, pnid, text),
            correction=CorrectionExtractor(llm),
        )

    # ------------------------------------------------------------- handlers
    def parse_table(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._table.parse(*doc, data))

    def extract_text(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._text.extract(
            *doc, data.decode("utf-8", errors="replace")))

    def extract_pnid(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._pnid.extract(*doc, data))

    def extract_manual(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._manual.extract(*doc, read_pdf_pages(data)))

    def extract_email(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._email.extract(*doc, data))

    def extract_image(self, payload: dict) -> CandidateSubgraph:
        doc, data = self._fetch(payload)
        return asyncio.run(self._image.extract(*doc, data))

    def extract_correction(self, payload: dict) -> CandidateSubgraph:
        (doc_id, content_hash, _), data = self._fetch(payload)
        c = corrections.parse(data.decode("utf-8", errors="replace"))
        return asyncio.run(self._correction.extract(
            doc_id=doc_id, content_hash=content_hash, question=c.question,
            answer=c.answer, correction=c.correction, author=c.author,
            wrong_doc_ids=c.cited_docs))

    def _fetch(self, payload: dict):
        """-> ((doc_id, content_hash, filename), raw bytes)"""
        data = self._store.get(payload["object_key"])
        return (payload["doc_id"], payload["content_hash"],
                payload["filename"]), data

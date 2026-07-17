"""Edge logic that isn't HTTP plumbing: accept an upload into the pipeline,
fetch an original document for a citation click, gather metrics. The
FastAPI layer (main.py) owns request/response and proxying to retrieval."""

import uuid
from datetime import date

from plantmind_core import corrections
from plantmind_core.bus import RedisBus
from plantmind_core.pipeline import stage_and_enqueue
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

log = get_logger("gateway.service")


class GatewayService:
    def __init__(self, store: ObjectStore, bus: RedisBus, sender):
        self._store = store
        self._bus = bus
        self._send = sender

    @classmethod
    def from_settings(cls) -> "GatewayService":
        from plantmind_core.celeryapp import WorkerApp
        return cls(ObjectStore.from_settings(), RedisBus.from_settings(),
                   WorkerApp("gateway").send)

    def ingest(self, filename: str, data: bytes, source="upload") -> dict:
        """Stage the bytes and drop a classify note - the synchronous half of
        an async pipeline: we acknowledge 'accepted', not 'processed'."""
        stage_and_enqueue(self._store, self._send, filename, data, source)
        log.info("accepted upload", filename=filename, size=len(data))
        return {"status": "accepted", "filename": filename}

    def correct(self, question: str, answer: str, correction: str,
                author: str, cited_docs: list) -> dict:
        """An engineer says we got something wrong.

        It takes the ordinary ingest road, because that is all a correction
        is: a short document, written by a person instead of a vendor, that
        the plant did not have before. Same staging, same classify note, same
        extraction and resolution behind it - the lane it lands in is what
        marks its provenance HUMAN.
        """
        record = corrections.Correction(
            question=question, answer=answer, correction=correction,
            author=author, date=date.today().isoformat(),
            cited_docs=cited_docs)
        name = corrections.filename(uuid.uuid4().hex[:12])
        stage_and_enqueue(self._store, self._send, name,
                          corrections.render(record), source="correction")
        log.info("accepted correction", author=author, filename=name,
                 corrects=cited_docs)
        return {"status": "accepted", "filename": name}

    def document(self, doc_id: str):
        """(filename, bytes) for a citation's source, or None."""
        return self._store.find_document(doc_id)

    def metrics(self) -> dict:
        return {"graph_version": self._bus.graph_version(),
                "queues": self._bus.depths()}

    def read_alerts(self, after: str, block_ms: int):
        return self._bus.read_alerts(after, block_ms=block_ms)

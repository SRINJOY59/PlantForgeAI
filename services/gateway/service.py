"""Edge logic that isn't HTTP plumbing: accept an upload into the pipeline,
fetch an original document for a citation click, gather metrics. The
FastAPI layer (main.py) owns request/response and proxying to retrieval."""

import uuid

from plantmind_core.bus import RedisBus
from plantmind_core.queues import Flow
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
        staging_key = f"staging/{uuid.uuid4().hex}/{filename}"
        self._store.put(staging_key, data)
        self._send(Flow.ingest, {"staging_key": staging_key,
                                 "filename": filename, "source": source})
        log.info("accepted upload", filename=filename, size=len(data))
        return {"status": "accepted", "filename": filename}

    def document(self, doc_id: str):
        """(filename, bytes) for a citation's source, or None."""
        return self._store.find_document(doc_id)

    def metrics(self) -> dict:
        return {"graph_version": self._bus.graph_version(),
                "queues": self._bus.depths()}

    def read_alerts(self, after: str, block_ms: int):
        return self._bus.read_alerts(after, block_ms=block_ms)

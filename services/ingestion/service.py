import hashlib

from plantmind_core.bus import RedisBus
from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

from ingestion.classify import Classifier

log = get_logger("ingestion.service")


class IngestionService:
    """The front door: content-hash dedup, classification, promotion to the
    raw archive. Pure logic - where the document goes NEXT is the pipeline
    topology's decision (plantmind_core.queues.Flow), applied by the task
    adapter, never in here."""

    def __init__(self, store: ObjectStore, bus: RedisBus,
                 classifier: Classifier):
        self._store = store
        self._bus = bus
        self._classifier = classifier

    def classify_document(self, payload: dict) -> dict:
        """payload: {staging_key, filename, source?} - the uploader put the
        raw bytes at staging_key and enqueued us."""
        staging_key = payload["staging_key"]
        filename = payload["filename"]

        data = self._store.get(staging_key)
        content_hash = hashlib.sha256(data).hexdigest()

        if not self._bus.claim_document(content_hash):
            self._store.delete(staging_key)
            log.info("duplicate dropped", filename=filename,
                     content_hash=content_hash)
            return {"status": "duplicate", "content_hash": content_hash}

        try:
            doc_id = content_hash[:16]
            object_key = f"raw/{doc_id}/{filename}"
            self._store.move(staging_key, object_key)

            sniff = data[:2048].decode("utf-8", errors="ignore")
            kind = self._classifier.classify(filename, sniff, data)
        except Exception:
            # give the claim back, otherwise a transient failure here would
            # permanently block this file from ever being ingested
            self._bus.release_document(content_hash)
            raise

        log.info("document classified", doc_id=doc_id, filename=filename,
                 kind=kind.value)
        return {
            "status": "classified",
            "doc_id": doc_id,
            "kind": kind.value,
            "next_payload": {
                "doc_id": doc_id,
                "object_key": object_key,
                "filename": filename,
                "content_hash": content_hash,
                "source": payload.get("source"),
            },
        }

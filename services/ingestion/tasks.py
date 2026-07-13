import asyncio
import hashlib

from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.llm import Tier, get_llm
from plantmind_core.queues import Routes
from plantmind_core.telemetry import get_logger

from ingestion.classify import ROUTE_FOR, Classifier
from plantmind_core.storage import ObjectStore

log = get_logger("ingestion.tasks")
settings = get_settings()

worker = WorkerApp("ingestion")
celery_app = worker.app  # celery CLI entrypoint: celery -A ingestion.tasks ...

_store = None
_bus = None
_classifier = None


def _llm_classify(filename: str, sniff: str) -> str:
    prompt = (
        "Classify this industrial document as exactly one of: table, pnid, text.\n"
        "table = structured rows (work orders, inspections). pnid = engineering "
        f"drawing. text = prose document.\n\nFilename: {filename}\n"
        f"First bytes:\n{sniff[:800]}\n\nAnswer with the single word only."
    )
    reply = asyncio.run(get_llm().complete(
        [{"role": "user", "content": prompt}], tier=Tier.CHEAP, max_tokens=5))
    return reply.strip().lower()


def _deps():
    global _store, _bus, _classifier
    if _store is None:
        _store = ObjectStore.from_settings()
    if _bus is None:
        _bus = RedisBus.from_settings()
    if _classifier is None:
        _classifier = Classifier(llm_fallback=_llm_classify)
    return _store, _bus, _classifier


@worker.task(Routes.classify)
def classify_document(payload: dict):
    store, bus, classifier = _deps()
    return run_classify(payload, store, bus, classifier, sender=worker.send)


def run_classify(payload: dict, store: ObjectStore, bus: RedisBus,
                 classifier: Classifier, sender) -> dict:
    """payload: {staging_key, filename, source?} - the uploader put the raw
    bytes at staging_key and enqueued us."""
    staging_key = payload["staging_key"]
    filename = payload["filename"]

    data = store.get(staging_key)
    content_hash = hashlib.sha256(data).hexdigest()

    if not bus.claim_document(content_hash):
        store.delete(staging_key)
        log.info("duplicate dropped", filename=filename, content_hash=content_hash)
        return {"status": "duplicate", "content_hash": content_hash}

    try:
        doc_id = content_hash[:16]
        object_key = f"raw/{doc_id}/{filename}"
        store.move(staging_key, object_key)

        sniff = data[:2048].decode("utf-8", errors="ignore")
        kind = classifier.classify(filename, sniff)

        route = ROUTE_FOR[kind]
        sender(route, {
            "doc_id": doc_id,
            "object_key": object_key,
            "filename": filename,
            "content_hash": content_hash,
            "source": payload.get("source"),
        })
    except Exception:
        # give the claim back, otherwise a transient failure here would
        # permanently block this file from ever being ingested
        bus.release_document(content_hash)
        raise

    log.info("document routed", doc_id=doc_id, filename=filename,
             kind=kind.value, queue=route.queue)
    return {"status": "queued", "doc_id": doc_id, "kind": kind.value,
            "queue": route.queue}

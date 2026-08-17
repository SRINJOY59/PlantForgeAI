from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Flow, Routes
from plantmind_core.schemas import CandidateSubgraph
from plantmind_core.telemetry import get_logger

from extraction.service import ExtractionService

log = get_logger("extraction.tasks")

worker = WorkerApp("extraction")
celery_app = worker.app  # celery CLI entrypoint: celery -A extraction.tasks ...

_service = None
_bus = None


def _instance() -> ExtractionService:
    global _service
    if _service is None:
        _service = ExtractionService.from_settings()
    return _service


def _get_bus() -> RedisBus:
    global _bus
    if _bus is None:
        _bus = RedisBus.from_settings()
    return _bus


def _run_lane(handler, payload: dict, lane: str) -> dict:
    """A lane that fails must give the document's hash claim back -
    otherwise the file is permanently stuck as claimed-but-never-in-graph
    and no resubmission can heal it."""
    content_hash = payload.get("content_hash", "")
    bus = _get_bus()

    # 1. Check idempotency cache first (skip expensive OCR/VLM if already extracted)
    if content_hash:
        cached_raw = bus.get_cached_extraction(content_hash, lane)
        if cached_raw:
            try:
                csg = CandidateSubgraph.model_validate_json(cached_raw)
                worker.send(Flow.after_extraction, csg.model_dump(mode="json"))
                log.info("lane extraction cache hit", lane=lane, doc_id=csg.doc_id,
                         nodes=len(csg.nodes), edges=len(csg.edges))
                return {"status": "cache_hit", "lane": lane, "doc_id": csg.doc_id,
                        "nodes": len(csg.nodes), "edges": len(csg.edges)}
            except Exception as e:
                log.warning("failed to deserialize cached extraction", error=str(e))

        # 2. Acquire single-flight lock to prevent duplicate concurrent extraction
        lock_acquired = bus.acquire_extraction_lock(content_hash, lane)
        if not lock_acquired:
            # Check if cache was populated while waiting
            cached_raw = bus.get_cached_extraction(content_hash, lane)
            if cached_raw:
                try:
                    csg = CandidateSubgraph.model_validate_json(cached_raw)
                    worker.send(Flow.after_extraction, csg.model_dump(mode="json"))
                    log.info("lane extraction concurrent cache hit", lane=lane, doc_id=csg.doc_id)
                    return {"status": "cache_hit", "lane": lane, "doc_id": csg.doc_id,
                            "nodes": len(csg.nodes), "edges": len(csg.edges)}
                except Exception:
                    pass
            log.info("lane extraction already in flight by another worker, dropping duplicate task",
                     lane=lane, doc_id=payload.get("doc_id"), content_hash=content_hash)
            return {"status": "in_flight", "lane": lane, "doc_id": payload.get("doc_id")}

    try:
        csg = handler(payload)
        if content_hash:
            try:
                bus.set_cached_extraction(content_hash, lane, csg.model_dump_json())
            except Exception as cache_err:
                log.warning("failed to cache extraction result", error=str(cache_err))
    except Exception as e:
        if content_hash:
            bus.release_document(content_hash)
        log.error("lane failed, claim released for retry", lane=lane,
                  doc_id=payload.get("doc_id"),
                  filename=payload.get("filename"), error=str(e)[:200])
        raise
    finally:
        if content_hash:
            bus.release_extraction_lock(content_hash, lane)

    worker.send(Flow.after_extraction, csg.model_dump(mode="json"))
    log.info("lane extracted", lane=lane, doc_id=csg.doc_id,
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "lane": lane, "doc_id": csg.doc_id,
            "nodes": len(csg.nodes), "edges": len(csg.edges)}


@worker.task(Routes.parse_workorder)
def parse_workorder(payload: dict):
    return _run_lane(_instance().parse_table, payload, "table")


@worker.task(Routes.extract_text)
def extract_text(payload: dict):
    return _run_lane(_instance().extract_text, payload, "text")


@worker.task(Routes.extract_pnid)
def extract_pnid(payload: dict):
    return _run_lane(_instance().extract_pnid, payload, "pnid")


@worker.task(Routes.extract_manual)
def extract_manual(payload: dict):
    return _run_lane(_instance().extract_manual, payload, "manual")


@worker.task(Routes.extract_email)
def extract_email(payload: dict):
    return _run_lane(_instance().extract_email, payload, "email")


@worker.task(Routes.extract_image)
def extract_image(payload: dict):
    return _run_lane(_instance().extract_image, payload, "image")


@worker.task(Routes.extract_correction)
def extract_correction(payload: dict):
    return _run_lane(_instance().extract_correction, payload, "correction")

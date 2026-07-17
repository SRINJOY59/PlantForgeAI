from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Flow, Routes
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
    try:
        csg = handler(payload)
    except Exception as e:
        _get_bus().release_document(payload["content_hash"])
        log.error("lane failed, claim released for retry", lane=lane,
                  doc_id=payload.get("doc_id"),
                  filename=payload.get("filename"), error=str(e)[:200])
        raise
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

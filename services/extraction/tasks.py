from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Flow, Routes
from plantmind_core.telemetry import get_logger

from extraction.service import ExtractionService

log = get_logger("extraction.tasks")

worker = WorkerApp("extraction")
celery_app = worker.app  # celery CLI entrypoint: celery -A extraction.tasks ...

_service = None


def _instance() -> ExtractionService:
    global _service
    if _service is None:
        _service = ExtractionService.from_settings()
    return _service


def _ship(csg, lane: str) -> dict:
    worker.send(Flow.after_extraction, csg.model_dump(mode="json"))
    log.info("lane extracted", lane=lane, doc_id=csg.doc_id,
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "lane": lane, "doc_id": csg.doc_id,
            "nodes": len(csg.nodes), "edges": len(csg.edges)}


@worker.task(Routes.parse_workorder)
def parse_workorder(payload: dict):
    return _ship(_instance().parse_table(payload), "table")


@worker.task(Routes.extract_text)
def extract_text(payload: dict):
    return _ship(_instance().extract_text(payload), "text")


@worker.task(Routes.extract_pnid)
def extract_pnid(payload: dict):
    return _ship(_instance().extract_pnid(payload), "pnid")


@worker.task(Routes.extract_manual)
def extract_manual(payload: dict):
    return _ship(_instance().extract_manual(payload), "manual")


@worker.task(Routes.extract_email)
def extract_email(payload: dict):
    return _ship(_instance().extract_email(payload), "email")


@worker.task(Routes.extract_image)
def extract_image(payload: dict):
    return _ship(_instance().extract_image(payload), "image")

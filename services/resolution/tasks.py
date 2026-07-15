from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Routes

from resolution.service import ResolutionService

worker = WorkerApp("resolution")
celery_app = worker.app  # celery CLI entrypoint: celery -A resolution.tasks ...

_service = ResolutionService()
_bus = None


def _get_bus() -> RedisBus:
    global _bus
    if _bus is None:
        _bus = RedisBus.from_settings()
    return _bus


@worker.task(Routes.resolve)
def resolve(payload: dict):
    try:
        csg = _service.resolve(payload)
    except Exception:
        # give the hash claim back so resubmitting the file can heal this
        content_hash = payload.get("content_hash")
        if content_hash:
            _get_bus().release_document(content_hash)
        raise
    _get_bus().queue_subgraph(csg.model_dump_json())
    return {"status": "queued_for_write", "doc_id": csg.doc_id, "nodes": len(csg.nodes)}

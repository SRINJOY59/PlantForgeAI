from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.queues import Routes
from plantmind_core.schemas import CandidateSubgraph
from plantmind_core.telemetry import get_logger

from resolution.resolver import Resolver

log = get_logger("resolution.tasks")

worker = WorkerApp("resolution")
celery_app = worker.app  # celery CLI entrypoint: celery -A resolution.tasks ...

_bus = None
_resolver = Resolver()


def _deps():
    global _bus
    if _bus is None:
        _bus = RedisBus.from_settings()
    return _bus


@worker.task(Routes.resolve)
def resolve(payload: dict):
    return run_resolve(payload, _deps(), _resolver)


def run_resolve(payload: dict, bus: RedisBus, resolver: Resolver) -> dict:
    csg = CandidateSubgraph.model_validate(payload)
    csg = resolver.resolve(csg)
    bus.queue_subgraph(csg.model_dump_json())
    log.info("subgraph resolved and queued", doc_id=csg.doc_id, nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "queued_for_write", "doc_id": csg.doc_id, "nodes": len(csg.nodes)}

from pydantic import ValidationError

from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.queues import Routes
from plantmind_core.schemas import CandidateSubgraph, GraphDelta
from plantmind_core.telemetry import get_logger

from graphd.batching import group_batch
from graphd.store import GraphStore

log = get_logger("graphd.writer")
settings = get_settings()

worker = WorkerApp("graphd")
worker.schedule(Routes.flush, every_seconds=settings.write_flush_interval_s)
# denoise gets scheduled here once implemented

celery_app = worker.app  # celery CLI entrypoint: celery -A graphd.writer ...

_bus = None
_store = None


def _deps():
    global _bus, _store
    if _bus is None:
        _bus = RedisBus.from_settings()
    if _store is None:
        _store = GraphStore.from_settings()
    return _bus, _store


@worker.task(Routes.flush)
def flush_write_buffer():
    bus, store = _deps()
    return run_flush(bus, store, settings.write_batch_size)


def run_flush(bus: RedisBus, store: GraphStore, batch_size: int,
              max_rounds: int = 20) -> dict:
    """Drain the write buffer in batches of batch_size, one transaction each.
    max_rounds caps a single invocation so a huge backfill can't starve the
    beat loop forever — the next tick continues where this one stopped."""

    # the queue itself serialises writers; this lock only guards against
    # overlapping beat ticks when a flush runs longer than the interval
    if not bus.acquire_flush_lock():
        return {"skipped": "already flushing"}

    stats = {"rounds": 0, "subgraphs": 0, "nodes": 0, "edges": 0, "bad": 0}
    try:
        for _ in range(max_rounds):
            items = bus.take_subgraphs(batch_size)
            if not items:
                break

            subgraphs = []
            for raw in items:
                try:
                    subgraphs.append(CandidateSubgraph.model_validate_json(raw))
                except ValidationError as e:
                    bus.park_bad_subgraph(raw)
                    stats["bad"] += 1
                    log.error("bad item sent to DLQ", error=str(e)[:200])

            if subgraphs:
                try:
                    batch = group_batch(subgraphs)
                except ValueError as e:
                    # unresolved nodes mean a resolver bug; park the whole
                    # round in the DLQ rather than drop or crash-loop
                    for csg in subgraphs:
                        bus.park_bad_subgraph(csg.model_dump_json())
                    stats["bad"] += len(subgraphs)
                    log.error("ungroupable round sent to DLQ", error=str(e))
                    continue

                if not batch.empty:
                    version = bus.next_graph_version()
                    store.write_batch(batch, version)
                    delta = GraphDelta(
                        graph_version=version,
                        touched_node_ids=sorted(batch.node_ids),
                        new_edge_types=sorted(batch.edge_types),
                        source_doc_ids=sorted(batch.doc_ids),
                    )
                    bus.publish_delta(delta.model_dump_json())

                stats["subgraphs"] += len(subgraphs)
                stats["nodes"] += len(batch.node_ids)
                stats["edges"] += sum(len(v) for v in batch.edges_by_type.values())

            stats["rounds"] += 1
            if len(items) < batch_size:
                break
    finally:
        bus.release_flush_lock()

    if stats["subgraphs"] or stats["bad"]:
        log.info("flush done", **stats)
    return stats

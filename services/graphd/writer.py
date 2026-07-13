import redis
from celery import Celery
from pydantic import ValidationError

from plantmind_core import keys
from plantmind_core.config import get_settings
from plantmind_core.schemas import CandidateSubgraph, GraphDelta
from plantmind_core.telemetry import get_logger

from graphd.batching import group_batch
from graphd.store import GraphStore

log = get_logger("graphd.writer")
settings = get_settings()

celery_app = Celery("graphd", broker=settings.redis_url)
celery_app.conf.timezone = "UTC"
celery_app.conf.beat_schedule = {
    "flush-write-buffer": {
        "task": "graphd.writer.flush_write_buffer",
        "schedule": settings.write_flush_interval_s,
        "options": {"queue": "q_write"},
    },
    # denoise job gets registered here once implemented
}

_redis = None
_store = None


def _deps():
    global _redis, _store
    if _redis is None:
        _redis = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    if _store is None:
        _store = GraphStore.from_settings()
    return _redis, _store


@celery_app.task(name="graphd.writer.flush_write_buffer")
def flush_write_buffer():
    r, store = _deps()
    return run_flush(r, store, settings.write_batch_size)


def run_flush(r, store: GraphStore, batch_size: int, max_rounds: int = 20) -> dict:
    """Drain the write buffer in batches of batch_size, one transaction each.
    max_rounds caps a single invocation so a huge backfill can't starve the
    beat loop forever — the next tick continues where this one stopped."""

    # the queue itself serialises writers; this lock only guards against
    # overlapping beat ticks when a flush runs longer than the interval
    if not r.set(keys.FLUSH_LOCK, "1", nx=True, ex=60):
        return {"skipped": "already flushing"}

    stats = {"rounds": 0, "subgraphs": 0, "nodes": 0, "edges": 0, "bad": 0}
    try:
        for _ in range(max_rounds):
            items = r.lpop(keys.WRITE_BUFFER, batch_size)
            if not items:
                break

            subgraphs = []
            for raw in items:
                try:
                    subgraphs.append(CandidateSubgraph.model_validate_json(raw))
                except ValidationError as e:
                    r.rpush(keys.WRITE_DLQ, raw)
                    stats["bad"] += 1
                    log.error("bad item sent to DLQ", error=str(e)[:200])

            if subgraphs:
                try:
                    batch = group_batch(subgraphs)
                except ValueError as e:
                    # unresolved nodes mean a resolver bug; park the whole
                    # round in the DLQ rather than drop or crash-loop
                    for csg in subgraphs:
                        r.rpush(keys.WRITE_DLQ, csg.model_dump_json())
                    stats["bad"] += len(subgraphs)
                    log.error("ungroupable round sent to DLQ", error=str(e))
                    continue

                if not batch.empty:
                    version = r.incr(keys.GRAPH_VERSION)
                    store.write_batch(batch, version)
                    delta = GraphDelta(
                        graph_version=version,
                        touched_node_ids=sorted(batch.node_ids),
                        new_edge_types=sorted(batch.edge_types),
                        source_doc_ids=sorted(batch.doc_ids),
                    )
                    r.xadd(keys.DELTA_STREAM, {"payload": delta.model_dump_json()})

                stats["subgraphs"] += len(subgraphs)
                stats["nodes"] += len(batch.node_ids)
                stats["edges"] += sum(len(v) for v in batch.edges_by_type.values())

            stats["rounds"] += 1
            if len(items) < batch_size:
                break
    finally:
        r.delete(keys.FLUSH_LOCK)

    if stats["subgraphs"] or stats["bad"]:
        log.info("flush done", **stats)
    return stats

from pydantic import ValidationError

from plantmind_core.bus import RedisBus
from plantmind_core.config import get_settings
from plantmind_core.schemas import CandidateSubgraph, GraphDelta
from plantmind_core.telemetry import get_logger

from graphd.batching import group_batch
from graphd.store import GraphStore

log = get_logger("graphd.writer")


class GraphWriter:
    """The single writer. Drains resolved subgraphs from the write buffer in
    batches, commits each batch as one transaction, stamps it with a version
    and announces it on the delta stream. Concurrency safety comes from the
    flush lock plus the fact that exactly one of these runs (q_write, -c 1)."""

    def __init__(self, bus: RedisBus, store: GraphStore,
                 batch_size: int, max_rounds: int = 20):
        self._bus = bus
        self._store = store
        self._batch_size = batch_size
        self._max_rounds = max_rounds

    @classmethod
    def from_settings(cls) -> "GraphWriter":
        return cls(RedisBus.from_settings(), GraphStore.from_settings(),
                   get_settings().write_batch_size)

    def flush(self) -> dict:
        """One drain cycle. max_rounds caps it so a huge backfill can't
        starve the beat loop - the next tick continues where this stopped."""
        if not self._bus.acquire_flush_lock():
            return {"skipped": "already flushing"}

        stats = {"rounds": 0, "subgraphs": 0, "nodes": 0, "edges": 0, "bad": 0}
        try:
            for _ in range(self._max_rounds):
                items = self._bus.take_subgraphs(self._batch_size)
                if not items:
                    break
                subgraphs = self._parse(items, stats)
                if subgraphs:
                    self._commit(subgraphs, stats)
                stats["rounds"] += 1
                if len(items) < self._batch_size:
                    break
        finally:
            self._bus.release_flush_lock()

        if stats["subgraphs"] or stats["bad"]:
            log.info("flush done", **stats)
        return stats

    def _parse(self, items, stats) -> list:
        subgraphs = []
        for raw in items:
            try:
                subgraphs.append(CandidateSubgraph.model_validate_json(raw))
            except ValidationError as e:
                self._bus.park_bad_subgraph(raw)
                stats["bad"] += 1
                log.error("bad item sent to DLQ", error=str(e)[:200])
        return subgraphs

    def _commit(self, subgraphs, stats):
        try:
            batch = group_batch(subgraphs)
        except ValueError as e:
            # unresolved nodes mean a resolver bug; park the whole round
            # as replayable json rather than drop or crash-loop
            for csg in subgraphs:
                self._bus.park_bad_subgraph(csg.model_dump_json())
            stats["bad"] += len(subgraphs)
            log.error("ungroupable round sent to DLQ", error=str(e))
            return

        if batch.empty:
            return
        try:
            version = self._bus.next_graph_version()
            self._store.write_batch(batch, version)
        except Exception as e:
            # one poison subgraph must not sink the whole round: retry them
            # one by one so only the culprit lands in the DLQ
            if len(subgraphs) == 1:
                self._bus.park_bad_subgraph(subgraphs[0].model_dump_json())
                stats["bad"] += 1
                log.error("subgraph rejected by store, parked in DLQ",
                          doc_id=subgraphs[0].doc_id, error=str(e)[:200])
                return
            log.warning("batch write failed, retrying subgraphs individually",
                        size=len(subgraphs), error=str(e)[:200])
            for csg in subgraphs:
                self._commit([csg], stats)
            return

        self._bus.publish_delta(GraphDelta(
            graph_version=version,
            touched_node_ids=sorted(batch.node_ids),
            new_edge_types=sorted(batch.edge_types),
            source_doc_ids=sorted(batch.doc_ids),
        ).model_dump_json())
        stats["subgraphs"] += len(subgraphs)
        stats["nodes"] += len(batch.node_ids)
        stats["edges"] += sum(len(v) for v in batch.edges_by_type.values())


def main():
    """usage (needs redis+neo4j running): python -m graphd.writer
    Runs one flush of whatever is sitting in the write buffer."""
    print(GraphWriter.from_settings().flush())


if __name__ == "__main__":
    main()

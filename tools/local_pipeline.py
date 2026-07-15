"""The whole pipeline in one process: classify -> extract -> resolve ->
batch -> write, with function calls where the queues would be. Same classes
the services run - only the transport differs. For demos, debugging and
tests; celery/redis remains the production path (parallelism, durability,
independent scaling).

usage:
    python -m tools.local_pipeline data/samples/work_orders.csv [...]
    python -m tools.local_pipeline --neo4j data/samples/*   (writes to live db)
"""

import asyncio
import hashlib

from plantmind_core.telemetry import get_logger

from plantmind_core.queues import DocKind

from ingestion.classify import Classifier
from extraction.imaging.extractor import ImageLane
from extraction.mail.extractor import EmailExtractor
from extraction.manual.extractor import ManualExtractor
from extraction.manual.pdfio import read_pdf_pages
from extraction.pnid.extractor import PnidExtractor
from extraction.text.extractor import TextExtractor
from extraction.workorder.parser import TableParser
from resolution.resolver import Resolver
from graphd.batching import group_batch

log = get_logger("tools.local_pipeline")


class GraphCollector:
    """Stand-in for GraphStore when no database is running: just keeps the
    batches so callers can inspect what WOULD have been written."""

    def __init__(self):
        self.batches = []

    def write_batch(self, batch, version):
        self.batches.append((batch, version))


class LocalPipeline:
    def __init__(self, llm=None, embedder=None, store=None):
        self.classifier = Classifier()
        self.resolver = Resolver()
        self.store = store or GraphCollector()
        self._seen_hashes = set()
        self._version = 0

        self._table = TableParser(llm)
        if llm and embedder:
            text = TextExtractor(llm, embedder)
            pnid = PnidExtractor(llm)
            self._lanes = {
                DocKind.TEXT: lambda d, h, n, b: text.extract(
                    d, h, n, b.decode("utf-8", errors="replace")),
                DocKind.PNID: pnid.extract,
                DocKind.MANUAL: lambda d, h, n, b: ManualExtractor(
                    llm, embedder).extract(d, h, n, read_pdf_pages(b)),
                DocKind.EMAIL: EmailExtractor(text).extract,
                DocKind.IMAGE: ImageLane(llm, embedder, pnid, text).extract,
            }
        else:
            self._lanes = {}   # tables still work; llm lanes need credentials

    async def ingest(self, filename: str, data: bytes) -> dict:
        content_hash = hashlib.sha256(data).hexdigest()
        if content_hash in self._seen_hashes:
            return {"status": "duplicate", "filename": filename}
        self._seen_hashes.add(content_hash)
        doc_id = content_hash[:16]

        sniff = data[:2048].decode("utf-8", errors="ignore")
        kind = self.classifier.classify(filename, sniff, data)

        if kind == DocKind.TABLE:
            csg = await self._table.parse(doc_id, content_hash, filename, data)
        elif kind in self._lanes:
            csg = await self._lanes[kind](doc_id, content_hash, filename, data)
        else:
            return {"status": "skipped", "filename": filename,
                    "reason": f"{kind.value} lane needs an LLM configured"}

        self.resolver.resolve(csg)
        batch = group_batch([csg])
        self._version += 1
        self.store.write_batch(batch, self._version)

        return {"status": "written", "filename": filename, "kind": kind.value,
                "doc_id": doc_id, "version": self._version,
                "nodes": len(batch.node_ids),
                "edges": sum(len(v) for v in batch.edges_by_type.values())}


def main():
    import sys

    from plantmind_core.config import get_settings
    from plantmind_core.devtools import find_file

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    use_neo4j = "--neo4j" in sys.argv

    llm = embedder = None
    if get_settings().openrouter_api_key:
        from plantmind_core.llm import get_embedder, get_llm
        llm, embedder = get_llm(), get_embedder()

    store = None
    if use_neo4j:
        from graphd.store import GraphStore
        store = GraphStore.from_settings()
        print(f"writing to {get_settings().neo4j_uri}")

    pipeline = LocalPipeline(llm, embedder, store)
    for arg in args:
        path = find_file(arg)
        result = asyncio.run(pipeline.ingest(path.name, path.read_bytes()))
        print(result)

    if isinstance(pipeline.store, GraphCollector):
        total_nodes = {id for b, _ in pipeline.store.batches for id in b.node_ids}
        print(f"\n(dry run - nothing persisted) unique nodes: {len(total_nodes)}, "
              f"batches: {len(pipeline.store.batches)}")


if __name__ == "__main__":
    main()

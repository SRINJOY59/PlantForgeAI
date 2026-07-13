import asyncio

from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.llm import get_embedder, get_llm
from plantmind_core.storage import ObjectStore
from plantmind_core.queues import Routes
from plantmind_core.telemetry import get_logger

from extraction.pnid.extractor import PnidExtractor
from extraction.text.extractor import TextExtractor
from extraction.workorder.parser import TableParser

log = get_logger("extraction.tasks")
settings = get_settings()

worker = WorkerApp("extraction")
celery_app = worker.app  # celery CLI entrypoint: celery -A extraction.tasks ...

_store = None
_table_parser = None
_text_extractor = None
_pnid_extractor = None


def _deps():
    global _store, _table_parser, _text_extractor, _pnid_extractor
    if _store is None:
        _store = ObjectStore.from_settings()
    if _table_parser is None:
        _table_parser = TableParser()
    if _text_extractor is None:
        _text_extractor = TextExtractor(get_llm(), get_embedder())
    if _pnid_extractor is None:
        _pnid_extractor = PnidExtractor(get_llm())
    return _store, _table_parser, _text_extractor, _pnid_extractor


@worker.task(Routes.parse_workorder)
def parse_workorder(payload: dict):
    store, parser, _, _ = _deps()
    return run_parse_workorder(payload, store, parser, sender=worker.send)


@worker.task(Routes.extract_text)
def extract_text(payload: dict):
    store, _, extractor, _ = _deps()
    return run_extract_text(payload, store, extractor, sender=worker.send)


@worker.task(Routes.extract_pnid)
def extract_pnid(payload: dict):
    store, _, _, extractor = _deps()
    return run_extract_pnid(payload, store, extractor, sender=worker.send)


def run_parse_workorder(payload: dict, store: ObjectStore, parser: TableParser,
                        sender) -> dict:
    """payload: {doc_id, object_key, filename, content_hash, source?}"""
    data = store.get(payload["object_key"])
    csg = parser.parse(payload["doc_id"], payload["content_hash"],
                       payload["filename"], data)

    sender(Routes.resolve, csg.model_dump(mode="json"))

    log.info("table parsed", doc_id=payload["doc_id"],
             filename=payload["filename"],
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "parsed", "doc_id": payload["doc_id"],
            "nodes": len(csg.nodes), "edges": len(csg.edges)}


def run_extract_text(payload: dict, store: ObjectStore,
                     extractor: TextExtractor, sender) -> dict:
    data = store.get(payload["object_key"])
    text = data.decode("utf-8", errors="replace")
    csg = asyncio.run(extractor.extract(payload["doc_id"],
                                        payload["content_hash"],
                                        payload["filename"], text))
    sender(Routes.resolve, csg.model_dump(mode="json"))
    log.info("text extracted", doc_id=payload["doc_id"],
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "doc_id": payload["doc_id"],
            "nodes": len(csg.nodes), "edges": len(csg.edges)}


def run_extract_pnid(payload: dict, store: ObjectStore,
                     extractor: PnidExtractor, sender) -> dict:
    data = store.get(payload["object_key"])
    csg = asyncio.run(extractor.extract(payload["doc_id"],
                                        payload["content_hash"],
                                        payload["filename"], data))
    sender(Routes.resolve, csg.model_dump(mode="json"))
    log.info("pnid extracted", doc_id=payload["doc_id"],
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "doc_id": payload["doc_id"],
            "nodes": len(csg.nodes), "edges": len(csg.edges)}

import asyncio

from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.llm import get_embedder, get_llm
from plantmind_core.storage import ObjectStore
from plantmind_core.queues import Routes
from plantmind_core.telemetry import get_logger

from extraction.imaging.extractor import ImageLane
from extraction.mail.extractor import EmailExtractor
from extraction.manual.extractor import ManualExtractor
from extraction.manual.pdfio import read_pdf_pages
from extraction.pnid.extractor import PnidExtractor
from extraction.text.extractor import TextExtractor
from extraction.workorder.parser import TableParser

log = get_logger("extraction.tasks")
settings = get_settings()

worker = WorkerApp("extraction")
celery_app = worker.app  # celery CLI entrypoint: celery -A extraction.tasks ...

_lanes = None


class Lanes:
    """One instance of every extractor, built lazily per worker process."""

    def __init__(self):
        self.store = ObjectStore.from_settings()
        llm, embedder = get_llm(), get_embedder()
        self.table = TableParser(llm)
        self.text = TextExtractor(llm, embedder)
        self.pnid = PnidExtractor(llm)
        self.manual = ManualExtractor(llm, embedder)
        self.email = EmailExtractor(self.text)
        self.image = ImageLane(llm, embedder, self.pnid, self.text)


def _deps() -> Lanes:
    global _lanes
    if _lanes is None:
        _lanes = Lanes()
    return _lanes


@worker.task(Routes.parse_workorder)
def parse_workorder(payload: dict):
    lanes = _deps()
    return run_parse_workorder(payload, lanes.store, lanes.table,
                               sender=worker.send)


@worker.task(Routes.extract_text)
def extract_text(payload: dict):
    lanes = _deps()
    return run_extract_text(payload, lanes.store, lanes.text,
                            sender=worker.send)


@worker.task(Routes.extract_pnid)
def extract_pnid(payload: dict):
    lanes = _deps()
    return run_extract_pnid(payload, lanes.store, lanes.pnid,
                            sender=worker.send)


@worker.task(Routes.extract_manual)
def extract_manual(payload: dict):
    lanes = _deps()
    return run_extract_manual(payload, lanes.store, lanes.manual,
                              sender=worker.send)


@worker.task(Routes.extract_email)
def extract_email(payload: dict):
    lanes = _deps()
    return run_bytes_lane(payload, lanes.store, lanes.email,
                          sender=worker.send)


@worker.task(Routes.extract_image)
def extract_image(payload: dict):
    lanes = _deps()
    return run_bytes_lane(payload, lanes.store, lanes.image,
                          sender=worker.send)


def run_parse_workorder(payload: dict, store: ObjectStore, parser: TableParser,
                        sender) -> dict:
    """payload: {doc_id, object_key, filename, content_hash, source?}"""
    data = store.get(payload["object_key"])
    csg = asyncio.run(parser.parse(payload["doc_id"], payload["content_hash"],
                                   payload["filename"], data))

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


def run_extract_manual(payload: dict, store: ObjectStore,
                       extractor: ManualExtractor, sender) -> dict:
    data = store.get(payload["object_key"])
    pages = read_pdf_pages(data)
    csg = asyncio.run(extractor.extract(payload["doc_id"],
                                        payload["content_hash"],
                                        payload["filename"], pages))
    sender(Routes.resolve, csg.model_dump(mode="json"))
    log.info("manual extracted", doc_id=payload["doc_id"], pages=len(pages),
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "doc_id": payload["doc_id"],
            "nodes": len(csg.nodes), "edges": len(csg.edges)}


def run_bytes_lane(payload: dict, store: ObjectStore, extractor, sender) -> dict:
    """Email and image lanes share a shape: raw bytes in, subgraph out."""
    data = store.get(payload["object_key"])
    csg = asyncio.run(extractor.extract(payload["doc_id"],
                                        payload["content_hash"],
                                        payload["filename"], data))
    sender(Routes.resolve, csg.model_dump(mode="json"))
    log.info("lane extracted", doc_id=payload["doc_id"],
             lane=type(extractor).__name__,
             nodes=len(csg.nodes), edges=len(csg.edges))
    return {"status": "extracted", "doc_id": payload["doc_id"],
            "nodes": len(csg.nodes), "edges": len(csg.edges)}

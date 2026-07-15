import asyncio

from plantmind_core.bus import RedisBus
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.llm import Tier, get_llm
from plantmind_core.queues import DocKind, Flow
from plantmind_core.storage import ObjectStore

from ingestion.classify import Classifier
from ingestion.service import IngestionService

worker = WorkerApp("ingestion")
celery_app = worker.app  # celery CLI entrypoint: celery -A ingestion.tasks ...

_service = None


def _llm_classify(filename: str, sniff: str) -> str:
    prompt = (
        "Classify this industrial document as exactly one of: table, pnid, "
        "text, manual, email, image.\n"
        "table = structured rows (work orders, inspections). pnid = engineering "
        "drawing. text = short prose. manual = long structured handbook. "
        f"image = photo/scan/chart.\n\nFilename: {filename}\n"
        f"First bytes:\n{sniff[:800]}\n\nAnswer with the single word only."
    )
    reply = asyncio.run(get_llm().complete(
        [{"role": "user", "content": prompt}], tier=Tier.CHEAP, max_tokens=5))
    return reply.strip().lower()


def _instance() -> IngestionService:
    global _service
    if _service is None:
        _service = IngestionService(
            store=ObjectStore.from_settings(),
            bus=RedisBus.from_settings(),
            classifier=Classifier(llm_fallback=_llm_classify),
        )
    return _service


@worker.task(Flow.ingest)
def classify_document(payload: dict):
    result = _instance().classify_document(payload)
    if result["status"] == "classified":
        route = Flow.extraction_for[DocKind(result["kind"])]
        worker.send(route, result.pop("next_payload"))
        result["queue"] = route.queue
    return result

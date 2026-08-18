from plantmind_core.aio import run_sync
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
    # run_sync, not asyncio.run: this process handles many tasks and the
    # clients it awaits are per-worker singletons. asyncio.run closes the loop
    # it made, so the second task in a worker meets a dead connection pool and
    # a semaphore bound to a loop that no longer exists. See plantmind_core.aio.
    reply = run_sync(get_llm().complete(
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

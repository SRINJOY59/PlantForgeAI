from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.queues import Routes

from graphd.writer import GraphWriter

worker = WorkerApp("graphd")
worker.schedule(Routes.flush,
                every_seconds=get_settings().write_flush_interval_s)
# denoise gets scheduled here once implemented

celery_app = worker.app  # celery CLI entrypoint: celery -A graphd.tasks ...

_writer = None


def _instance() -> GraphWriter:
    global _writer
    if _writer is None:
        _writer = GraphWriter.from_settings()
    return _writer


@worker.task(Routes.flush)
def flush_write_buffer():
    return _instance().flush()

from plantmind_core.aio import run_sync
from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.queues import Routes

from graphd.denoise.runner import DenoiseRunner
from graphd.writer import GraphWriter

settings = get_settings()
worker = WorkerApp("graphd")
worker.schedule(Routes.flush, every_seconds=settings.write_flush_interval_s)
worker.schedule(Routes.denoise, every_seconds=settings.denoise_interval_s)

celery_app = worker.app  # celery CLI entrypoint: celery -A graphd.tasks ...

_writer = None
_denoise = None


def _writer_instance() -> GraphWriter:
    global _writer
    if _writer is None:
        _writer = GraphWriter.from_settings()
    return _writer


def _denoise_instance() -> DenoiseRunner:
    global _denoise
    if _denoise is None:
        _denoise = DenoiseRunner.from_settings()
    return _denoise


@worker.task(Routes.flush)
def flush_write_buffer():
    return _writer_instance().flush()


@worker.task(Routes.denoise)
def run_denoise():
    # run_sync, not asyncio.run: this process handles many tasks and the
    # clients it awaits are per-worker singletons. asyncio.run closes the loop
    # it made, so the second task in a worker meets a dead connection pool and
    # a semaphore bound to a loop that no longer exists. See plantmind_core.aio.
    return run_sync(_denoise_instance().run())

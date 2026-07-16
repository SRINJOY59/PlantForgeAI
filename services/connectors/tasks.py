from plantmind_core.celeryapp import WorkerApp
from plantmind_core.config import get_settings
from plantmind_core.queues import Routes

from connectors.registry import load_connectors
from connectors.runner import ConnectorSync

settings = get_settings()
worker = WorkerApp("connectors")
worker.schedule(Routes.sync_connectors,
                every_seconds=settings.connector_sync_interval_s)

celery_app = worker.app  # celery CLI entrypoint: celery -A connectors.tasks ...

_sync = None
_connectors = None


def _deps():
    global _sync, _connectors
    if _sync is None:
        _sync = ConnectorSync.from_settings()
        _connectors = load_connectors(settings.connectors_config)
    return _sync, _connectors


@worker.task(Routes.sync_connectors)
def sync_all():
    sync, connectors = _deps()
    return sync.sync_all(connectors)


def main():
    """One sync pass now. usage: python -m connectors.tasks"""
    sync, connectors = _deps()
    print(sync.sync_all(connectors))


if __name__ == "__main__":
    main()

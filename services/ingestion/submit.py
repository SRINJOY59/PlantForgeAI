"""Uploader used by the gateway later and by hand today:

    python -m ingestion.submit data/samples/work_orders.csv [...]

Puts each file at a staging key and enqueues classification."""

import sys
import uuid
from pathlib import Path

from plantmind_core.queues import Routes

from plantmind_core.storage import ObjectStore


def submit_file(path: Path, store: ObjectStore, sender, source=None) -> str:
    staging_key = f"staging/{uuid.uuid4().hex}/{path.name}"
    store.put(staging_key, path.read_bytes())
    sender(Routes.classify, {
        "staging_key": staging_key,
        "filename": path.name,
        "source": source,
    })
    return staging_key


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    from ingestion.tasks import worker
    store = ObjectStore.from_settings()
    for arg in sys.argv[1:]:
        path = Path(arg)
        key = submit_file(path, store, worker.send, source="cli")
        print(f"submitted {path.name} -> {key}")


if __name__ == "__main__":
    main()

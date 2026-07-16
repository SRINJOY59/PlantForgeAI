"""Runs a connector: pull items newer than the stored cursor, submit each
into the pipeline, advance the cursor. Idempotent by construction - the
cursor skips seen files and the hash gate catches anything that slips."""

from plantmind_core.pipeline import stage_and_enqueue
from plantmind_core.telemetry import get_logger

log = get_logger("connectors.runner")


class ConnectorSync:
    def __init__(self, store, sender, cursors):
        self._store = store
        self._sender = sender
        self._cursors = cursors      # get_cursor(name) / set_cursor(name, val)

    @classmethod
    def from_settings(cls) -> "ConnectorSync":
        from plantmind_core.bus import RedisBus
        from plantmind_core.celeryapp import WorkerApp
        from plantmind_core.storage import ObjectStore

        bus = RedisBus.from_settings()
        return cls(ObjectStore.from_settings(),
                   WorkerApp("connectors").send, bus)

    def sync(self, connector) -> dict:
        name = f"connector:{connector.id}"
        since = self._cursors.get_cursor(name)
        count, last = 0, since
        for item in connector.fetch(since):
            stage_and_enqueue(self._store, self._sender, item.filename,
                              item.data, source=connector.id)
            last = item.marker
            count += 1
        if last and last != since:
            self._cursors.set_cursor(name, last)
        if count:
            log.info("connector synced", connector=connector.id, ingested=count)
        return {"connector": connector.id, "ingested": count, "cursor": last}

    def sync_all(self, connectors) -> list:
        return [self.sync(c) for c in connectors]

from plantmind_core.queues import Flow

from connectors.base import Connector, SyncItem
from connectors.runner import ConnectorSync
from conftest import FakeCursors, FakeSender, FakeStore


class ListConnector(Connector):
    """Yields a fixed set of items with markers > since."""
    def __init__(self, id, items):
        super().__init__(id)
        self._items = items

    def fetch(self, since):
        for item in self._items:
            if item.marker > (since or "0"):
                yield item


def runner():
    return ConnectorSync(FakeStore(), FakeSender(), FakeCursors()),


def test_sync_submits_each_item_and_advances_cursor():
    store, sender, cursors = FakeStore(), FakeSender(), FakeCursors()
    sync = ConnectorSync(store, sender, cursors)
    conn = ListConnector("inbox", [
        SyncItem("a.csv", b"1", "100"), SyncItem("b.csv", b"2", "200")])

    result = sync.sync(conn)

    assert result["ingested"] == 2
    assert len(sender.sent) == 2
    route, payload = sender.sent[0]
    assert route is Flow.ingest
    assert payload["source"] == "inbox"
    assert payload["filename"] == "a.csv"
    assert len(store.objects) == 2
    assert cursors.get_cursor("connector:inbox") == "200"     # newest marker


def test_second_sync_skips_already_seen():
    store, sender, cursors = FakeStore(), FakeSender(), FakeCursors()
    sync = ConnectorSync(store, sender, cursors)
    items = [SyncItem("a.csv", b"1", "100"), SyncItem("b.csv", b"2", "200")]

    sync.sync(ListConnector("inbox", items))
    # a third file arrives later
    items.append(SyncItem("c.csv", b"3", "300"))
    result = sync.sync(ListConnector("inbox", items))

    assert result["ingested"] == 1                            # only the new one
    assert sender.sent[-1][1]["filename"] == "c.csv"
    assert cursors.get_cursor("connector:inbox") == "300"


def test_empty_sync_leaves_cursor_untouched():
    cursors = FakeCursors()
    cursors.set_cursor("connector:inbox", "500")
    sync = ConnectorSync(FakeStore(), FakeSender(), cursors)

    result = sync.sync(ListConnector("inbox", []))

    assert result["ingested"] == 0
    assert cursors.get_cursor("connector:inbox") == "500"


def test_sync_all_runs_every_connector():
    sync = ConnectorSync(FakeStore(), FakeSender(), FakeCursors())
    results = sync.sync_all([
        ListConnector("a", [SyncItem("x", b"1", "1")]),
        ListConnector("b", [SyncItem("y", b"2", "1")])])

    assert {r["connector"] for r in results} == {"a", "b"}

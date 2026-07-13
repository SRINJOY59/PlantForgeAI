import hashlib

import fakeredis
import pytest

from plantmind_core.bus import RedisBus
from plantmind_core.queues import Routes

from ingestion.classify import Classifier
from ingestion.tasks import run_classify
from conftest import FakeObjectStore, FakeSender

CSV = b"wo_id,date,equipment_tag\nWO-1,2026-01-01,P-101A\n"


@pytest.fixture
def env():
    store = FakeObjectStore()
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    sender = FakeSender()
    return store, bus, sender


def submit(store, filename=b"work_orders.csv", data=CSV):
    key = f"staging/abc/{filename.decode()}"
    store.put(key, data)
    return {"staging_key": key, "filename": filename.decode(), "source": "test"}


def test_new_document_promoted_and_routed(env):
    store, bus, sender = env
    payload = submit(store)

    result = run_classify(payload, store, bus, Classifier(), sender)

    assert result["status"] == "queued"
    assert result["queue"] == "q_parse_wo"

    doc_id = hashlib.sha256(CSV).hexdigest()[:16]
    object_key = f"raw/{doc_id}/work_orders.csv"
    assert object_key in store.objects              # promoted out of staging
    assert not any(k.startswith("staging/") for k in store.objects)

    route, args, _ = sender.sent[0]
    assert route is Routes.parse_workorder
    assert args[0]["doc_id"] == doc_id
    assert args[0]["object_key"] == object_key
    assert args[0]["content_hash"] == hashlib.sha256(CSV).hexdigest()


def test_duplicate_dropped_and_staging_cleaned(env):
    store, bus, sender = env
    run_classify(submit(store), store, bus, Classifier(), sender)

    result = run_classify(submit(store), store, bus, Classifier(), sender)

    assert result["status"] == "duplicate"
    assert len(sender.sent) == 1                    # only the first got routed
    assert not any(k.startswith("staging/") for k in store.objects)


def test_same_content_different_filename_is_still_duplicate(env):
    store, bus, sender = env
    run_classify(submit(store), store, bus, Classifier(), sender)

    result = run_classify(submit(store, filename=b"copy_of_export.csv"),
                          store, bus, Classifier(), sender)

    assert result["status"] == "duplicate"


def test_failure_after_claim_releases_the_hash(env):
    store, bus, sender = env

    class ExplodingStore(FakeObjectStore):
        def move(self, src, dst):
            raise ConnectionError("minio gone")

    bad_store = ExplodingStore()
    payload = submit(bad_store)

    with pytest.raises(ConnectionError):
        run_classify(payload, bad_store, bus, Classifier(), sender)

    # the claim was rolled back, so a retry can succeed
    content_hash = hashlib.sha256(CSV).hexdigest()
    assert bus.claim_document(content_hash) is True


def test_svg_routes_to_pnid_queue(env):
    store, bus, sender = env
    payload = submit(store, filename=b"pnid_unit100.svg", data=b"<svg></svg>")

    result = run_classify(payload, store, bus, Classifier(), sender)

    assert result["queue"] == "q_extract_pnid"
    assert sender.sent[0][0] is Routes.extract_pnid


def test_document_claim_is_first_writer_wins():
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    assert bus.claim_document("abc") is True
    assert bus.claim_document("abc") is False
    bus.release_document("abc")
    assert bus.claim_document("abc") is True

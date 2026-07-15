import hashlib

import fakeredis
import pytest

from plantmind_core.bus import RedisBus
from plantmind_core.queues import DocKind, Flow

from ingestion.classify import Classifier
from ingestion.service import IngestionService
from conftest import FakeObjectStore

CSV = b"wo_id,date,equipment_tag\nWO-1,2026-01-01,P-101A\n"


@pytest.fixture
def env():
    store = FakeObjectStore()
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    return store, bus, IngestionService(store, bus, Classifier())


def submit(store, filename="work_orders.csv", data=CSV):
    key = f"staging/abc/{filename}"
    store.put(key, data)
    return {"staging_key": key, "filename": filename, "source": "test"}


def test_new_document_promoted_and_classified(env):
    store, bus, service = env

    result = service.classify_document(submit(store))

    assert result["status"] == "classified"
    assert result["kind"] == "table"

    doc_id = hashlib.sha256(CSV).hexdigest()[:16]
    object_key = f"raw/{doc_id}/work_orders.csv"
    assert object_key in store.objects              # promoted out of staging
    assert not any(k.startswith("staging/") for k in store.objects)

    nxt = result["next_payload"]
    assert nxt["doc_id"] == doc_id
    assert nxt["object_key"] == object_key
    assert nxt["content_hash"] == hashlib.sha256(CSV).hexdigest()
    # the adapter routes this via the central topology:
    assert Flow.extraction_for[DocKind(result["kind"])].queue == "q_parse_wo"


def test_duplicate_dropped_and_staging_cleaned(env):
    store, bus, service = env
    service.classify_document(submit(store))

    result = service.classify_document(submit(store))

    assert result["status"] == "duplicate"
    assert "next_payload" not in result             # nothing to route
    assert not any(k.startswith("staging/") for k in store.objects)


def test_same_content_different_filename_is_still_duplicate(env):
    store, bus, service = env
    service.classify_document(submit(store))

    result = service.classify_document(
        submit(store, filename="copy_of_export.csv"))

    assert result["status"] == "duplicate"


def test_failure_after_claim_releases_the_hash(env):
    _, bus, _ = env

    class ExplodingStore(FakeObjectStore):
        def move(self, src, dst):
            raise ConnectionError("minio gone")

    bad_store = ExplodingStore()
    service = IngestionService(bad_store, bus, Classifier())

    with pytest.raises(ConnectionError):
        service.classify_document(submit(bad_store))

    # the claim was rolled back, so a retry can succeed
    assert bus.claim_document(hashlib.sha256(CSV).hexdigest()) is True


def test_svg_classified_for_the_pnid_lane(env):
    store, bus, service = env

    result = service.classify_document(
        submit(store, filename="pnid_unit100.svg", data=b"<svg></svg>"))

    assert result["kind"] == "pnid"
    assert Flow.extraction_for[DocKind.PNID].queue == "q_extract_pnid"


def test_document_claim_is_first_writer_wins():
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    assert bus.claim_document("abc") is True
    assert bus.claim_document("abc") is False
    bus.release_document("abc")
    assert bus.claim_document("abc") is True

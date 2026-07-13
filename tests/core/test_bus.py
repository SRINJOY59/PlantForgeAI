import fakeredis
import pytest

from plantmind_core import keys
from plantmind_core.bus import RedisBus


@pytest.fixture
def bus():
    return RedisBus(fakeredis.FakeRedis(decode_responses=True))


def test_subgraph_buffer_is_fifo(bus):
    bus.queue_subgraph("first")
    bus.queue_subgraph("second")
    bus.queue_subgraph("third")

    assert bus.take_subgraphs(2) == ["first", "second"]
    assert bus.take_subgraphs(2) == ["third"]
    assert bus.take_subgraphs(2) == []


def test_flush_lock_single_flight(bus):
    assert bus.acquire_flush_lock() is True
    assert bus.acquire_flush_lock() is False
    bus.release_flush_lock()
    assert bus.acquire_flush_lock() is True


def test_graph_version_is_monotonic(bus):
    assert bus.next_graph_version() == 1
    assert bus.next_graph_version() == 2
    assert bus.next_graph_version() == 3


def test_delta_stream_appends(bus):
    bus.publish_delta('{"graph_version": 1}')
    bus.publish_delta('{"graph_version": 2}')

    entries = bus._r.xrange(keys.DELTA_STREAM)
    assert len(entries) == 2
    assert entries[0][1]["payload"] == '{"graph_version": 1}'


def test_parked_subgraphs_kept_separate_from_buffer(bus):
    bus.queue_subgraph("good")
    bus.park_bad_subgraph("bad")

    assert bus.take_subgraphs(10) == ["good"]
    assert bus._r.lrange(keys.WRITE_DLQ, 0, -1) == ["bad"]

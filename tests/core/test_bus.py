import fakeredis
import pytest

from plantmind_core import keys
from plantmind_core.bus import RedisBus
from plantmind_core.bus.redis_bus import MAX_BLOCK_MS, SOCKET_TIMEOUT_S


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


def test_socket_outlasts_the_longest_block():
    # the ordering that matters: a socket timeout inside the block hangs up on
    # redis mid-wait and raises while redis is behaving perfectly
    assert SOCKET_TIMEOUT_S * 1000 > MAX_BLOCK_MS


def test_the_client_sets_its_own_socket_timeout(monkeypatch):
    """The bug this pins: the client used to inherit redis-py's default, which
    was None on <=5 and 5s on 8.0 - shorter than our 15s block. A rebuild that
    resolved a newer redis turned every idle read into a crash."""
    captured = {}

    def fake_from_url(url, **kwargs):
        captured.update(kwargs)
        return fakeredis.FakeRedis(decode_responses=True)

    monkeypatch.setattr("plantmind_core.bus.redis_bus.redis.Redis.from_url",
                        fake_from_url)
    RedisBus.from_settings()

    assert captured["socket_timeout"] == SOCKET_TIMEOUT_S
    assert captured["socket_timeout"] * 1000 > MAX_BLOCK_MS


def test_a_block_longer_than_the_socket_is_refused_not_attempted(bus):
    with pytest.raises(ValueError, match="exceeds MAX_BLOCK_MS"):
        bus.read_deltas("0", MAX_BLOCK_MS + 1)


def test_blocks_up_to_the_maximum_are_passed_through(bus):
    # both production callers sit exactly on the limit, so the guard must not
    # be off-by-one against them. Records the call rather than making it -
    # fakeredis honours BLOCK, and a real 15s wait here would be 15s of suite.
    seen = {}
    bus._r.xread = lambda streams, **kw: seen.update(streams=streams, **kw) or []

    assert bus.read_deltas("$", MAX_BLOCK_MS) == []
    assert seen["block"] == MAX_BLOCK_MS

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


def test_rate_check_allows_up_to_the_limit_then_blocks(bus):
    allowed = [bus.rate_check("ask:u1", limit=3, window_s=60)[0] for _ in range(5)]
    assert allowed == [True, True, True, False, False]


def test_rate_check_reports_a_retry_after_once_blocked(bus):
    for _ in range(2):
        bus.rate_check("ask:u1", limit=2, window_s=60)
    allowed, retry = bus.rate_check("ask:u1", limit=2, window_s=60)
    assert allowed is False
    assert 0 < retry <= 60


def test_rate_check_is_per_bucket(bus):
    for _ in range(3):
        bus.rate_check("ask:u1", limit=3, window_s=60)
    # a different user, and a different endpoint, each get their own budget
    assert bus.rate_check("ask:u2", limit=3, window_s=60)[0] is True
    assert bus.rate_check("moc:u1", limit=3, window_s=60)[0] is True


def test_socket_outlasts_the_longest_block():
    # the ordering that matters: a socket timeout inside the block hangs up on
    # redis mid-wait and raises while redis is behaving perfectly
    assert SOCKET_TIMEOUT_S * 1000 > MAX_BLOCK_MS


# -- the async stream tail (SSE fan-out) --------------------------------------
def async_bus():
    import fakeredis.aioredis
    return RedisBus(fakeredis.FakeRedis(decode_responses=True),
                    async_client=fakeredis.aioredis.FakeRedis(
                        decode_responses=True))


async def test_read_alerts_async_returns_published_alerts():
    bus = async_bus()
    # publish through the ASYNC client: fakeredis sync/async instances don't
    # share state, and the reader under test is the async one
    await bus._ar.xadd(keys.ALERT_STREAM, {"payload": '{"title": "a1"}'})
    await bus._ar.xadd(keys.ALERT_STREAM, {"payload": '{"title": "a2"}'})

    entries = await bus.read_alerts_async("0", block_ms=0)
    assert [p for _, p in entries] == ['{"title": "a1"}', '{"title": "a2"}']
    # ids come back so an SSE client can resume from the last one it saw
    assert all(entry_id for entry_id, _ in entries)


async def test_read_alerts_async_enforces_the_same_block_ceiling():
    # the socket-vs-block invariant protects the async client identically
    bus = async_bus()
    with pytest.raises(ValueError, match="exceeds MAX_BLOCK_MS"):
        await bus.read_alerts_async("0", MAX_BLOCK_MS + 1)


def test_async_client_is_lazy_so_workers_never_build_one():
    # celery workers and the agents consumer are sync-only; constructing the
    # bus must not create (or require an event loop for) an async client
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    assert bus._ar is None


def test_lazily_built_async_client_sets_its_own_socket_timeout(monkeypatch):
    """Same trap as the sync client: redis-py 8's default socket timeout is
    shorter than our 15s block, so the lazy constructor must pass it
    explicitly or every idle SSE read dies mid-block."""
    import redis.asyncio
    captured = {}

    def fake_from_url(url, **kwargs):
        captured.update(kwargs)
        import fakeredis.aioredis
        return fakeredis.aioredis.FakeRedis(decode_responses=True)

    monkeypatch.setattr(redis.asyncio.Redis, "from_url", fake_from_url)
    bus = RedisBus(fakeredis.FakeRedis(decode_responses=True))
    bus._async()

    assert captured["socket_timeout"] == SOCKET_TIMEOUT_S
    assert captured["socket_timeout"] * 1000 > MAX_BLOCK_MS


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

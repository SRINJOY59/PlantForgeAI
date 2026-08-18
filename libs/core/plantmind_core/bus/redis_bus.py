"""All coordination state — dedup ledger, write buffer, DLQ, locks, the
graph version counter and the delta stream — lives behind this class.
Services talk to the bus in domain terms; raw redis commands and key names
stay in here and keys.py."""

import json
import time

import redis

from plantmind_core import keys
from plantmind_core.config import get_settings

# The longest a caller may park on a blocking stream read, and the socket
# timeout that has to outlast it.
#
# These two are a pair, and the ordering between them is load-bearing: a
# blocking XREAD holds the socket idle for the whole block, so a socket timeout
# shorter than the block hangs up on redis mid-wait and raises TimeoutError
# while redis is behaving perfectly. Never let SOCKET_TIMEOUT_S drop below
# MAX_BLOCK_MS; raise them together.
#
# It is set explicitly rather than left to the client's default because that
# default is not ours to rely on - redis-py <=5 used None (wait forever) and 8.0
# changed it to 5s, which silently inverted this ordering on the next rebuild.
MAX_BLOCK_MS = 15000
SOCKET_TIMEOUT_S = MAX_BLOCK_MS / 1000 + 5


class RedisBus:
    def __init__(self, client, async_client=None):
        self._r = client
        # created lazily: only long-lived stream tails (the gateway's SSE
        # fan-out) need it, and the celery workers must not pay for a client
        # they never use - nor require a running event loop to construct one
        self._ar = async_client

    @classmethod
    def from_settings(cls) -> "RedisBus":
        s = get_settings()
        return cls(redis.Redis.from_url(s.redis_url, decode_responses=True,
                                        socket_timeout=SOCKET_TIMEOUT_S))

    def _async(self):
        if self._ar is None:
            import redis.asyncio
            s = get_settings()
            # same socket-timeout invariant as the sync client, for the same
            # reason: the async client's default would hang up mid-block too
            self._ar = redis.asyncio.Redis.from_url(
                s.redis_url, decode_responses=True,
                socket_timeout=SOCKET_TIMEOUT_S)
        return self._ar

    # document dedup ledger -------------------------------------------------
    def claim_document(self, content_hash: str) -> bool:
        """First caller wins; atomic, so concurrent ingests of the same
        content can't both pass."""
        return bool(self._r.set(keys.DOC_HASH_PREFIX + content_hash, "1", nx=True))

    def release_document(self, content_hash: str):
        """Undo a claim when processing fails after the gate — otherwise a
        crashed ingest would block that file forever."""
        self._r.delete(keys.DOC_HASH_PREFIX + content_hash)

    # extraction deduplication & idempotency --------------------------------
    def acquire_extraction_lock(self, content_hash: str, lane: str,
                                ttl_seconds: int = 300) -> bool:
        """Single-flight lock per (lane, content_hash) so concurrent tasks
        don't run duplicate expensive OCR/VLM inference."""
        key = f"{keys.EXTRACTION_LOCK_PREFIX}{lane}:{content_hash}"
        return bool(self._r.set(key, "1", nx=True, ex=ttl_seconds))

    def release_extraction_lock(self, content_hash: str, lane: str):
        key = f"{keys.EXTRACTION_LOCK_PREFIX}{lane}:{content_hash}"
        self._r.delete(key)

    def get_cached_extraction(self, content_hash: str, lane: str) -> str | None:
        """Return serialized CandidateSubgraph JSON if previously extracted."""
        key = f"{keys.EXTRACTION_CACHE_PREFIX}{lane}:{content_hash}"
        return self._r.get(key)

    def set_cached_extraction(self, content_hash: str, lane: str, csg_json: str,
                               ttl_seconds: int = 604800):
        """Cache CandidateSubgraph JSON with a default 7-day TTL."""
        key = f"{keys.EXTRACTION_CACHE_PREFIX}{lane}:{content_hash}"
        self._r.set(key, csg_json, ex=ttl_seconds)

    # write buffer + quarantine ---------------------------------------------
    def queue_subgraph(self, payload_json: str):
        self._r.rpush(keys.WRITE_BUFFER, payload_json)

    def take_subgraphs(self, count: int) -> list:
        return self._r.lpop(keys.WRITE_BUFFER, count) or []

    def park_bad_subgraph(self, payload_json: str):
        self._r.rpush(keys.WRITE_DLQ, payload_json)

    # single-flight lock for the writer --------------------------------------
    def acquire_flush_lock(self, ttl_seconds: int = 60) -> bool:
        return bool(self._r.set(keys.FLUSH_LOCK, "1", nx=True, ex=ttl_seconds))

    def release_flush_lock(self):
        self._r.delete(keys.FLUSH_LOCK)

    # graph version + change announcements ----------------------------------
    def next_graph_version(self) -> int:
        return self._r.incr(keys.GRAPH_VERSION)

    def publish_delta(self, delta_json: str):
        self._r.xadd(keys.DELTA_STREAM, {"payload": delta_json})

    # streams: deltas consumed by agents, alerts produced by them -------------
    def read_deltas(self, after_id: str = "0", block_ms: int = 15000) -> list:
        """-> [(entry_id, payload_json)] newer than after_id; blocks up to
        block_ms so the consumer waits instead of polling."""
        return self._read_stream(keys.DELTA_STREAM, after_id, block_ms)

    def publish_alert(self, alert_json: str) -> str:
        return self._r.xadd(keys.ALERT_STREAM, {"payload": alert_json})

    def read_alerts(self, after_id: str = "0", block_ms: int = 15000) -> list:
        return self._read_stream(keys.ALERT_STREAM, after_id, block_ms)

    async def read_alerts_async(self, after_id: str = "0",
                                block_ms: int = 15000) -> list:
        """read_alerts for callers living on an event loop - the SSE fan-out.

        Awaited, not wrapped in to_thread: an SSE connection spends its life
        parked on this block, and a thread-per-connection hold is exactly how
        a few dozen open Alerts tabs ate the pool that the query path's real
        work runs on. Parked awaits cost nothing; parked threads cost the
        platform."""
        self._check_block(block_ms)
        kwargs = {"block": block_ms} if block_ms else {}
        reply = await self._async().xread({keys.ALERT_STREAM: after_id},
                                          **kwargs)
        return self._entries(reply)

    def publish_draft_work_order(self, payload_json: str) -> str:
        return self._r.xadd(keys.DRAFT_WORK_ORDERS_STREAM, {"payload": payload_json})

    def read_draft_work_orders(self, after_id: str = "0", block_ms: int = 15000) -> list:
        return self._read_stream(keys.DRAFT_WORK_ORDERS_STREAM, after_id, block_ms)

    async def read_draft_work_orders_async(self, after_id: str = "0",
                                           block_ms: int = 15000) -> list:
        self._check_block(block_ms)
        kwargs = {"block": block_ms} if block_ms else {}
        reply = await self._async().xread({keys.DRAFT_WORK_ORDERS_STREAM: after_id},
                                          **kwargs)
        return self._entries(reply)

    # --- work-order decisions -------------------------------------------
    # Kept in a hash beside the stream rather than inside it: a stream entry
    # is immutable, and the draft genuinely is - it is what the agent produced
    # at a given graph version. Who approved it is a later, separate fact, so
    # it is recorded separately and merged when the drafts are read back.

    def set_work_order_decision(self, draft_id: str, decision: str, who: str):
        self._r.hset(keys.WORK_ORDER_DECISIONS, draft_id,
                     json.dumps({"decision": decision, "by": who,
                                 "at": time.time()}))

    def work_order_decisions(self) -> dict:
        raw = self._r.hgetall(keys.WORK_ORDER_DECISIONS) or {}
        out = {}
        for k, v in raw.items():
            try:
                out[k] = json.loads(v)
            except (ValueError, TypeError):
                continue
        return out

    def _read_stream(self, stream, after_id, block_ms) -> list:
        # block_ms > 0 waits; 0/None returns immediately. (Raw redis treats
        # BLOCK 0 as block-forever - we don't want that footgun.)
        self._check_block(block_ms)
        kwargs = {"block": block_ms} if block_ms else {}
        reply = self._r.xread({stream: after_id}, **kwargs)
        return self._entries(reply)

    @staticmethod
    def _check_block(block_ms):
        if block_ms and block_ms > MAX_BLOCK_MS:
            # refuse rather than let the socket time out mid-block and report a
            # dead redis that is in fact fine
            raise ValueError(
                f"block_ms={block_ms} exceeds MAX_BLOCK_MS={MAX_BLOCK_MS}; the "
                f"socket would time out at {SOCKET_TIMEOUT_S}s while redis is "
                f"still waiting. Raise both together.")

    @staticmethod
    def _entries(reply) -> list:
        if not reply:
            return []
        return [(entry_id, fields["payload"])
                for _, entries in reply for entry_id, fields in entries]

    def get_cursor(self, name: str) -> str:
        return self._r.get(keys.CURSOR_PREFIX + name) or "0"

    def set_cursor(self, name: str, entry_id: str):
        self._r.set(keys.CURSOR_PREFIX + name, entry_id)

    def claim_alert(self, fingerprint: str, ttl_seconds: int | None = None) -> bool:
        """First caller wins - one alert per distinct fact, so re-processing
        a delta or re-ingesting a file doesn't re-raise the same alert.

        ttl_seconds re-opens the claim after a while, and exists because
        "one alert per fact, forever" is only right for facts that happen once.
        A delta arriving twice is the same event and must not alarm twice. An
        inspection that is overdue is not an event at all - it is a condition,
        still true tomorrow - and a permanent claim means the plant is told
        about it exactly once, on whichever sweep first saw it, and then never
        again for the life of the redis volume. That is how a standing
        compliance breach goes quiet.

        A TTL'd claim needs its own key rather than a set member: redis expires
        keys, not elements, so the fingerprints that should lapse cannot live
        in ALERTED_SET. The untimed path is unchanged and still uses the set.
        """
        if ttl_seconds is None:
            return bool(self._r.sadd(keys.ALERTED_SET, fingerprint))
        key = f"{keys.ALERTED_SET}:{fingerprint}"
        return bool(self._r.set(key, "1", nx=True, ex=ttl_seconds))

    # rate limiting -----------------------------------------------------------
    def rate_check(self, bucket: str, limit: int, window_s: int):
        """Fixed-window counter -> (allowed, retry_after_s). First hit in a
        window sets the TTL, so the window is the first request's window and the
        key expires on its own - no sweep, no unbounded growth.

        Fixed window, not a token bucket: a caller can burst up to 2x the limit
        across a boundary, which for cost control on an LLM endpoint is a fine
        trade for a counter this cheap and this hard to get wrong."""
        key = keys.RATE_PREFIX + bucket
        count = self._r.incr(key)
        if count == 1:
            self._r.expire(key, window_s)
        if count <= limit:
            return True, 0
        ttl = self._r.ttl(key)
        return False, ttl if ttl and ttl > 0 else window_s

    # standards watch ---------------------------------------------------------
    def known_revision(self, standard: str):
        """The revision of a standard the watcher last saw published, or None
        if we have never looked. None means 'establish a baseline', not
        'everything changed'."""
        return self._r.get(keys.STANDARD_REVISION_PREFIX + standard)

    def set_known_revision(self, standard: str, revision: str):
        self._r.set(keys.STANDARD_REVISION_PREFIX + standard, revision)

    # observability -----------------------------------------------------------
    def depths(self) -> dict:
        """How much work is waiting where. Zero everywhere = pipeline idle."""
        from plantmind_core.queues import Routes
        d = {r.queue: self._r.llen(r.queue)
             for r in Routes.all() if r.queue != "q_write"}
        d["write_buffer"] = self._r.llen(keys.WRITE_BUFFER)
        d["dlq"] = self._r.llen(keys.WRITE_DLQ)
        return d

    def graph_version(self) -> int:
        return int(self._r.get(keys.GRAPH_VERSION) or 0)

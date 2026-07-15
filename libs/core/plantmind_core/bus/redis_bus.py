"""All coordination state — dedup ledger, write buffer, DLQ, locks, the
graph version counter and the delta stream — lives behind this class.
Services talk to the bus in domain terms; raw redis commands and key names
stay in here and keys.py."""

import redis

from plantmind_core import keys
from plantmind_core.config import get_settings


class RedisBus:
    def __init__(self, client):
        self._r = client

    @classmethod
    def from_settings(cls) -> "RedisBus":
        s = get_settings()
        return cls(redis.Redis.from_url(s.redis_url, decode_responses=True))

    # document dedup ledger -------------------------------------------------
    def claim_document(self, content_hash: str) -> bool:
        """First caller wins; atomic, so concurrent ingests of the same
        content can't both pass."""
        return bool(self._r.set(keys.DOC_HASH_PREFIX + content_hash, "1", nx=True))

    def release_document(self, content_hash: str):
        """Undo a claim when processing fails after the gate — otherwise a
        crashed ingest would block that file forever."""
        self._r.delete(keys.DOC_HASH_PREFIX + content_hash)

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

    def _read_stream(self, stream, after_id, block_ms) -> list:
        reply = self._r.xread({stream: after_id}, block=block_ms)
        if not reply:
            return []
        return [(entry_id, fields["payload"])
                for _, entries in reply for entry_id, fields in entries]

    def get_cursor(self, name: str) -> str:
        return self._r.get(keys.CURSOR_PREFIX + name) or "0"

    def set_cursor(self, name: str, entry_id: str):
        self._r.set(keys.CURSOR_PREFIX + name, entry_id)

    def claim_alert(self, fingerprint: str) -> bool:
        """First caller wins - one alert per distinct fact, so re-processing
        a delta or re-ingesting a file doesn't re-raise the same alert."""
        return bool(self._r.sadd(keys.ALERTED_SET, fingerprint))

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

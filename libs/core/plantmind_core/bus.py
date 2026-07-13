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

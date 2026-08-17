"""Semantic answer cache - a concern of its own, separate from the RedisBus
(which coordinates work). This stores question->answer pairs and matches an
incoming question to a cached one by embedding similarity, so the common,
repeated questions cost ~nothing.

Two things fill it: the retrieval service caches answers it computes, and
the agents service pre-fills it speculatively when the graph changes (an
answer computed at write time, before anyone asks). Both are invalidated
by node id: when a delta touches a node, cached answers that depend on it
are dropped.

Backed by Redis but brute-force cosine over a bounded set - fine for the
hundreds of hot entries a cache holds; a RediSearch vector index is the
scale path if the cache ever grows large."""

import hashlib
import json
import time

from plantmind_core import keys
from plantmind_core.config import get_settings


def cosine(a: list, b: list) -> float:
    if len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return dot / (na * nb) if na and nb else 0.0


class AnswerCache:
    def __init__(self, client, threshold=None, max_entries=None):
        s = get_settings()
        self._r = client
        self._threshold = threshold if threshold is not None \
            else s.cache_semantic_threshold
        self._max = max_entries if max_entries is not None \
            else s.answer_cache_max

    @classmethod
    def from_settings(cls) -> "AnswerCache":
        import redis
        s = get_settings()
        return cls(redis.Redis.from_url(s.redis_url, decode_responses=True))

    def get(self, embedding: list):
        """The cached answer dict for the most similar question above the
        threshold, or None."""
        best_id, best_sim = None, self._threshold
        entries = self._r.hgetall(keys.ANSWER_CACHE)
        for eid, raw in entries.items():
            sim = cosine(embedding, json.loads(raw)["embedding"])
            if sim >= best_sim:
                best_sim, best_id = sim, eid
        if best_id is None:
            return None
        self._r.zadd(keys.ANSWER_CACHE_LRU, {best_id: time.time()})   # touch
        return json.loads(entries[best_id])["answer"]

    def put(self, question: str, embedding: list, answer: dict,
            cited_nodes: list):
        eid = hashlib.sha1(question.strip().lower().encode()).hexdigest()[:16]
        entry = {"question": question, "embedding": [float(x) for x in embedding],
                 "answer": answer, "cited_nodes": cited_nodes}
        self._r.hset(keys.ANSWER_CACHE, eid, json.dumps(entry))
        self._r.zadd(keys.ANSWER_CACHE_LRU, {eid: time.time()})
        self._evict()

    def invalidate(self, node_ids: list) -> int:
        """Drop cached answers that depend on any touched node - called on a
        graph delta so stale answers never survive a change to their subject."""
        if not node_ids:
            return 0
        touched = set(node_ids)
        removed = 0
        for eid, raw in self._r.hgetall(keys.ANSWER_CACHE).items():
            if touched & set(json.loads(raw).get("cited_nodes", [])):
                self._r.hdel(keys.ANSWER_CACHE, eid)
                self._r.zrem(keys.ANSWER_CACHE_LRU, eid)
                removed += 1
        return removed

    def _evict(self):
        while self._r.hlen(keys.ANSWER_CACHE) > self._max:
            oldest = self._r.zpopmin(keys.ANSWER_CACHE_LRU, 1)
            if not oldest:
                break
            self._r.hdel(keys.ANSWER_CACHE, oldest[0][0])

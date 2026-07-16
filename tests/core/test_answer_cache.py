import fakeredis
import pytest

from plantmind_core.cache import AnswerCache, cosine


@pytest.fixture
def cache():
    return AnswerCache(fakeredis.FakeRedis(decode_responses=True),
                       threshold=0.95, max_entries=3)


def ans(text):
    return {"text": text, "citations": [], "mode": "vector",
            "confidence": "high", "graph_version": 1}


def test_cosine_basics():
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)


def test_miss_on_empty(cache):
    assert cache.get([1.0, 0.0, 0.0]) is None


def test_exact_hit(cache):
    cache.put("torque?", [1.0, 0.0, 0.0], ans("45 Nm"), ["equip:P-101A"])
    hit = cache.get([1.0, 0.0, 0.0])
    assert hit["text"] == "45 Nm"


def test_near_miss_below_threshold_returns_none(cache):
    cache.put("torque?", [1.0, 0.0, 0.0], ans("45 Nm"), [])
    # cosine ~0.83, under the 0.95 threshold
    assert cache.get([1.0, 0.7, 0.0]) is None


def test_invalidate_by_cited_node(cache):
    cache.put("q1", [1.0, 0.0, 0.0], ans("a"), ["equip:P-101A", "doc:d1"])
    cache.put("q2", [0.0, 1.0, 0.0], ans("b"), ["equip:K-301"])

    removed = cache.invalidate(["equip:P-101A"])

    assert removed == 1
    assert cache.get([1.0, 0.0, 0.0]) is None          # q1 gone
    assert cache.get([0.0, 1.0, 0.0])["text"] == "b"   # q2 survives


def test_lru_eviction_respects_max(cache):
    for i in range(5):
        v = [0.0, 0.0, 0.0]
        v[i % 3] = 1.0
        cache.put(f"q{i}", v, ans(str(i)), [])
    # max_entries=3, so only the 3 most-recent survive
    assert cache._r.hlen("answercache:entries") == 3


def test_same_question_overwrites_not_duplicates(cache):
    cache.put("torque?", [1.0, 0.0, 0.0], ans("40 Nm"), [])
    cache.put("torque?", [1.0, 0.0, 0.0], ans("45 Nm"), [])
    assert cache._r.hlen("answercache:entries") == 1
    assert cache.get([1.0, 0.0, 0.0])["text"] == "45 Nm"

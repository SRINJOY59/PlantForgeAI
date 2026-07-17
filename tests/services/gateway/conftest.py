import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    # Settings walks up to the real .env, so a developer with auth configured
    # would otherwise see these tests 401. Tests pin their own world: default
    # to auth off, and let the auth tests opt in with their own secret.
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeStore:
    def __init__(self, docs=None):
        self.docs = docs or {}          # doc_id -> (filename, bytes)
        self.staged = {}

    def put(self, key, data, content_type="application/octet-stream"):
        self.staged[key] = data

    def find_document(self, doc_id):
        return self.docs.get(doc_id)


class FakeBus:
    def __init__(self):
        self.version = 7
        self.alerts = []

    def graph_version(self):
        return self.version

    def depths(self):
        return {"q_classify": 0, "write_buffer": 0}

    def read_alerts(self, after, block_ms=15000):
        return self.alerts


class FakeSender:
    def __init__(self):
        self.sent = []

    def __call__(self, route, payload):
        self.sent.append((route, payload))

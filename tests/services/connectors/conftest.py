import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeStore:
    def __init__(self):
        self.objects = {}

    def put(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = data


class FakeSender:
    def __init__(self):
        self.sent = []

    def __call__(self, route, payload):
        self.sent.append((route, payload))


class FakeCursors:
    def __init__(self):
        self.store = {}

    def get_cursor(self, name):
        return self.store.get(name, "0")

    def set_cursor(self, name, value):
        self.store[name] = value

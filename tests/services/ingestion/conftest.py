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


class FakeObjectStore:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def put(self, key, data, content_type=None):
        self.objects[key] = data

    def get(self, key):
        return self.objects[key]

    def move(self, src, dst):
        self.objects[dst] = self.objects.pop(src)

    def delete(self, key):
        self.objects.pop(key, None)
        self.deleted.append(key)


class FakeSender:
    def __init__(self):
        self.sent = []

    def __call__(self, route, *args, **kwargs):
        self.sent.append((route, args, kwargs))

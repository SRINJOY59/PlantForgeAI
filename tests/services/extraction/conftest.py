import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings

SAMPLES = Path(__file__).resolve().parents[3] / "data" / "samples"


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeObjectStore:
    def __init__(self, objects=None):
        self.objects = objects or {}

    def get(self, key):
        return self.objects[key]


class FakeSender:
    def __init__(self):
        self.sent = []

    def __call__(self, route, *args, **kwargs):
        self.sent.append((route, args, kwargs))


class FakeLLM:
    """Returns queued pydantic instances from structured()/vision_structured()
    in order; records every prompt for assertions. Queue an Exception instance
    to make that call raise instead of return - how a caller handles a model
    that failed to answer is worth a test too."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def _next(self):
        reply = self.responses.pop(0)
        if isinstance(reply, BaseException):
            raise reply
        return reply

    async def structured(self, messages, schema, tier=None, max_tokens=4096):
        self.calls.append(("structured", messages, schema))
        return self._next()

    async def vision_structured(self, prompt, images_b64, schema, max_tokens=4096):
        self.calls.append(("vision", prompt, schema))
        return self._next()

    async def vision(self, prompt, images_b64, max_tokens=4096):
        self.calls.append(("vision_text", prompt, None))
        return self._next()


class FakeEmbedder:
    async def embed(self, texts):
        return [[0.1, 0.2, 0.3] for _ in texts]

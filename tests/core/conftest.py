import asyncio
from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError

from plantmind_core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    real_sleep = asyncio.sleep

    async def instant(_delay):
        await real_sleep(0)

    monkeypatch.setattr("plantmind_core.llm.client.asyncio.sleep", instant)


def make_response(content="ok", prompt_tokens=10, completion_tokens=5):
    return SimpleNamespace(
        usage=SimpleNamespace(prompt_tokens=prompt_tokens,
                              completion_tokens=completion_tokens),
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def make_status_error(status_code):
    request = httpx.Request("POST", "https://test/chat/completions")
    response = httpx.Response(status_code, request=request)
    return APIStatusError(f"http {status_code}", response=response, body=None)


class FakeChatAPI:
    """Stands in for client.chat.completions. Yields queued outcomes in order;
    an Exception instance is raised, anything else is returned."""

    def __init__(self, *outcomes):
        self.outcomes = list(outcomes)
        self.calls = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def install_fake(llm_client, fake):
    llm_client._client = SimpleNamespace(
        chat=SimpleNamespace(completions=fake)
    )

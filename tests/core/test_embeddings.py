from types import SimpleNamespace

import pytest

from plantmind_core.llm import embeddings as emb_mod
from plantmind_core.llm.embeddings import EmbeddingClient
from conftest import make_status_error


class FakeEmbeddingsAPI:
    def __init__(self, fail_first=0):
        self.fail_first = fail_first
        self.calls = []

    async def create(self, model, input):
        self.calls.append(list(input))
        if self.fail_first > 0:
            self.fail_first -= 1
            raise make_status_error(429)
        return SimpleNamespace(
            data=[SimpleNamespace(embedding=[0.1, 0.2]) for _ in input]
        )


def install(client, fake):
    client._client = SimpleNamespace(embeddings=fake)


async def test_empty_input_returns_empty():
    client = EmbeddingClient()
    install(client, FakeEmbeddingsAPI())
    assert await client.embed([]) == []


async def test_single_batch():
    client = EmbeddingClient()
    fake = FakeEmbeddingsAPI()
    install(client, fake)

    vecs = await client.embed(["a", "b", "c"])

    assert len(vecs) == 3
    assert len(fake.calls) == 1


async def test_splits_into_batches_and_preserves_order(monkeypatch):
    monkeypatch.setattr(emb_mod, "MAX_BATCH", 2)
    client = EmbeddingClient()
    fake = FakeEmbeddingsAPI()
    install(client, fake)

    vecs = await client.embed(["a", "b", "c", "d", "e"])

    assert len(vecs) == 5
    assert [len(c) for c in fake.calls] == [2, 2, 1]
    assert fake.calls[0] == ["a", "b"]
    assert fake.calls[2] == ["e"]


async def test_retries_on_429(monkeypatch):
    async def instant(_):
        pass
    monkeypatch.setattr("plantmind_core.llm.embeddings.asyncio.sleep", instant)

    client = EmbeddingClient()
    fake = FakeEmbeddingsAPI(fail_first=2)
    install(client, fake)

    vecs = await client.embed(["a"])

    assert len(vecs) == 1
    assert len(fake.calls) == 3

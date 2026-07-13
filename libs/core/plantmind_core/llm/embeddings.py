import asyncio
import random

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("embeddings")

MAX_BATCH = 512  # most providers cap somewhere between 1k-2k inputs per request


class EmbeddingClient:
    def __init__(self):
        s = get_settings()
        self._client = AsyncOpenAI(
            api_key=s.embedding_api_key or s.openrouter_api_key,
            base_url=s.embedding_base_url,
            timeout=60.0,
            max_retries=0,
        )
        self._model = s.embedding_model
        self._sem = asyncio.Semaphore(8)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        batches = [texts[i:i + MAX_BATCH] for i in range(0, len(texts), MAX_BATCH)]
        results = await asyncio.gather(*(self._embed_batch(b) for b in batches))
        return [vec for batch in results for vec in batch]

    async def _embed_batch(self, batch):
        for attempt in range(5):
            try:
                async with self._sem:
                    resp = await self._client.embeddings.create(
                        model=self._model, input=batch
                    )
                return [d.embedding for d in resp.data]
            except (APITimeoutError, APIConnectionError):
                pass
            except APIStatusError as e:
                if e.status_code not in {429, 500, 502, 503, 529}:
                    raise
            delay = min(2 ** attempt + random.random(), 20)
            log.warning("embedding retry", attempt=attempt, delay=round(delay, 1))
            await asyncio.sleep(delay)
        raise RuntimeError("embedding request failed after 5 attempts")


_client = None


def get_embedder() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client

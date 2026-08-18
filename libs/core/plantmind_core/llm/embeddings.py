import asyncio
import math
import random
from typing import List, Optional

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger

log = get_logger("embeddings")

MAX_BATCH = 512

_fastembed_model = None


def _get_local_model(model_name: str = "BAAI/bge-small-en-v1.5"):
    global _fastembed_model
    if _fastembed_model is None:
        try:
            from fastembed import TextEmbedding
            _fastembed_model = TextEmbedding(model_name=model_name)
            log.info("Initialized local FastEmbed model", model=model_name)
        except Exception as e:
            log.warning("FastEmbed not available, using hash projection fallback", error=str(e))
            _fastembed_model = False
    return _fastembed_model


def _normalize_dim(vec, target_dim: int) -> List[float]:
    """Pad or truncate vector to target_dim and L2-normalize it."""
    vec = [float(x) for x in vec]
    if len(vec) < target_dim:
        vec = vec + [0.0] * (target_dim - len(vec))
    elif len(vec) > target_dim:
        vec = vec[:target_dim]
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        return [float(x / norm) for x in vec]
    return vec


def _hash_embed(text: str, dim: int = 1536) -> List[float]:
    """Lightweight zero-dependency deterministic pseudo-embedding fallback."""
    import hashlib
    words = text.lower().split()
    vec = [0.0] * dim
    for i, word in enumerate(words):
        h = int(hashlib.md5(word.encode("utf-8")).hexdigest(), 16)
        idx = h % dim
        sign = 1.0 if ((h >> 4) & 1) else -1.0
        vec[idx] += sign * (1.0 / (1.0 + 0.1 * i))
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 1e-9:
        return [x / norm for x in vec]
    # Default non-zero fallback vector
    vec[0] = 1.0
    return vec


import os


class EmbeddingClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None, target_dim: int | None = None):
        s = get_settings()
        self._target_dim = target_dim or s.embedding_dim

        gemini_key = (
            s.gemini_api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_GENAI_API_KEY")
        )
        is_gemini = (
            getattr(s, "embedding_provider", "openrouter") == "gemini"
            or (getattr(s, "llm_provider", "openrouter") == "gemini" and not s.embedding_api_key and not s.openrouter_api_key)
        )

        if is_gemini and not model:
            self._model = getattr(s, "gemini_embedding_model", "text-embedding-004")
            self._base_url = base_url or getattr(s, "gemini_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/")
            self._api_key = api_key or s.embedding_api_key or gemini_key or "missing-key"
        else:
            self._model = model or s.embedding_model
            self._base_url = base_url or (s.embedding_base_url if s.embedding_base_url != "local" else "https://openrouter.ai/api/v1")
            self._api_key = api_key or s.embedding_api_key or s.openrouter_api_key or "local"

        self._is_local = (
            self._model.startswith("fastembed")
            or self._model == "local"
            or s.embedding_base_url == "local"
            or getattr(s, "embedding_provider", "openrouter") == "local"
        )
        self._client = AsyncOpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            timeout=60.0,
            max_retries=0,
        )
        self._sem = asyncio.Semaphore(8)
        self._fallback_mode = False

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        # If a fake/mock client was explicitly installed for testing, always use it
        is_real_client = isinstance(self._client, AsyncOpenAI)

        if is_real_client and (self._is_local or self._fallback_mode):
            return await self._embed_local(texts)

        batches = [texts[i:i + MAX_BATCH] for i in range(0, len(texts), MAX_BATCH)]
        try:
            results = await asyncio.gather(*(self._embed_batch(b) for b in batches))
            return [vec for batch in results for vec in batch]
        except Exception as e:
            if not is_real_client:
                raise
            log.warning("Remote embedding failed, switching to local fallback engine", error=str(e))
            self._fallback_mode = True
            return await self._embed_local(texts)

    async def _embed_local(self, texts: list[str]) -> list[list[float]]:
        local_model = _get_local_model()
        if local_model:
            try:
                def _run_fastembed():
                    raw = list(local_model.embed(texts))
                    return [_normalize_dim(list(v), self._target_dim) for v in raw]
                return await asyncio.to_thread(_run_fastembed)
            except Exception as e:
                log.warning("Local FastEmbed execution error, falling back to hash embedder", error=str(e))

        return [_hash_embed(t, self._target_dim) for t in texts]

    async def _embed_batch(self, batch):
        for attempt in range(5):
            try:
                async with self._sem:
                    resp = await self._client.embeddings.create(
                        model=self._model, input=batch
                    )
                return [_normalize_dim(d.embedding, self._target_dim) for d in resp.data]
            except (APITimeoutError, APIConnectionError):
                pass
            except APIStatusError as e:
                if e.status_code == 402:
                    log.warning("OpenRouter embedding 402: insufficient credits, activating local fallback")
                    raise
                if e.status_code not in {429, 500, 502, 503, 529}:
                    raise
            delay = min(2 ** attempt + random.random(), 10)
            log.warning("embedding retry", attempt=attempt, delay=round(delay, 1))
            await asyncio.sleep(delay)
        raise RuntimeError("embedding request failed after 5 attempts")


_client = None


def get_embedder() -> EmbeddingClient:
    global _client
    if _client is None:
        _client = EmbeddingClient()
    return _client


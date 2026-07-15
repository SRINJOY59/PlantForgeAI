"""Central settings. Every service reads the same .env via this class —
no service defines its own config keys."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _find_env() -> str:
    """Walk up from CWD so smoke tests work from any directory in the repo."""
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / ".env"
        if candidate.exists():
            return str(candidate)
    return ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_find_env(), extra="ignore")

    # --- infrastructure ---
    neo4j_uri: str = "bolt://neo4j:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "change_me"
    neo4j_ro_user: str = "retrieval_ro"
    neo4j_ro_password: str = "change_me"
    redis_url: str = "redis://redis:6379/0"
    retrieval_url: str = "http://localhost:8001"     # gateway proxies Q&A here
    minio_endpoint: str = "http://minio:9000"
    minio_user: str = "plantmind"
    minio_password: str = "change_me"

    # --- LLM via OpenRouter (OpenAI-compatible) ---
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_cheap: str = "qwen/qwen3.6-flash"         # classify, verify, ER adjudication
    llm_mid: str = "deepseek/deepseek-v4-pro"     # text extraction, answering
    llm_vision: str = "qwen/qwen3.7-plus"         # P&ID extraction (image input)
    llm_max_concurrency: int = 32                    # global in-process semaphore
    llm_max_retries: int = 5
    llm_timeout_s: float = 120.0

    # --- embeddings (any OpenAI-compatible /embeddings endpoint) ---
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""                      # falls back to openrouter key
    embedding_model: str = "openai/text-embedding-3-small"
    embedding_dim: int = 1536      # what the model emits; index must match

    # --- pipeline tuning ---
    extraction_batch_size: int = 8
    write_batch_size: int = 500
    write_flush_interval_s: float = 2.0
    er_cosine_accept: float = 0.92
    er_cosine_llm_band: float = 0.80
    pathrag_decay_alpha: float = 0.8
    pathrag_max_hops: int = 4
    pathrag_top_paths: int = 15
    cache_semantic_threshold: float = 0.95
    denoise_interval_s: int = 3600


@lru_cache
def get_settings() -> Settings:
    return Settings()

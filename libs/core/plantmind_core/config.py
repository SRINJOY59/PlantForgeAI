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
    agents_url: str = "http://localhost:8002"        # ... and assessments here
    # browser origins allowed to call the gateway, comma-separated. Locked to
    # the dev SPA by default; set the real origin(s) in prod. "*" is accepted
    # but should never be used with a browser client you actually ship.
    cors_origins: str = "http://localhost:5173"

    # Supabase JWT secret (dashboard > Settings > API > JWT Secret). Empty
    # disables auth so local dev / demos still run open.
    supabase_jwt_secret: str = ""
    minio_endpoint: str = "http://minio:9000"
    # The host a browser reaches MinIO on. Presigned URLs must be SIGNED with
    # this, not rewritten to it afterwards - SigV4 covers the Host header, so a
    # post-signing string replace produces SignatureDoesNotMatch. Set this to
    # the public MinIO domain in production.
    minio_public_endpoint: str = "http://localhost:9000"
    # Pinned, not discovered. minio-py resolves an unknown region by calling
    # GET /<bucket>?location= against the endpoint - which the signing client
    # cannot do, because its endpoint is the browser's hostname and is not
    # reachable from inside the compose network. Both clients must agree on
    # this, since the region is part of the SigV4 signature.
    minio_region: str = "us-east-1"
    minio_user: str = "plantmind"
    minio_password: str = "change_me"

    # --- historian (time-series system of record) ---
    # A plain Postgres DSN. Point it at Timescale Cloud for full hypertable +
    # compression + retention, or at Supabase / any Postgres for the plain
    # fallback - the client detects the timescaledb extension and adapts, so
    # nothing else changes. Empty disables the historian: the sink idles and
    # the rest of the stack runs untouched. Never commit a real DSN; set it in
    # .env (it carries the password).
    timescale_dsn: str = ""
    historian_batch_rows: int = 500       # flush a batch once it reaches this
    historian_flush_ms: int = 2000        # ...or after this long, whichever first
    historian_retention_days: int = 90    # retention policy, applied only on timescaledb

    # --- LLM Provider Selection & Settings ---
    llm_provider: str = "openrouter"              # "openrouter" | "gemini"
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    llm_cheap: str = "qwen/qwen3.6-flash"         # classify, verify, ER adjudication
    llm_mid: str = "deepseek/deepseek-v4-pro"     # text extraction, answering
    llm_vision: str = "qwen/qwen3.7-plus"         # P&ID extraction (image input)
    llm_max_concurrency: int = 32                    # global in-process semaphore
    llm_max_rps: float = 3.0                         # max requests per second client-side rate limit
    llm_max_retries: int = 5
    llm_timeout_s: float = 120.0

    # --- Google Gemini (AI Studio endpoint, API key auth) ---
    gemini_api_key: str = ""                         # falls back to GEMINI_API_KEY / GOOGLE_API_KEY env
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai/"
    gemini_llm_cheap: str = "gemini-3.6-flash"
    gemini_llm_mid: str = "gemini-3.7-flash"
    gemini_llm_vision: str = "gemini-3.6-flash"

    # --- Vertex AI (Gemini via GCP project, ADC / gcloud auth) ---
    # Set llm_provider="vertex" to route through Vertex AI instead of AI Studio.
    # Requires: gcloud auth application-default login (or a service account).
    gcp_project: str = ""          # GCP project ID; falls back to GOOGLE_CLOUD_PROJECT env
    vertex_region: str = "us-central1"
    # MID answers the streaming Ask path; flash (not the pro thinking model)
    # keeps time-to-first-token low. See .env for the rationale.
    vertex_llm_cheap: str = "google/gemini-2.5-flash-lite"
    vertex_llm_mid: str = "google/gemini-2.5-flash"
    vertex_llm_vision: str = "google/gemini-2.5-flash"

    # --- embeddings (OpenRouter, Gemini, or local) ---
    embedding_provider: str = "openrouter"           # "openrouter" | "gemini" | "local"
    embedding_base_url: str = "https://openrouter.ai/api/v1"
    embedding_api_key: str = ""                      # falls back to openrouter or gemini key
    embedding_model: str = "openai/text-embedding-3-small"
    gemini_embedding_model: str = "text-embedding-004"
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
    answer_cache_max: int = 300            # LRU cap on cached answers
    denoise_interval_s: int = 3600
    connectors_config: str = "connectors.json"    # data-source definitions
    connector_sync_interval_s: int = 300
    # Off unless a site asks for it. It is the only part of the system that
    # reaches the public internet, it bills per search on top of tokens, and a
    # plant OT network usually has no route out at all.
    standards_watch_enabled: bool = False

    # Whether a process-limit alarm from a simulator auto-spends an LLM RCA.
    # Off by default: the diagnostics service now answers every alarm
    # deterministically (signature + library match), for free and in seconds, so
    # an automatic LLM investigation of every breach is cost with little signal.
    # LLM RCA becomes a deliberate, per-episode request instead (rca:requests).
    auto_rca_enabled: bool = False

    # --- Slack notifications (important-only) ---
    # Off unless a webhook is set. Deliberately narrow: only high-signal events
    # reach Slack (critical process alarms today; confirmed-fault diagnoses and
    # RCA verdicts are the planned next triggers), deduped per fault episode so a
    # channel does not get muted into uselessness. See plantmind_core.notify.
    slack_enabled: bool = False
    slack_webhook_url: str = ""              # Slack Incoming Webhook URL
    slack_min_severity: str = "critical"     # "critical" | "warning"
    # A given alarm fingerprint is not re-sent within this window, so a tag that
    # chatters across a limit produces one Slack message, not one per crossing.
    slack_dedup_ttl_s: int = 1800

    # --- Slack as an approval gate (work-order scheduling) ---
    # Scheduling work is the one flow where Slack is not a notification but a
    # control: the engineer proposes a slot, Slack authorises it, and only then
    # can the order be dispatched to a crew. That needs a way back IN from
    # Slack, which an Incoming Webhook alone does not give you. Two return
    # paths, because the two have very different setup costs:
    #
    #   1. Block Kit buttons -> POST /slack/interactions. Needs a real Slack
    #      app (signing secret below) and a publicly reachable gateway.
    #   2. Signed approve/reject links. Needs nothing but the webhook that is
    #      already configured, so the flow works on day one.
    #
    # Both are posted on the same message; whichever the workspace supports is
    # the one that gets used, and both land in the same handler.

    # Slack app signing secret (api.slack.com > Your App > Basic Information).
    # Empty means button callbacks are refused - unverifiable, so not trusted.
    slack_signing_secret: str = ""
    # HMAC key for the signed approval links. Left empty it is derived
    # deterministically from other secrets (see notify.approvals) so a demo
    # still works across gateway workers, with a warning. Set it in production.
    slack_approval_secret: str = ""
    # How long an approval link stays valid. A work slot that sat unapproved
    # for a day should be re-proposed against current plant state, not
    # rubber-stamped from a stale message.
    slack_approval_ttl_s: int = 86400
    # The base URL Slack itself can reach the gateway on. The links are built
    # from this, so localhost only works if Slack is not really involved.
    public_gateway_url: str = "http://localhost:8000"

    # --- crew dispatch ---
    # There is deliberately no "languages to translate into" setting. The set
    # is derived from the crew actually on the roster (see gateway.dispatch),
    # because a fixed list means translating into twelve languages for a crew
    # that reads two - eleven wasted LLM calls, and eleven job cards nobody
    # checks. Which languages are POSSIBLE is a property of the dispatcher
    # (LANGUAGE_NAMES in agents.usecases.work_order.dispatch), not of config.
    #
    # A translated brief is cached per (draft, language) for this long. The
    # draft is immutable, so the only reason to expire at all is to reclaim.
    dispatch_brief_ttl_s: int = 604800


@lru_cache
def get_settings() -> Settings:
    return Settings()

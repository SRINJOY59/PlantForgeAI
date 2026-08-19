import asyncio
import json
import os
import random
import re
from enum import Enum
from typing import Type, TypeVar

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError
from pydantic import BaseModel, ValidationError

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger, TokenMeter

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)

RETRYABLE = {429, 500, 502, 503, 529}


class EmptyCompletion(ValueError):
    """The model returned nothing where structured output was required.

    Its own error class because it is not malformed JSON and must not be
    handled as such: parsing '' surfaces as a pydantic "EOF while parsing a
    value at line 1 column 0", which reads like a broken schema and sends the
    reader hunting through the model definition. The model simply said nothing
    - usually a reasoning model that spent its entire token budget thinking.
    """


# Tool-call markup leaking into the prose channel.
#
# DeepSeek-family models (LLM_MID) serialise tool calls with their own special
# tokens rather than the OpenAI tool_calls field. When a provider does not parse
# them back out, they arrive inside message.content as literal text - and end up
# rendered in a work permit, where "<｜｜DSML｜｜invoke name=..." sits under
# "Safety Analysis & Pre-Job Instruction" for a technician to read.
#
# The vertical bars are FULLWIDTH (U+FF5C) in these tokens, so the patterns
# accept both that and ASCII '|'. Nothing legitimate in a plant document looks
# like this, which is what makes stripping safe.
_BAR = r"[｜|]"
_DSML_BLOCK = re.compile(
    rf"<\s*{_BAR}{{1,2}}\s*DSML\s*{_BAR}{{1,2}}\s*tool_calls\s*>.*?"
    rf"<\s*/\s*{_BAR}{{1,2}}\s*DSML\s*{_BAR}{{1,2}}\s*tool_calls\s*>",
    re.S | re.I)
_DSML_TAG = re.compile(rf"<\s*/?\s*{_BAR}{{1,2}}\s*DSML\s*{_BAR}{{1,2}}[^>]*>", re.I)
# The whole span, not just the delimiters: between <｜tool▁calls▁begin｜> and
# <｜tool▁calls▁end｜> sits the serialised call itself (function name, arguments).
# Dropping only the tokens would leave "get_documents{"doc_id":...}" as prose.
_NATIVE_TOOL_SPAN = re.compile(
    rf"<{_BAR}[^<>]{{0,40}}?begin{_BAR}>.*?<{_BAR}[^<>]{{0,40}}?end{_BAR}>",
    re.S | re.I)
# leftovers: <｜tool▁sep｜>, <|endoftext|> and friends
_SPECIAL_TOKEN = re.compile(rf"<{_BAR}[^<>]{{0,80}}?{_BAR}>")
_BLANK_RUN = re.compile(r"\n{3,}")


def sanitize_text(raw: str) -> str:
    """Strip leaked tool-call markup and special tokens out of model prose.

    Applied to every text completion rather than at the call sites that
    happened to break: the markup is a transport artefact, so the transport is
    where it should die. A caller building a safety document should not have to
    know which model family is behind the tier it asked for.
    """
    if not raw:
        return ""
    text = _DSML_BLOCK.sub("", raw)
    text = _DSML_TAG.sub("", text)
    text = _NATIVE_TOOL_SPAN.sub("", text)
    text = _SPECIAL_TOKEN.sub("", text)
    return _BLANK_RUN.sub("\n\n", text).strip()


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


class AsyncRateLimiter:
    """Token-bucket style rate limiter ensuring requests stay within max_rps."""
    def __init__(self, max_rps: float = 3.0):
        self._interval = 1.0 / max(0.1, max_rps)
        self._lock = asyncio.Lock()
        self._last_time = 0.0

    async def acquire(self):
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            elapsed = now - self._last_time
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_time = loop.time()


class Tier(str, Enum):
    CHEAP = "cheap"
    MID = "mid"
    VISION = "vision"


class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 models: dict[Tier, str] | None = None, max_concurrency: int | None = None,
                 max_rps: float | None = None, max_retries: int | None = None,
                 timeout_s: float | None = None):
        s = get_settings()
        self._provider = getattr(s, "llm_provider", "openrouter")
        self._api_key = api_key or s.openrouter_api_key
        self._base_url = base_url or s.openrouter_base_url
        self._models = models or {
            Tier.CHEAP: s.llm_cheap,
            Tier.MID: s.llm_mid,
            Tier.VISION: s.llm_vision,
        }
        self._timeout_s = timeout_s or s.llm_timeout_s
        self._max_retries = max_retries if max_retries is not None else s.llm_max_retries
        # max_retries=0: the SDK's built-in retry would bypass our semaphore
        self._client = AsyncOpenAI(
            api_key=self._api_key or "missing-key",
            base_url=self._base_url,
            timeout=self._timeout_s,
            max_retries=0,
        )
        self._sem = asyncio.Semaphore(max_concurrency or s.llm_max_concurrency)
        self._limiter = AsyncRateLimiter(max_rps=max_rps or getattr(s, "llm_max_rps", 3.0))
        self.meter = TokenMeter()

    async def _create(self, messages, tier, max_tokens, temperature=0.0,
                      **extra):
        """The one place that talks to the provider: semaphore, rate limit, retry,
        token accounting. Returns the raw response."""
        model = self._models[tier]
        for attempt in range(self._max_retries + 1):
            try:
                async with self._sem:
                    await self._limiter.acquire()
                    resp = await self._client.chat.completions.create(
                        model=model, messages=messages, max_tokens=max_tokens,
                        temperature=temperature, **extra)
                if resp.usage:
                    self.meter.record(model, resp.usage.prompt_tokens,
                                      resp.usage.completion_tokens)
                return resp
            except (APITimeoutError, APIConnectionError) as e:
                err = e
            except APIStatusError as e:
                err = e
                if e.status_code == 402:
                    if attempt == self._max_retries:
                        raise
                    match = re.search(r"can only afford (\d+)", str(e))
                    if match:
                        afford = int(match.group(1))
                        if afford > 20:
                            max_tokens = min(max_tokens, afford - 5)
                            log.warning("OpenRouter 402: reduced max_tokens", max_tokens=max_tokens)
                            continue
                    max_tokens = max(100, max_tokens // 2)
                    log.warning("OpenRouter 402: reduced max_tokens", max_tokens=max_tokens)
                    continue
                if e.status_code == 429:
                    if attempt == self._max_retries:
                        raise
                    delay = min(3.0 * (2 ** attempt) + random.uniform(0.5, 2.0), 30.0)
                    log.warning("OpenRouter 429 rate limited; backing off", model=model, attempt=attempt, delay=round(delay, 1))
                    await asyncio.sleep(delay)
                    continue
                if e.status_code not in RETRYABLE:
                    raise
            if attempt == self._max_retries:
                raise err
            delay = min(2 ** attempt + random.random(), 30)
            log.warning("llm retry", model=model, attempt=attempt,
                        delay=round(delay, 1))
            await asyncio.sleep(delay)

    async def complete(self, messages, tier=Tier.CHEAP, max_tokens=2048,
                       temperature=0.0, response_format=None) -> str:
        extra = {"response_format": response_format} if response_format else {}
        resp = await self._create(messages, tier, max_tokens, temperature,
                                  **extra)
        return sanitize_text(resp.choices[0].message.content or "")

    async def chat_with_tools(self, messages, tools, tier=Tier.MID,
                              max_tokens=2048):
        """One tool-calling turn: returns the assistant message, which may
        carry tool_calls to execute. The agent loop drives the iteration."""
        resp = await self._create(messages, tier, max_tokens,
                                  tools=tools, tool_choice="auto")
        return resp.choices[0].message

    async def stream(self, messages, tier=Tier.MID, max_tokens=2048,
                     temperature=0.0):
        """Yields answer text deltas as they arrive."""
        model = self._models[tier]
        for attempt in range(self._max_retries + 1):
            try:
                async with self._sem:
                    stream = await self._client.chat.completions.create(
                        model=model, messages=messages, max_tokens=max_tokens,
                        temperature=temperature, stream=True)
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta.content
                        if delta:
                            yield delta
                break
            except APIStatusError as e:
                if e.status_code == 402:
                    match = re.search(r"can only afford (\d+)", str(e))
                    if match:
                        afford = int(match.group(1))
                        if afford > 20:
                            max_tokens = min(max_tokens, afford - 5)
                            log.warning("OpenRouter 402 stream: reduced max_tokens", max_tokens=max_tokens)
                            continue
                    max_tokens = max(100, max_tokens // 2)
                    log.warning("OpenRouter 402 stream: reduced max_tokens", max_tokens=max_tokens)
                    continue
                raise

    async def structured(self, messages, schema: Type[T], tier=Tier.CHEAP,
                         max_tokens=4096) -> T:
        json_schema = schema.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": json_schema,
            },
        }
        # schema also goes in a system message: some open-weight providers
        # silently downgrade json_schema to json_object (which then requires
        # the word "json" in the prompt), and weaker ones follow the prompt
        # better than the response_format anyway
        convo = [{"role": "system", "content":
                  "Respond with a single JSON object conforming to this "
                  "JSON schema, no prose:\n" + json.dumps(json_schema)},
                 *messages]
        raw = await self.complete(convo, tier=tier, max_tokens=max_tokens,
                                  response_format=response_format)
        try:
            return self._parse(schema, raw)
        except (ValidationError, EmptyCompletion) as e:
            # reasoning models burn thinking tokens from the same budget, so
            # truncated json usually means "not enough room" - retry bigger.
            # An empty response gets the same treatment for the same reason:
            # a model that spent its whole budget thinking emits nothing at all.
            log.warning("structured output unusable, retrying larger",
                        schema=schema.__name__, error=str(e)[:200])
            raw = await self.complete(convo, tier=tier, max_tokens=max_tokens * 2,
                                      response_format=response_format)
            # Parsed through the same guard: a second empty response used to
            # escape as a bare pydantic "EOF while parsing" on input_value='',
            # which reads like malformed JSON rather than "the model said
            # nothing" and sent callers looking in the wrong place.
            return self._parse(schema, raw)

    @staticmethod
    def _parse(schema: Type[T], raw: str) -> T:
        text = _strip_fences(raw or "")
        if not text.strip():
            raise EmptyCompletion(
                f"{schema.__name__}: the model returned an empty completion")
        return schema.model_validate_json(text)

    async def web_search(self, prompt: str, tier=Tier.CHEAP,
                         max_tokens=1024) -> tuple:
        """-> (text, [{'url', 'title'}]). Openrouter runs the search itself as
        a server-side tool and hands back the answer plus url_citation
        annotations, so there is no tool loop for us to drive.

        Billed per search on top of tokens, and it reaches the public internet,
        so this is not on the answer path - only a watcher that runs on a slow
        clock calls it.
        """
        try:
            resp = await self._create(
                [{"role": "user", "content": prompt}], tier, max_tokens,
                tools=[{"type": "web_search"}])
            message = resp.choices[0].message
            return message.content or "", _url_citations(message)
        except Exception as e:
            # Fallback for providers where openrouter-specific web_search tool is unavailable
            log.warning("web_search tool call unavailable on provider; falling back to direct prompt",
                        error=str(e))
            text = await self.complete([{"role": "user", "content": prompt}],
                                       tier=tier, max_tokens=max_tokens)
            return text, []

    async def vision(self, prompt: str, images_b64: list[str],
                     max_tokens=4096) -> str:
        content = [{"type": "text", "text": prompt}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        return await self.complete([{"role": "user", "content": content}],
                                   tier=Tier.VISION, max_tokens=max_tokens)

    async def vision_structured(self, prompt: str, images_b64: list[str],
                                schema: Type[T], max_tokens=8192) -> T:
        content = [{"type": "text", "text": prompt}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        return await self.structured([{"role": "user", "content": content}],
                                     schema, tier=Tier.VISION, max_tokens=max_tokens)


class GeminiClient(LLMClient):
    """Specialized LLM client for Google Gemini models via Gemini's OpenAI-compatible endpoint."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 models: dict[Tier, str] | None = None, max_concurrency: int | None = None,
                 max_rps: float | None = None, max_retries: int | None = None,
                 timeout_s: float | None = None):
        s = get_settings()
        gemini_key = (
            api_key
            or s.gemini_api_key
            or os.environ.get("GEMINI_API_KEY")
            or os.environ.get("GOOGLE_API_KEY")
            or os.environ.get("GOOGLE_GENAI_API_KEY")
            or s.openrouter_api_key
        )
        gemini_models = models or {
            Tier.CHEAP: getattr(s, "gemini_llm_cheap", "gemini-3.5-flash"),
            Tier.MID: getattr(s, "gemini_llm_mid", "gemini-3.7-flash"),
            Tier.VISION: getattr(s, "gemini_llm_vision", "gemini-3.5-flash"),
        }
        super().__init__(
            api_key=gemini_key,
            base_url=base_url or getattr(s, "gemini_base_url", "https://generativelanguage.googleapis.com/v1beta/openai/"),
            models=gemini_models,
            max_concurrency=max_concurrency,
            max_rps=max_rps,
            max_retries=max_retries,
            timeout_s=timeout_s,
        )
        self._provider = "gemini"


class VertexLLMClient(LLMClient):
    """Gemini via Vertex AI using Application Default Credentials (gcloud auth).

    Tokens are refreshed automatically via google-auth — no API key needed.
    The Vertex AI OpenAI-compatible endpoint accepts the same request shape
    as the AI Studio endpoint but uses Bearer token auth and GCP project routing.
    """

    def __init__(self, models: dict[Tier, str] | None = None,
                 max_concurrency: int | None = None, max_rps: float | None = None,
                 max_retries: int | None = None, timeout_s: float | None = None):
        s = get_settings()
        project = getattr(s, "gcp_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        region = getattr(s, "vertex_region", "") or os.environ.get("VERTEX_REGION", "us-central1")
        # kept for the native generateContent endpoint, which web_search uses for
        # Google Search grounding (the OpenAI-compat endpoint has no grounding)
        self._project = project
        self._region = region
        base_url = (
            f"https://{region}-aiplatform.googleapis.com/v1beta1"
            f"/projects/{project}/locations/{region}/endpoints/openapi/"
        )
        vertex_models = models or {
            Tier.CHEAP: getattr(s, "vertex_llm_cheap", "google/gemini-2.5-flash"),
            Tier.MID: getattr(s, "vertex_llm_mid", "google/gemini-2.5-pro"),
            Tier.VISION: getattr(s, "vertex_llm_vision", "google/gemini-2.5-flash"),
        }
        super().__init__(
            api_key="vertex-adc",
            base_url=base_url,
            models=vertex_models,
            max_concurrency=max_concurrency,
            max_rps=max_rps,
            max_retries=max_retries,
            timeout_s=timeout_s,
        )
        self._provider = "vertex"
        self._creds = None
        self._creds_lock = asyncio.Lock()
        # Which token self._client was last built with, so a call only rebuilds
        # the client when the token actually rotated - not on every request, and
        # not racing two rebuilds against each other in the steady state.
        self._built_with = None

    def _load_creds(self):
        import google.auth
        s = get_settings()
        project = getattr(s, "gcp_project", "") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        creds, _ = google.auth.default(
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
            quota_project_id=project or None,
        )
        return creds

    async def _get_token(self) -> str:
        import google.auth.transport.requests
        async with self._creds_lock:
            if self._creds is None:
                self._creds = await asyncio.get_event_loop().run_in_executor(
                    None, self._load_creds)
            if not self._creds.valid:
                req = google.auth.transport.requests.Request()
                await asyncio.get_event_loop().run_in_executor(
                    None, self._creds.refresh, req)
        return self._creds.token

    async def _refresh_client(self):
        """Ensure self._client carries a live ADC bearer token.

        This is the one thing that must run before ANY provider call - not just
        _create. The base class was built for a static api_key: complete() goes
        through _create, but stream() and the tool path hit self._client
        directly. If only _create refreshed the token, streaming would still be
        sending the 'vertex-adc' placeholder and Vertex would reject it
        (ACCESS_TOKEN_TYPE_UNSUPPORTED). So every entry point calls this, and it
        rebuilds only when the cached token has rotated.
        """
        token = await self._get_token()
        if token == self._built_with:
            return
        self._client = AsyncOpenAI(
            api_key=token,
            base_url=str(self._client.base_url),
            timeout=self._timeout_s,
            max_retries=0,
        )
        self._built_with = token

    async def _create(self, messages, tier, max_tokens, temperature=0.0, **extra):
        await self._refresh_client()
        return await super()._create(messages, tier, max_tokens, temperature, **extra)

    async def stream(self, messages, tier=Tier.MID, max_tokens=2048, temperature=0.0):
        # The Ask path streams, and the base stream() talks to self._client
        # directly - so the token must be refreshed here too, or every streamed
        # answer 401s on the placeholder key.
        await self._refresh_client()
        async for delta in super().stream(messages, tier, max_tokens, temperature):
            yield delta

    async def web_search(self, prompt: str, tier=Tier.MID,
                         max_tokens=2048) -> tuple:
        """Web search via Gemini's Google Search grounding.

        The OpenAI-compatible endpoint the rest of this client speaks has no
        grounding, so this one method drops to the native generateContent API,
        which does. Returns (text, [{'url','title'}]) - the same shape the base
        (OpenRouter) web_search returns, so a caller like the standards watcher
        never has to know which provider actually ran the search.

        Uses a grounding-capable model (Gemini 2.5 flash by default); flash-lite
        does not ground, so the tier is bumped to MID rather than trusting the
        cheap tier. Returns empty on any failure - a watcher on a slow clock
        should lose one scan, never crash.
        """
        import httpx
        try:
            token = await self._get_token()
        except Exception as e:
            log.warning("vertex web_search: no ADC token", error=str(e)[:120])
            return "", []
        model = self._models.get(tier, self._models[Tier.MID]).split("/")[-1]
        url = (f"https://{self._region}-aiplatform.googleapis.com/v1/projects/"
               f"{self._project}/locations/{self._region}/publishers/google/"
               f"models/{model}:generateContent")
        body = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "tools": [{"googleSearch": {}}],
            # thinkingBudget 0: a grounded revision lookup wants the model to
            # search and report, not deliberate - and 2.5 flash otherwise spends
            # the whole token budget thinking and truncates the JSON mid-string.
            "generationConfig": {"maxOutputTokens": max_tokens,
                                 "temperature": 0.0,
                                 "thinkingConfig": {"thinkingBudget": 0}},
        }
        try:
            async with self._sem:
                await self._limiter.acquire()
                async with httpx.AsyncClient(timeout=self._timeout_s) as http:
                    resp = await http.post(
                        url, json=body,
                        headers={"Authorization": f"Bearer {token}"})
            if resp.status_code >= 300:
                log.warning("vertex web_search non-2xx",
                            status=resp.status_code, body=resp.text[:200])
                return "", []
            return _gemini_grounded(resp.json())
        except Exception as e:
            log.warning("vertex web_search failed", error=str(e)[:160])
            return "", []


def _gemini_grounded(data: dict) -> tuple:
    """(text, sources) out of a native generateContent grounded response."""
    cands = data.get("candidates") or []
    if not cands:
        return "", []
    cand = cands[0]
    parts = (cand.get("content") or {}).get("parts") or []
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    sources = []
    meta = cand.get("groundingMetadata") or {}
    for chunk in meta.get("groundingChunks") or []:
        web = (chunk or {}).get("web") or {}
        if web.get("uri"):
            sources.append({"url": web["uri"], "title": web.get("title", "")})
    return text, sources


def _url_citations(message) -> list:
    """Pull url_citation annotations off a web-search reply.

    Defensive on purpose: annotations are a newer, still-moving part of the
    openrouter surface, and a provider that returns none should cost us the
    links, not the answer.
    """
    out = []
    for note in getattr(message, "annotations", None) or []:
        note = note if isinstance(note, dict) else getattr(note, "model_dump",
                                                           lambda: {})()
        if note.get("type") != "url_citation":
            continue
        citation = note.get("url_citation") or {}
        url = citation.get("url")
        if url:
            out.append({"url": url, "title": citation.get("title", "")})
    return out


_client = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        s = get_settings()
        provider = getattr(s, "llm_provider", "openrouter")
        if provider == "vertex":
            _client = VertexLLMClient()
        elif provider == "gemini":
            _client = GeminiClient()
        else:
            gemini_key = (
                s.gemini_api_key
                or os.environ.get("GEMINI_API_KEY")
                or os.environ.get("GOOGLE_API_KEY")
                or os.environ.get("GOOGLE_GENAI_API_KEY")
            )
            if not s.openrouter_api_key and gemini_key:
                _client = GeminiClient()
            else:
                _client = LLMClient()
    return _client


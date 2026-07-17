import asyncio
import json
import random
from enum import Enum
from typing import Type, TypeVar

from openai import AsyncOpenAI, APIStatusError, APITimeoutError, APIConnectionError
from pydantic import BaseModel, ValidationError

from plantmind_core.config import get_settings
from plantmind_core.telemetry import get_logger, TokenMeter

log = get_logger("llm")
T = TypeVar("T", bound=BaseModel)

RETRYABLE = {429, 500, 502, 503, 529}


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        raw = raw.rsplit("```", 1)[0]
    return raw.strip()


class Tier(str, Enum):
    CHEAP = "cheap"
    MID = "mid"
    VISION = "vision"


class LLMClient:
    def __init__(self):
        s = get_settings()
        # max_retries=0: the SDK's built-in retry would bypass our semaphore
        self._client = AsyncOpenAI(
            api_key=s.openrouter_api_key,
            base_url=s.openrouter_base_url,
            timeout=s.llm_timeout_s,
            max_retries=0,
        )
        self._models = {
            Tier.CHEAP: s.llm_cheap,
            Tier.MID: s.llm_mid,
            Tier.VISION: s.llm_vision,
        }
        self._sem = asyncio.Semaphore(s.llm_max_concurrency)
        self._max_retries = s.llm_max_retries
        self.meter = TokenMeter()

    async def _create(self, messages, tier, max_tokens, temperature=0.0,
                      **extra):
        """The one place that talks to the provider: semaphore, retry,
        token accounting. Returns the raw response."""
        model = self._models[tier]
        for attempt in range(self._max_retries + 1):
            try:
                async with self._sem:
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
                if e.status_code not in RETRYABLE:
                    raise
                err = e
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
        return resp.choices[0].message.content or ""

    async def chat_with_tools(self, messages, tools, tier=Tier.MID,
                              max_tokens=2048):
        """One tool-calling turn: returns the assistant message, which may
        carry tool_calls to execute. The agent loop drives the iteration."""
        resp = await self._create(messages, tier, max_tokens,
                                  tools=tools, tool_choice="auto")
        return resp.choices[0].message

    async def stream(self, messages, tier=Tier.MID, max_tokens=2048,
                     temperature=0.0):
        """Yields answer text deltas as they arrive. No retry mid-stream:
        once tokens are flowing a failure is surfaced by ending the stream,
        because the caller has already shown partial output."""
        model = self._models[tier]
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
            return schema.model_validate_json(_strip_fences(raw))
        except ValidationError as e:
            # reasoning models burn thinking tokens from the same budget, so
            # truncated json usually means "not enough room" - retry bigger
            log.warning("structured output failed validation, retrying larger",
                        schema=schema.__name__, error=str(e)[:200])
            raw = await self.complete(convo, tier=tier, max_tokens=max_tokens * 2,
                                      response_format=response_format)
            return schema.model_validate_json(_strip_fences(raw))

    async def web_search(self, prompt: str, tier=Tier.CHEAP,
                         max_tokens=1024) -> tuple:
        """-> (text, [{'url', 'title'}]). Openrouter runs the search itself as
        a server-side tool and hands back the answer plus url_citation
        annotations, so there is no tool loop for us to drive.

        Billed per search on top of tokens, and it reaches the public internet,
        so this is not on the answer path - only a watcher that runs on a slow
        clock calls it.
        """
        resp = await self._create(
            [{"role": "user", "content": prompt}], tier, max_tokens,
            tools=[{"type": "web_search"}])
        message = resp.choices[0].message
        return message.content or "", _url_citations(message)

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
        _client = LLMClient()
    return _client

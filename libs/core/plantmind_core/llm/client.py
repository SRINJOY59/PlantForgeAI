import asyncio
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

    async def complete(self, messages, tier=Tier.CHEAP, max_tokens=2048,
                       temperature=0.0, response_format=None) -> str:
        model = self._models[tier]

        for attempt in range(self._max_retries + 1):
            try:
                async with self._sem:
                    resp = await self._client.chat.completions.create(
                        model=model,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        response_format=response_format,
                    )
                if resp.usage:
                    self.meter.record(model, resp.usage.prompt_tokens,
                                      resp.usage.completion_tokens)
                return resp.choices[0].message.content or ""
            except (APITimeoutError, APIConnectionError) as e:
                err = e
            except APIStatusError as e:
                if e.status_code not in RETRYABLE:
                    raise
                err = e
            if attempt == self._max_retries:
                raise err
            delay = min(2 ** attempt + random.random(), 30)
            log.warning("llm retry", model=model, attempt=attempt, delay=round(delay, 1))
            await asyncio.sleep(delay)

    async def structured(self, messages, schema: Type[T], tier=Tier.CHEAP,
                         max_tokens=4096) -> T:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "strict": True,
                "schema": schema.model_json_schema(),
            },
        }
        raw = await self.complete(messages, tier=tier, max_tokens=max_tokens,
                                  response_format=response_format)
        try:
            return schema.model_validate_json(raw)
        except ValidationError as e:
            log.warning("structured output failed validation, retrying",
                        schema=schema.__name__, error=str(e)[:200])
            raw = await self.complete(messages, tier=tier, max_tokens=max_tokens,
                                      response_format=response_format)
            return schema.model_validate_json(raw)

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
                                schema: Type[T], max_tokens=4096) -> T:
        content = [{"type": "text", "text": prompt}]
        for b64 in images_b64:
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            })
        return await self.structured([{"role": "user", "content": content}],
                                     schema, tier=Tier.VISION, max_tokens=max_tokens)


_client = None


def get_llm() -> LLMClient:
    global _client
    if _client is None:
        _client = LLMClient()
    return _client

import pytest
from openai import APIStatusError
from pydantic import BaseModel

from plantmind_core.llm.client import LLMClient, Tier
from conftest import FakeChatAPI, install_fake, make_response, make_status_error

MSGS = [{"role": "user", "content": "hi"}]


async def test_complete_returns_content_and_records_usage():
    llm = LLMClient()
    fake = FakeChatAPI(make_response("hello", prompt_tokens=7, completion_tokens=3))
    install_fake(llm, fake)

    out = await llm.complete(MSGS, tier=Tier.MID)

    assert out == "hello"
    counts = llm.meter.snapshot()
    (stats,) = counts.values()
    assert stats == {"prompt": 7, "completion": 3, "calls": 1}


async def test_complete_retries_on_429_then_succeeds():
    llm = LLMClient()
    fake = FakeChatAPI(make_status_error(429), make_status_error(503),
                       make_response("recovered"))
    install_fake(llm, fake)

    out = await llm.complete(MSGS)

    assert out == "recovered"
    assert len(fake.calls) == 3


async def test_complete_does_not_retry_client_errors():
    llm = LLMClient()
    fake = FakeChatAPI(make_status_error(400), make_response("never reached"))
    install_fake(llm, fake)

    with pytest.raises(APIStatusError):
        await llm.complete(MSGS)
    assert len(fake.calls) == 1


async def test_complete_raises_after_exhausting_retries():
    llm = LLMClient()
    llm._max_retries = 2
    fake = FakeChatAPI(*[make_status_error(429)] * 3)
    install_fake(llm, fake)

    with pytest.raises(APIStatusError):
        await llm.complete(MSGS)
    assert len(fake.calls) == 3


async def test_complete_omits_response_format_when_not_set():
    llm = LLMClient()
    fake = FakeChatAPI(make_response())
    install_fake(llm, fake)

    await llm.complete(MSGS)

    assert "response_format" not in fake.calls[0]


class Verdict(BaseModel):
    same_asset: bool
    reason: str


async def test_structured_parses_valid_json():
    llm = LLMClient()
    fake = FakeChatAPI(make_response('{"same_asset": true, "reason": "tag match"}'))
    install_fake(llm, fake)

    result = await llm.structured(MSGS, Verdict)

    assert result.same_asset is True
    rf = fake.calls[0]["response_format"]
    assert rf["type"] == "json_schema"
    assert rf["json_schema"]["strict"] is True
    assert rf["json_schema"]["name"] == "Verdict"


async def test_structured_retries_once_on_invalid_json():
    llm = LLMClient()
    fake = FakeChatAPI(make_response("not json at all"),
                       make_response('{"same_asset": false, "reason": "different unit"}'))
    install_fake(llm, fake)

    result = await llm.structured(MSGS, Verdict)

    assert result.same_asset is False
    assert len(fake.calls) == 2


async def test_structured_gives_up_after_second_bad_response():
    llm = LLMClient()
    fake = FakeChatAPI(make_response("garbage"), make_response("still garbage"))
    install_fake(llm, fake)

    with pytest.raises(Exception):
        await llm.structured(MSGS, Verdict)


async def test_vision_builds_image_content():
    llm = LLMClient()
    fake = FakeChatAPI(make_response("a pump"))
    install_fake(llm, fake)

    out = await llm.vision("what is this?", ["AAAA", "BBBB"])

    assert out == "a pump"
    content = fake.calls[0]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "what is this?"}
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,AAAA")
    assert len(content) == 3

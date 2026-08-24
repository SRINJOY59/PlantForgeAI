import pytest
from openai import APIStatusError
from pydantic import BaseModel

from plantmind_core.config import get_settings
from plantmind_core.llm.client import GeminiClient, LLMClient, Tier, get_llm
from plantmind_core.llm.embeddings import EmbeddingClient
from conftest import FakeChatAPI, install_fake, make_response, make_status_error

MSGS = [{"role": "user", "content": "hello gemini"}]


class Assessment(BaseModel):
    risk_level: str
    action_required: bool


def test_gemini_client_defaults(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-key")
    get_settings.cache_clear()

    client = GeminiClient()
    assert client._provider == "gemini"
    assert client._api_key == "gm-test-key"
    assert "generativelanguage.googleapis.com" in client._base_url
    # Against the settings, not a hard-coded model name: what this asserts is
    # that each tier is wired to its own setting. Pinning the literals meant a
    # routine model bump (3.5 -> 3.6 on cheap and vision) failed three tests
    # that have nothing to do with which model is current.
    s = get_settings()
    assert client._models[Tier.CHEAP] == s.gemini_llm_cheap
    assert client._models[Tier.MID] == s.gemini_llm_mid
    assert client._models[Tier.VISION] == s.gemini_llm_vision


def test_get_llm_selects_gemini_when_configured(monkeypatch):
    import plantmind_core.llm.client as client_mod
    client_mod._client = None

    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-key")
    get_settings.cache_clear()

    llm = get_llm()
    assert isinstance(llm, GeminiClient)
    assert llm._provider == "gemini"

    # Reset
    client_mod._client = None


async def test_gemini_complete_calls_model_and_records_tokens():
    client = GeminiClient(api_key="gm-test-key")
    fake = FakeChatAPI(make_response("Gemini response", prompt_tokens=15, completion_tokens=8))
    install_fake(client, fake)

    out = await client.complete(MSGS, tier=Tier.MID)

    assert out == "Gemini response"
    assert fake.calls[0]["model"] == get_settings().gemini_llm_mid
    stats = list(client.meter.snapshot().values())[0]
    assert stats == {"prompt": 15, "completion": 8, "calls": 1}


async def test_gemini_structured_output():
    client = GeminiClient(api_key="gm-test-key")
    fake = FakeChatAPI(make_response('{"risk_level": "medium", "action_required": true}'))
    install_fake(client, fake)

    res = await client.structured(MSGS, Assessment, tier=Tier.CHEAP)

    assert res.risk_level == "medium"
    assert res.action_required is True
    assert fake.calls[0]["model"] == get_settings().gemini_llm_cheap
    assert fake.calls[0]["response_format"]["type"] == "json_schema"


async def test_gemini_vision():
    client = GeminiClient(api_key="gm-test-key")
    fake = FakeChatAPI(make_response("P&ID pump tag P-101A"))
    install_fake(client, fake)

    out = await client.vision("Read tag from diagram", ["BASE64_IMAGE_DATA"])

    assert out == "P&ID pump tag P-101A"
    # the VISION setting: cheap and vision happen to name the same model today,
    # so asserting cheap here would still pass while silently accepting a
    # vision call routed to the wrong tier
    assert fake.calls[0]["model"] == get_settings().gemini_llm_vision
    content = fake.calls[0]["messages"][0]["content"]
    assert content[0]["text"] == "Read tag from diagram"
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,BASE64_IMAGE_DATA")


async def test_gemini_web_search_fallback():
    client = GeminiClient(api_key="gm-test-key")
    # Simulate a response from standard completion when web_search tool is called
    fake = FakeChatAPI(make_response("Standard search reply"))
    install_fake(client, fake)

    text, citations = await client.web_search("latest standard")
    assert text == "Standard search reply"


def test_gemini_embeddings_client(monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "gm-test-key")
    get_settings.cache_clear()

    embedder = EmbeddingClient()
    assert embedder._model == "text-embedding-004"
    assert "generativelanguage.googleapis.com" in embedder._base_url
    assert embedder._api_key == "gm-test-key"

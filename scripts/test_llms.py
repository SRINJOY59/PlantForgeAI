import asyncio
import os
import sys
import json
import base64
from pydantic import BaseModel, Field
import httpx

# Ensure core library is on sys.path
sys.path.insert(0, os.path.abspath("libs/core"))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from plantmind_core.config import get_settings
from plantmind_core.llm.client import LLMClient, Tier
from plantmind_core.llm.embeddings import EmbeddingClient
from plantmind_core.llm.agent import ToolAgent, Tool

# Create a small valid 1x1 PNG for vision testing
ONE_PIXEL_PNG_B64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="

class DiagnosticOutput(BaseModel):
    is_valid: bool
    summary: str = Field(description="One sentence summary of the test")

async def test_openrouter_auth(settings):
    print("\n--- 1. Testing OpenRouter Auth & Account Info ---")
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(f"{settings.openrouter_base_url}/auth/key", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                print("  [SUCCESS] OpenRouter API Key is VALID.")
                print(f"  Account details: {json.dumps(data.get('data', {}), indent=2)}")
                return True
            else:
                print(f"  [FAILED] OpenRouter returned status {resp.status_code}: {resp.text}")
                return False
        except Exception as e:
            print(f"  [ERROR] OpenRouter auth check error: {e}")
            return False

async def test_llm_cheap(llm, settings):
    print(f"\n--- 2. Testing CHEAP Tier ({settings.llm_cheap}) ---")
    # Basic completion
    try:
        raw_resp = await llm._client.chat.completions.create(
            model=settings.llm_cheap,
            messages=[{"role": "user", "content": "What is 2+2? Answer in one number."}],
            max_tokens=100,
            temperature=0.0
        )
        raw_content = raw_resp.choices[0].message.content
        print(f"  [RAW RESPONSE]: {repr(raw_content)}")
        
        res = await llm.complete(
            [{"role": "user", "content": "What is 2+2? Answer in one number."}],
            tier=Tier.CHEAP,
            max_tokens=100
        )
        print(f"  [SUCCESS] Text completion via llm.complete: '{res.strip()}'")
    except Exception as e:
        print(f"  [FAILED] Text completion error: {e}")

    # Structured JSON completion
    try:
        struct_res = await llm.structured(
            [{"role": "user", "content": "Confirm that the pump vibration is normal."}],
            schema=DiagnosticOutput,
            tier=Tier.CHEAP,
            max_tokens=200
        )
        print(f"  [SUCCESS] Structured output: is_valid={struct_res.is_valid}, summary='{struct_res.summary}'")
    except Exception as e:
        print(f"  [FAILED] Structured output error: {e}")

async def test_llm_mid(llm, settings):
    print(f"\n--- 3. Testing MID Tier ({settings.llm_mid}) ---")
    # Basic completion
    try:
        res = await llm.complete(
            [{"role": "user", "content": "Explain briefly in 1 sentence what a centrifugal pump cavitation issue is."}],
            tier=Tier.MID,
            max_tokens=100
        )
        print(f"  [SUCCESS] Text completion: '{res.strip()}'")
    except Exception as e:
        print(f"  [FAILED] Text completion error: {e}")

    # Streaming test
    try:
        stream_chunks = []
        async for chunk in llm.stream(
            [{"role": "user", "content": "Count 1 to 3."}],
            tier=Tier.MID,
            max_tokens=50
        ):
            stream_chunks.append(chunk)
        stream_text = "".join(stream_chunks).strip()
        print(f"  [SUCCESS] Stream test: '{stream_text}' ({len(stream_chunks)} chunks)")
    except Exception as e:
        print(f"  [FAILED] Streaming error: {e}")

    # Tool calling / Agent test
    try:
        def get_equipment_status(tag: str) -> str:
            return json.dumps({"tag": tag, "status": "RUNNING", "temp_c": 64.2})

        tool = Tool(
            name="get_equipment_status",
            description="Get telemetry status for an equipment tag",
            parameters={
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "description": "Asset tag name (e.g. P-101A)"}
                },
                "required": ["tag"]
            },
            fn=get_equipment_status
        )

        agent = ToolAgent(tools=[tool], tier=Tier.MID, max_steps=4, llm=llm)
        agent_res = await agent.run(
            system="You are an industrial telemetry assistant. Use tools when needed.",
            task="What is the status and temperature of equipment P-101A?"
        )
        print(f"  [SUCCESS] ToolAgent answer: '{agent_res.answer.strip()}' (steps={agent_res.steps}, trace_len={len(agent_res.trace)})")
    except Exception as e:
        print(f"  [FAILED] ToolAgent / tool calling error: {e}")

async def test_llm_vision(llm, settings):
    print(f"\n--- 4. Testing VISION Tier ({settings.llm_vision}) ---")
    try:
        res = await llm.vision(
            prompt="What is the dominant color of this 1x1 image? Answer in 1 short phrase.",
            images_b64=[ONE_PIXEL_PNG_B64],
            max_tokens=60
        )
        print(f"  [SUCCESS] Vision response: '{res.strip()}'")
    except Exception as e:
        print(f"  [FAILED] Vision error: {e}")

async def test_embeddings(settings):
    print(f"\n--- 5. Testing Embeddings ({settings.embedding_model}) ---")
    embedder = EmbeddingClient()
    try:
        sample_texts = [
            "Centrifugal pump P-101A bearing temperature high alarm",
            "Heat exchanger E-201 tube side pressure drop inspection"
        ]
        vectors = await embedder.embed(sample_texts)
        if vectors and len(vectors) == 2:
            dim = len(vectors[0])
            print(f"  [SUCCESS] Generated 2 embeddings successfully. Dimension: {dim} (Expected: {settings.embedding_dim})")
            if dim != settings.embedding_dim:
                print(f"  [WARNING] Embedding dimension mismatch! Returned {dim} != Configured {settings.embedding_dim}")
        else:
            print(f"  [FAILED] Embeddings returned unexpected count: {len(vectors) if vectors else 0}")
    except Exception as e:
        print(f"  [FAILED] Embedding error: {e}")

async def test_deepgram():
    key = os.environ.get("DEEPGRAM_API_KEY", "")
    if not key:
        print("\n--- 6. Deepgram Voice API (Skipped - no DEEPGRAM_API_KEY configured) ---")
        return
    print("\n--- 6. Testing Deepgram Voice API ---")
    headers = {
        "Authorization": f"Token {key}"
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get("https://api.deepgram.com/v1/projects", headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                print("  [SUCCESS] Deepgram API key is VALID.")
                print(f"  Projects: {[p.get('name') for p in data.get('projects', [])]}")
            else:
                print(f"  [FAILED] Deepgram returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            print(f"  [ERROR] Deepgram check error: {e}")

async def main():
    settings = get_settings()
    print("==================================================")
    print("          PLANTMIND LLM & AI SUBSYSTEM CHECK       ")
    print("==================================================")
    print(f"OpenRouter Base URL : {settings.openrouter_base_url}")
    print(f"OpenRouter API Key  : {'*' * 8 + settings.openrouter_api_key[-6:] if settings.openrouter_api_key else 'NOT SET'}")
    print(f"Cheap Tier Model    : {settings.llm_cheap}")
    print(f"Mid Tier Model      : {settings.llm_mid}")
    print(f"Vision Tier Model   : {settings.llm_vision}")
    print(f"Embedding Model     : {settings.embedding_model}")
    print(f"Embedding Base URL  : {settings.embedding_base_url}")
    print(f"Embedding Dim       : {settings.embedding_dim}")
    print("==================================================")

    auth_ok = await test_openrouter_auth(settings)
    
    llm = LLMClient()
    
    await test_llm_cheap(llm, settings)
    await test_llm_mid(llm, settings)
    await test_llm_vision(llm, settings)
    await test_embeddings(settings)
    await test_deepgram()
    
    print("\n==================================================")
    print("Token Usage Summary:")
    print(json.dumps(llm.meter.snapshot(), indent=2))
    print("==================================================")

if __name__ == "__main__":
    asyncio.run(main())

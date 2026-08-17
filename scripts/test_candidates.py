import asyncio
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("libs/core"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from plantmind_core.llm.client import LLMClient, Tier
from pydantic import BaseModel

class ClassificationResult(BaseModel):
    category: str
    confidence: float

async def test_candidates():
    llm = LLMClient()
    models = [
        "openai/gpt-oss-20b:free",
        "nvidia/nemotron-3-nano-30b-a3b:free",
        "nvidia/nemotron-nano-9b-v2:free",
        "google/gemma-4-26b-a4b-it:free",
        "nvidia/nemotron-3-super-120b-a12b:free",
    ]
    print("\n--- Testing google/gemma-4-26b-a4b-it:free for structured output ---")
    try:
        class Triage(BaseModel):
            severity: str
            action_needed: bool
            reason: str

        res = await llm.structured(
            messages=[{"role": "user", "content": "Triage this alarm: Pump P-101A bearing temp 92C (trip limit 95C)."}],
            schema=Triage,
            tier=Tier.VISION # Uses gemma-4-26b-a4b-it
        )
        print(f"  [Structured Output]: severity={res.severity}, action_needed={res.action_needed}, reason='{res.reason}'")
    except Exception as e:
        print(f"  [Structured Output FAILED]: {e}")
    for m in models:
        print(f"\n--- Testing model: {m} ---")
        try:
            resp = await llm._client.chat.completions.create(
                model=m,
                messages=[{"role": "user", "content": "Say HELLO in exactly 1 word."}],
                max_tokens=30,
                temperature=0.0
            )
            txt = resp.choices[0].message.content or ""
            print(f"  [Simple Chat]: {repr(txt.strip())}")
        except Exception as e:
            print(f"  [Simple Chat FAILED]: {e}")

asyncio.run(test_candidates())

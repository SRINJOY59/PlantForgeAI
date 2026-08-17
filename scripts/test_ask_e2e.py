import asyncio
import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, os.path.abspath("libs/core"))
sys.path.insert(0, os.path.abspath("services/retrieval"))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from retrieval.service import RetrievalService

async def test_ask():
    print("\n--- Testing RetrievalService.ask() end-to-end ---")
    try:
        service = RetrievalService.from_settings()
        question = "What should I check if pump P-101A has high bearing temperature?"
        print(f"Question: {question}")
        
        answer = await service.ask(question=question)
        print("\n[SUCCESS] Received Answer:")
        print(f"Text: {answer.text}")
        print(f"Confidence: {answer.confidence}")
        print(f"Citations: {len(answer.citations)}")
    except Exception as e:
        print(f"\n[FAILED] RetrievalService.ask error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_ask())

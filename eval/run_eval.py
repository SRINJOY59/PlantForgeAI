"""Run the golden QA set through the live retrieval service and score it.
Produces the numbers the system is judged on: answer accuracy (LLM judge),
citation hit rate (mechanical), mode routing accuracy, time to answer.

usage (stack up, graph populated, key in .env):
    python -m eval.run_eval
    python -m eval.run_eval --limit 3        quick spin
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from plantmind_core.llm import Tier

REPO = Path(__file__).resolve().parents[1]
GOLDEN = REPO / "eval" / "golden" / "qa.jsonl"
RESULTS = REPO / "eval" / "results"

JUDGE_PROMPT = """You are grading a plant knowledge assistant.

QUESTION: {question}

REFERENCE ANSWER (ground truth): {expected}

ASSISTANT'S ANSWER: {actual}

Verdict rules: "correct" if the assistant's answer contains the key facts
of the reference (extra correct detail is fine); "partial" if some key
facts are present but others are missing or muddled; "wrong" if key facts
are absent or contradicted."""


class Judgement(BaseModel):
    verdict: Literal["correct", "partial", "wrong"]
    reason: str


class EvalRunner:
    def __init__(self, service, judge_llm, doc_filenames: dict):
        self._service = service
        self._judge = judge_llm
        self._doc_filenames = doc_filenames   # doc_id -> source filename

    async def run(self, cases: list) -> list:
        results = []
        for case in cases:
            started = time.perf_counter()
            answer = await self._service.ask(case["question"])
            elapsed = time.perf_counter() - started

            judgement = await self._judge_one(case, answer.text)
            cited_files = {self._doc_filenames.get(c.doc_id, c.doc_id)
                           for c in answer.citations}
            results.append({
                "id": case["id"],
                "question": case["question"],
                "verdict": judgement.verdict,
                "reason": judgement.reason,
                "citation_hit": citation_hit(cited_files, case["source_docs"]),
                "mode_expected": case["mode"],
                "mode_actual": answer.mode.value,
                "seconds": round(elapsed, 2),
                "answer": answer.text,
            })
            print(f"  {case['id']}  {judgement.verdict:8s} "
                  f"cite={'Y' if results[-1]['citation_hit'] else 'n'} "
                  f"mode={answer.mode.value:6s} {elapsed:5.1f}s")
        return results

    async def _judge_one(self, case, actual: str) -> Judgement:
        return await self._judge.structured(
            [{"role": "user", "content": JUDGE_PROMPT.format(
                question=case["question"], expected=case["expected_answer"],
                actual=actual)}],
            Judgement, tier=Tier.CHEAP)


def citation_hit(cited_files: set, expected_docs: list) -> bool:
    """Did at least one citation land on an expected source document?"""
    return any(exp in cited for exp in expected_docs for cited in cited_files)


def summarize(results: list) -> dict:
    n = len(results)
    verdicts = [r["verdict"] for r in results]
    return {
        "cases": n,
        "correct": verdicts.count("correct"),
        "partial": verdicts.count("partial"),
        "wrong": verdicts.count("wrong"),
        "accuracy": round(verdicts.count("correct") / n, 2) if n else 0,
        "citation_hit_rate": round(
            sum(r["citation_hit"] for r in results) / n, 2) if n else 0,
        "mode_match_rate": round(
            sum(r["mode_expected"] == r["mode_actual"] for r in results) / n,
            2) if n else 0,
        "mean_seconds": round(
            sum(r["seconds"] for r in results) / n, 2) if n else 0,
    }


def main():
    from plantmind_core.llm import get_llm
    from retrieval.graph_reader import GraphReader
    from retrieval.service import RetrievalService

    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    cases = [json.loads(l) for l in GOLDEN.read_text(encoding="utf-8")
             .splitlines() if l.strip()][:limit]

    reader = GraphReader.from_settings()
    service = RetrievalService.from_settings()
    doc_filenames = {r["id"].removeprefix("doc:"): r.get("filename") or ""
                     for r in reader.documents()}

    print(f"running {len(cases)} golden questions...\n")
    runner = EvalRunner(service, get_llm(), doc_filenames)
    results = asyncio.run(runner.run(cases))

    summary = summarize(results)
    print("\n=== summary ===")
    for key, value in summary.items():
        print(f"  {key:20s} {value}")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({"summary": summary, "results": results},
                              indent=2), encoding="utf-8")
    print(f"\nfull results: {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()

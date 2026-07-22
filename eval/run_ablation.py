"""Retrieval ablation: the same golden set answered three ways.

run_eval.py measures the system as deployed, with the router choosing a
strategy per question. This forces every question through one strategy at a
time, so the only variable is retrieval:

    vector   dense similarity only            (the conventional-RAG baseline)
    local    seed neighbourhood + hybrid text
    path     flow-pruned PathRAG              (the full method)

Everything else is held constant - same graph, same embeddings, same judge,
same generation step - which is what makes the comparison a controlled
ablation rather than a comparison of two different systems on two different
corpora. Published figures from other papers are deliberately NOT reported
beside these: they were produced on different corpora under different judging
protocols, and placing them in the same table would compare incommensurable
things.

usage (stack up, graph populated, key in .env):
    python -m eval.run_ablation
    python -m eval.run_ablation --limit 5           quick spin
    python -m eval.run_ablation --modes vector,path only two arms
"""

import asyncio
import json
import sys
import time
from pathlib import Path

from plantmind_core.llm import get_llm
from plantmind_core.schemas import QueryMode

from eval.run_eval import GOLDEN, RESULTS, EvalRunner, citation_hit  # noqa: F401

REPO = Path(__file__).resolve().parents[1]
ALL_MODES = ("vector", "local", "path")


class FixedRouter:
    """Pins the retrieval strategy regardless of the question's shape.

    Falls back to vector when nothing linked: local and path both need at
    least one seed node, and forcing them without one would crash rather than
    measure anything. Those cases are counted as fallbacks and reported, so a
    mode's score is never quietly inflated by questions it did not actually
    handle.
    """

    def __init__(self, mode: QueryMode):
        self.mode = mode
        self.fallbacks = 0

    def route(self, question: str, seeds: list) -> QueryMode:
        if not seeds and self.mode is not QueryMode.VECTOR:
            self.fallbacks += 1
            return QueryMode.VECTOR
        return self.mode


def build_service(mode: QueryMode):
    """A retrieval service pinned to one strategy, with the cache disabled.

    Disabling the answer cache is essential: a cache hit returns a stored
    answer without retrieving anything, so a warm cache would make every arm
    of the ablation look identical.
    """
    from retrieval.service import RetrievalService

    service = RetrievalService.from_settings()
    router = FixedRouter(mode)
    service._router = router
    service._cache = None
    return service, router


def summarize_arm(results: list, fallbacks: int) -> dict:
    n = len(results) or 1
    verdicts = [r["verdict"] for r in results]
    # scored as correct + half credit for partial, so an arm that is vaguely
    # right everywhere does not tie one that is exactly right half the time
    score = (verdicts.count("correct") + 0.5 * verdicts.count("partial")) / n
    return {
        "cases": len(results),
        "correct": verdicts.count("correct"),
        "partial": verdicts.count("partial"),
        "wrong": verdicts.count("wrong"),
        "accuracy": round(verdicts.count("correct") / n, 3),
        "weighted_score": round(score, 3),
        "citation_hit_rate": round(
            sum(r["citation_hit"] for r in results) / n, 3),
        "mean_seconds": round(sum(r["seconds"] for r in results) / n, 2),
        "vector_fallbacks": fallbacks,
    }


def by_expected_mode(results: list) -> dict:
    """Accuracy split by the question's intended strategy.

    This is the row that carries the argument. A path-retrieval arm is
    expected to beat the baseline on multi-entity causal questions and to tie
    on single-fact lookups - if it wins everywhere by the same margin, the
    golden set is probably not discriminating between question types.
    """
    out = {}
    for expected in ("vector", "local", "path"):
        subset = [r for r in results if r["mode_expected"] == expected]
        if subset:
            out[expected] = {
                "n": len(subset),
                "accuracy": round(
                    sum(r["verdict"] == "correct" for r in subset) / len(subset), 3),
            }
    return out


def print_table(report: dict):
    modes = list(report["arms"])
    width = max(len(m) for m in modes) + 2

    def row(label, fn):
        cells = "".join(f"{fn(report['arms'][m]):>14}" for m in modes)
        print(f"  {label:<26}{cells}")

    print("\n" + "=" * (26 + 14 * len(modes) + 2))
    print(f"  {'metric':<26}" + "".join(f"{m:>14}" for m in modes))
    print("=" * (26 + 14 * len(modes) + 2))
    row("accuracy (correct)", lambda a: f"{a['accuracy']:.1%}")
    row("weighted (partial=0.5)", lambda a: f"{a['weighted_score']:.1%}")
    row("citation hit rate", lambda a: f"{a['citation_hit_rate']:.1%}")
    row("mean seconds", lambda a: f"{a['mean_seconds']:.2f}")
    row("vector fallbacks", lambda a: str(a["vector_fallbacks"]))
    print("-" * (26 + 14 * len(modes) + 2))
    print("  accuracy by question type")
    for expected in ("vector", "local", "path"):
        present = [m for m in modes if expected in report["by_expected"][m]]
        if not present:
            continue
        cells = ""
        for m in modes:
            entry = report["by_expected"][m].get(expected)
            cells += f"{entry['accuracy']:>13.1%} " if entry else f"{'-':>14}"
        n = report["by_expected"][modes[0]][expected]["n"]
        print(f"    {expected + f' (n={n})':<24}{cells}")
    print("=" * (26 + 14 * len(modes) + 2))


def main():
    argv = sys.argv
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else None
    modes = (argv[argv.index("--modes") + 1].split(",")
             if "--modes" in argv else list(ALL_MODES))

    cases = [json.loads(line) for line in
             GOLDEN.read_text(encoding="utf-8").splitlines() if line.strip()]
    cases = cases[:limit]

    from retrieval.graph_reader import GraphReader
    reader = GraphReader.from_settings()
    doc_filenames = {r["id"].removeprefix("doc:"): r.get("filename") or ""
                     for r in reader.documents()}
    judge = get_llm()

    report = {"cases": len(cases), "arms": {}, "by_expected": {}, "raw": {}}

    for name in modes:
        mode = QueryMode(name)
        print(f"\n--- arm: {name} ({len(cases)} questions) ---")
        service, router = build_service(mode)
        results = asyncio.run(EvalRunner(service, judge, doc_filenames).run(cases))

        report["arms"][name] = summarize_arm(results, router.fallbacks)
        report["by_expected"][name] = by_expected_mode(results)
        report["raw"][name] = results

    print_table(report)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"ablation_{time.strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nfull results: {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()

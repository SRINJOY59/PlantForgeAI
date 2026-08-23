# Appendix A3 — Evaluation Methodology & Metrics

Source of truth: `eval/run_eval.py`, `eval/run_ablation.py`,
`eval/golden/qa.jsonl`, `eval/results/*.json`.

---

## A3.1 Golden set

**28 hand-written question–answer cases** over the seeded corpus. Each case:

```jsonc
{
  "id":              "q07",
  "question":        "Why did P-101A trip last month?",
  "expected_answer": "<reference answer containing the key facts>",
  "source_docs":     ["incident_report_IR-2026-014.md", "work_orders.csv"],
  "mode":            "path"        // expected routing decision
}
```

The `source_docs` and `mode` fields are what make this more than an accuracy
number: they let citation behaviour and routing be scored **mechanically**,
with no judge in the loop and therefore no judge variance.

---

## A3.2 Harness

```
   ┌────────────────────────────────────────────────────────────────┐
   │  for case in golden:                                           │
   │                                                                │
   │      t₀ ← perf_counter()                                       │
   │      answer ← RetrievalService.ask(case.question)              │
   │      Δt ← perf_counter() − t₀           ▸ latency               │
   │                                                                │
   │      verdict ← JudgeLLM(question, expected, answer.text)       │
   │                        ▸ {correct | partial | wrong}           │
   │                                                                │
   │      cited_files ← { doc_id → filename  for c in citations }   │
   │      hit ← cited_files ∩ case.source_docs ≠ ∅                  │
   │                                                                │
   │      mode_ok ← (answer.mode == case.mode)                      │
   └────────────────────────────────────────────────────────────────┘
```

Citations are resolved **doc_id → filename** before comparison, so the metric
is stated in terms a human wrote in the golden file rather than content hashes.

---

## A3.3 Metric definitions

Let `N` = number of cases, `vᵢ ∈ {correct, partial, wrong}`.

**Answer accuracy** — strict; `partial` earns nothing:

```
                  | { i : vᵢ = correct } |
    Accuracy  =  ──────────────────────────
                            N
```

**Citation hit rate** — did the answer cite at least one document the golden
case names as a genuine source? Mechanical, no LLM:

```
                       1
    CHR       =       ───  Σ  𝟙[ cited(i) ∩ expected(i) ≠ ∅ ]
                       N   i
```

**Mode match rate** — did the router pick the intended strategy?

```
                       1
    MMR       =       ───  Σ  𝟙[ mode_actual(i) = mode_expected(i) ]
                       N   i
```

**Mean latency** — end-to-end, retrieval + generation, cache disabled:

```
                       1
    T̄         =       ───  Σ  Δtᵢ            [seconds]
                       N   i
```

**Grounding distribution** — read off `§A1.8`; `unverified` is the one that
matters, because it is a fabricated provenance claim rather than a wrong fact:

```
    G  =  ( |documents| , |general| , |unverified| ) / N
```

---

## A3.4 Judge protocol

A cheap-tier LLM returns a **structured** verdict (Pydantic-validated, not free
text), under fixed rubric:

```
    correct   assistant's answer contains the key facts of the reference.
              Extra correct detail is not penalised.
    partial   some key facts present, others missing or muddled.
    wrong     key facts absent or contradicted.
```

Judging only the *text* against a *reference* keeps the judge away from
citations, mode and latency — those three are measured mechanically, so a
drifting judge cannot move them.

---

## A3.5 Measured results

Recorded runs, `eval/results/`. The first five are a 14-case subset used while
the pipeline was being built; the last two are the full 28-case set.

```
  run              N    Accuracy  CitationHit  ModeMatch   Mean s   routing mix
  ───────────────  ──   ────────  ───────────  ─────────   ──────   ─────────────────
  172246           14     0.50       0.29        0.29       9.8     L6 / P2 / V6
  175404           14     0.64       0.50        0.93      10.0     L6 / P3 / V5
  180626           14     0.79       0.79        0.93      12.7     L6 / P3 / V5
  181341           14     0.86       0.79        1.00      14.4     L6 / P4 / V4
  181912           14     0.86       0.79        1.00      10.7     L6 / P4 / V4
  ───────────────  ──   ────────  ───────────  ─────────   ──────   ─────────────────
  183025           28     0.61       0.82        0.93      10.0     L14 / P7 / V7
  183028      ★    28     0.64       0.82        0.93      11.2     L14 / P7 / V7
```

★ = headline run. Verdict split: **18 correct · 6 partial · 4 wrong**.

Trajectory on the 14-case subset:

```
  Accuracy                                   CitationHit
  1.0 ┤                                      1.0 ┤
      │              ●───●                       │         ●───●───●
  0.8 ┤         ●                            0.8 ┤    ●
      │                                          │
  0.6 ┤    ●                                 0.6 ┤
      │                                          │
  0.4 ┤●                                     0.4 ┤ ●
      │                                          │
  0.2 ┤                                      0.2 ┤●
      └─┬───┬───┬───┬───┬─                       └─┬───┬───┬───┬───┬─
        1   2   3   4   5                          1   2   3   4   5
```

**Reading these honestly.** Accuracy is *lower* on the 28-case set (0.64) than
on the 14-case subset (0.86). That is not a regression — the second set adds
harder multi-hop and aggregate questions. The subset is not a valid basis for
claiming 0.86; the 28-case figure is the one to quote.

Citation hit rate (0.82) exceeding accuracy (0.64) is the expected signature of
a working retrieval layer: the system **finds the right documents more often
than it reasons correctly over them**. The remaining loss is in generation and
synthesis, not retrieval.

---

## A3.6 Ablation design

`run_ablation.py` pins the router to one strategy so retrieval is the **only**
variable:

```
   ┌─────────────┬──────────────────────────────────────────────────┐
   │  arm        │  retrieval                                       │
   ├─────────────┼──────────────────────────────────────────────────┤
   │  vector     │  dense ANN over chunk embeddings only            │
   │             │  ← the conventional-RAG baseline                 │
   ├─────────────┼──────────────────────────────────────────────────┤
   │  local      │  seed neighbourhood + hybrid exact/semantic text │
   ├─────────────┼──────────────────────────────────────────────────┤
   │  path       │  flow-pruned PathRAG                             │
   │             │  ← the full method                               │
   └─────────────┴──────────────────────────────────────────────────┘

   held constant:  same graph · same embeddings · same judge ·
                   same generation step · answer cache DISABLED
```

Two design decisions worth stating in the presentation:

1. **Fallback accounting.** `local` and `path` both require ≥1 linked seed.
   When nothing links, the arm falls back to `vector` and the fallback is
   *counted and reported* — so an arm is never quietly credited for questions
   it did not actually handle.

2. **No cross-paper comparison.** Published PathRAG/GraphRAG figures are
   deliberately **not** printed beside these numbers. They were produced on
   different corpora under different judging protocols; putting them in one
   table would compare incommensurable things.

**Status:** the harness and arms are implemented; `eval/results/` currently
holds only deployed-router runs. The per-arm comparison has not been recorded
and should be run before any ablation claim is made in the presentation.

---

## A3.7 Metric summary card

```
   ╔══════════════════════════════════════════════════════════════╗
   ║  PlantForge.ai — retrieval evaluation, 28-case golden set     ║
   ╠══════════════════════════════════════════════════════════════╣
   ║                                                              ║
   ║    Answer accuracy (strict)         0.64    18/28 correct    ║
   ║    Citation hit rate                0.82    mechanical       ║
   ║    Mode routing accuracy            0.93    mechanical       ║
   ║    Mean time to answer             11.2 s   cache off        ║
   ║                                                              ║
   ║    Verdicts     correct 18  ·  partial 6  ·  wrong 4         ║
   ║    Routing mix  local 14    ·  path 7     ·  vector 7        ║
   ║                                                              ║
   ╚══════════════════════════════════════════════════════════════╝
```

Reproduce with:

```bash
python -m eval.run_eval
```

# Appendix A1 — Modified PathRAG: Formal Definition

Every symbol below maps to running code. Source of truth:
`services/retrieval/{linker,router,pathfinder,pruner,assembler,grounding}.py`.

---

## A1.1 Notation

Let the knowledge graph be a directed, typed, attributed multigraph

```
    G = (V, E, τ, κ)

    V              set of entity nodes (Equipment, Instrument, FailureMode,
                   Procedure, RegulationClause, Document, Chunk, Line, …)
    E ⊆ V × V      directed edges
    τ : E → T      edge-type labelling, T = {CONNECTED_TO, HAS_FAILURE,
                   FIXED_BY, GOVERNED_BY, MENTIONED_IN, PART_OF, FEEDS}
    κ : E → [0,1]  extraction confidence carried on each edge's provenance
```

A **path** of length ℓ is `p = (e₁, e₂, …, e_ℓ)`, edges consecutive,
`src(e₁) = s` a seed. Write `E_p` for the edge set of `p`.

---

## A1.2 Stage 1 — Query linking (seed identification)

`QueryLinker` maps a natural-language question `q` to seed nodes `S(q) ⊆ V`
by three ordered strategies. The key property is that **query-side and
write-side normalisation are the same function** `ν`, so a tag written as
`P 101 A`, `p-101a` or `P101A` collapses to one identifier at both ends:

```
    S(q) = ν(TAG(q))                                    exact tag match
         ∪ { v : name(v) ≈ m, m ∈ STD(q) }              standard codes
         ∪ { v : name(v) ≈ φ, φ ∈ TITLE(q) }  if empty  title-case fallback

    TAG    regex tag extractor + normaliser  (plantmind_core.tags)
    STD    /OISD[-\s]?STD[-\s]?\d+ | IS\s?\d{3,5} | IBR/i
    TITLE  /\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b/
```

The third branch fires **only when the first two yield nothing** — it is a
recall net for questions like *"the seal replacement procedure"* that name no
tag at all.

---

## A1.3 Stage 2 — Mode routing

A deterministic rule chooses the retrieval strategy. No LLM call, so it costs
nothing and cannot drift:

```
                      ┌─────────────────┐
                      │  question q     │
                      └────────┬────────┘
                               │
                       S(q) = QueryLinker(q)
                               │
                  ┌────────────┴────────────┐
                  │      |S(q)| = 0 ?       │
                  └────┬───────────────┬────┘
                   yes │               │ no
                       ▼               ▼
                 ╔═══════════╗  ┌──────────────────────────┐
                 ║  VECTOR   ║  │ |S(q)| ≥ 2  ∨  q ∈ CAUSAL│
                 ╚═══════════╝  └────┬────────────────┬────┘
                                 yes │                │ no
                                     ▼                ▼
                               ╔═══════════╗    ╔═══════════╗
                               ║   PATH    ║    ║   LOCAL   ║
                               ╚═══════════╝    ╚═══════════╝

    CAUSAL = {why, cause, caused, lead, led, result, because, affect,
              impact, downstream, upstream, "explain how", could, trigger}
```

Formally:

```
                ⎧ VECTOR   if |S(q)| = 0
    M(q)   =    ⎨ PATH     if |S(q)| ≥ 2  ∨  q ∩ CAUSAL ≠ ∅
                ⎩ LOCAL    otherwise
```

`PATH` degrades to `VECTOR` at runtime if the graph yields no candidate paths —
so the mode is a hypothesis, not a commitment.

---

## A1.4 Stage 3 — Constrained path enumeration

The central modification versus stock PathRAG. Unrestricted enumeration is
useless on a document graph, because **every pair of entities is connected
through some document that mentions both** — `MENTIONED_IN` makes the graph
almost complete and every path meaningless.

So the admissible edge-type set is a function of the question:

```
    T(q)  =  ⎧ T_comp ∪ T_causal   if q ∩ W_comp ≠ ∅
             ⎩ T_causal            otherwise

    T_causal = {CONNECTED_TO, HAS_FAILURE, FIXED_BY}
    T_comp   = {GOVERNED_BY, MENTIONED_IN}
    W_comp   = {standard, regulation, compliance, overdue, inspection,
                governed, oisd, ibr, statutory}
```

Candidate set, with `h_max = 4` hops (`pathrag_max_hops`):

```
              ⎧ ⋃         Π(sᵢ, sⱼ; T(q), h_max)              if |S| ≥ 2
              ⎪  i<j
    P(q)  =   ⎨
              ⎪ Π→(s₁; L_ev, T(q), h_max)                     if |S| = 1
              ⎩

            ∪  ⋃          Π→(s; {Equipment, Instrument},
               s ∈ S[:4]        {CONNECTED_TO}, min(2, h_max))
```

- `Π(a,b;·)` — all simple paths `a ⇝ b` using only edge types in `T(q)`
- `Π→(a,L;·)` — paths outward from `a` terminating on any node labelled in `L`
- `L_ev = {FailureMode, Procedure, RegulationClause}` (evidence-bearing labels)

The final union is the **process-neighbourhood term**. Between-paths stop *at*
the seeds, but a question like *"what is downstream of A and B"* needs each
seed's local process context too — so a bounded 2-hop `CONNECTED_TO` expansion
is added per seed, capped at the first four seeds.

---

## A1.5 Stage 4 — Flow-based pruning (the scoring core)

Each seed injects **one unit of resource** into the graph. Traversing an edge
attenuates it three ways. The score of a path is the resource that survives:

```
                          ┌                                  ┐
                          │      α  ·  max(κ(e), κ_min)      │
    flow(p)   =     ∏     │  ──────────────────────────────  │
                  e ∈ p   │    max( d_out(src(e)) − 1, 1 )   │
                          └                                  ┘
```

| term | value | meaning |
|---|---|---|
| `α` | `0.8` | **decay** — each hop is weaker evidence than the last |
| `κ(e)` | edge prop | **extraction confidence** — a rule-parsed table row outranks a hedged LLM extraction |
| `κ_min` | `0.3` | confidence **weakens** a path, never erases it |
| `d_out(v)` | degree in `T(q)` | **branching** — resource splits across siblings |
| `−1` | | discounts the edge we arrived on |
| `max(·,1)` | | a leaf must not divide by zero |

Two properties follow directly and are what make the score usable:

1. **Monotone decreasing in length.** Since every factor `< 1` for `α = 0.8`
   and `κ ≤ 1`, `flow(p)` shrinks with each hop — long chains of inference are
   automatically distrusted without a hard hop cutoff doing the work.

2. **Hub penalisation.** A node with out-degree 40 divides incoming resource by
   39. Paths that route through a hub (a plant-wide standard, a document
   everything mentions) are suppressed relative to paths through specific,
   low-degree structure — which is exactly the evidence an engineer wants.

Worked example, `α = 0.8`:

```
    P-101A ──CONNECTED_TO──▶ E-201 ──HAS_FAILURE──▶ FOULING
            d_out=3, κ=1.0          d_out=2, κ=0.85

    flow =  (0.8 · 1.00 / max(3−1,1))  ·  (0.8 · 0.85 / max(2−1,1))
         =  (0.8 / 2)                  ·  (0.68 / 1)
         =  0.400                      ·  0.680
         =  0.272
```

---

## A1.6 Stage 5 — Redundancy suppression

High-flow paths are frequently near-duplicates sharing a trunk. Greedy
selection with a Jaccard-style overlap test on **edge sets**, normalised by the
*smaller* path so a short path is not absorbed by a long one containing it:

```
                        | E_p ∩ E_q |
    overlap(p, q)  =  ──────────────────  ,      θ = 0.7
                      min(|E_p|, |E_q|)
```

```
    ALGORITHM  Prune(P, d_out)
    ─────────────────────────────────────────────────────────
    1  for p ∈ P:  p.score ← flow(p)
    2  K ← ∅
    3  for p ∈ sort(P, by score, descending):
    4      if |K| ≥ k_top:            break          ▸ k_top = 15
    5      if E_p = ∅:                continue       ▸ degenerate
    6      if ∃ q ∈ K : overlap(p,q) > θ:  continue
    7      K ← K ∪ {p}
    8  return K
```

Complexity `O(|P| log|P| + k_top·|P|)`; with `k_top = 15` the second term is
effectively linear.

---

## A1.7 Full pipeline

```
   q ──▶ Condenser ──▶ q'          follow-up → standalone question
                        │
                        ├──▶ embed(q') ──▶ AnswerCache  ──hit──▶ answer
                        │                  (semantic, cosine)
                        ▼
                    QueryLinker ──▶ S(q')
                        │
                        ▼
                    ModeRouter ──▶ M ∈ {VECTOR, LOCAL, PATH}
                        │
        ┌───────────────┼────────────────────┐
        ▼               ▼                    ▼
    ┌────────┐    ┌──────────┐        ┌─────────────┐
    │ VECTOR │    │  LOCAL   │        │    PATH     │
    │        │    │          │        │             │
    │ ANN    │    │ 1-hop    │        │ PathFinder  │  ◀── §A1.4
    │ over   │    │ relations│        │      ↓      │
    │ Chunk  │    │  + hybrid│        │ FlowPruner  │  ◀── §A1.5/6
    │ embeds │    │    text  │        │      ↓      │
    │        │    │  + hist  │        │ Assembler   │
    └───┬────┘    └────┬─────┘        └──────┬──────┘
        │              │                     │
        │              │              ∅ paths│→ degrade to VECTOR
        └──────────────┴─────────────────────┘
                       │
                       ▼
              + PlantDigest (live aggregate Cypher, if q ∩ W_dig ≠ ∅)
              + Corrections block  (engineer overrides, placed FIRST)
                       │
                       ▼
                   Answerer ──▶ text ──▶ Grounding ──▶ (grounding, confidence)
```

---

## A1.8 Grounding classification

Confidence is **not** a function of how much was retrieved — an earlier version
used `len(evidence)` and two irrelevant chunks scored "high confidence". It is
read off what the answer *cited*, which is a checkable provenance claim.

Let `A` = document ids placed in the context, `C` = ids the answer cites
(recovered by regex, with prefix resolution for truncated hashes, `MIN_PREFIX = 6`):

```
                    ⎧ (unverified, low)      if ∃c ∈ C : resolve(c, A) = ∅
    g(text, A)  =   ⎨ (general,    medium)   if C = ∅
                    ⎪ (documents,  high)     if |C| ≥ 2
                    ⎩ (documents,  medium)   if |C| = 1
```

```
    ┌───────────────────────────────────────────────────────────┐
    │  cited a doc NOT in context  →  unverified   ▮ red        │
    │       fabricated provenance — the only case that is a bug │
    ├───────────────────────────────────────────────────────────┤
    │  cited nothing               →  general      ▮ amber      │
    │       answered from model knowledge; badge says so        │
    ├───────────────────────────────────────────────────────────┤
    │  cited ≥ 2 context docs      →  documents    ▮ green high │
    │  cited 1 context doc         →  documents    ▮ green med  │
    │       confidence tracks corroboration, not volume         │
    └───────────────────────────────────────────────────────────┘
```

Deterministic, and costs no second LLM call.

---

## A1.9 Parameters

| symbol | setting | value |
|---|---|---|
| `α` | `pathrag_decay_alpha` | `0.8` |
| `h_max` | `pathrag_max_hops` | `4` |
| `k_top` | `pathrag_top_paths` | `15` |
| `θ` | `overlap_threshold` | `0.7` |
| `κ_min` | `MIN_CONFIDENCE_FACTOR` | `0.3` |
| `dim` | `embedding_dim` | `1536` |

`FlowPruner` is pure — no I/O — which is why it carries the heaviest unit-test
coverage in the service.

# 3. Solution Overview

## 3.1 Research Perspective

Enterprise AI treats an industrial archive the way it treats any other corpus: a
flat bag of words, embedded and retrieved by similarity. That assumption is why
it fails on a plant floor. A process facility is not a collection of documents —
it is a **topology**. Pipes, wires, control loops and causal chains exist
physically, and once flattened into vectors they cannot be recovered by any
amount of lexical similarity.

PlantForge is built on the opposite premise: the object worth constructing is not
an index but a **causally-reasoned knowledge graph**, with an autonomous
reasoning layer on top of it rather than beside it.

Committing to that premise forces a sequence of research problems, each created
by solving the one before it. The remainder of this section follows that
sequence: a topology cannot be built if extraction flattens it (**3.2**); a
topology assembled from fragments is unusable until identity is resolved and
vocabulary reconciled (**3.3**); a resolved topology cannot be exploited by
similarity search alone (**3.4**); a system that answers must prove it is not
fabricating (**3.5**); and a system that can be trusted is still useless if a
human must know to ask (**3.6**).

---

## 3.2 Multi-Modal Extraction: preserving what a flat parser destroys

Industrial data is not merely messy, it is **heterogeneous in kind**. One boiler
feed pump is described in a structured maintenance table, a hundred-page OEM
manual, and a P&ID drawing where the critical information is not text at all but
geometry — which line connects to which vessel.

Applying one general-purpose text extractor across all three is not a compromise;
it is lossy in precisely the dimension the graph needs. Standard OCR on a P&ID
returns a bag of tag numbers and discards every connection between them, which is
the one fact the drawing exists to record.

Documents are therefore classified on arrival and routed to a lane built for
their failure mode:

**Vision-language parsing — drawings.** A vision model traces physical topology
directly from pixels rather than reading text off the page, emitting
`CONNECTED_TO` edges. The drawing contributes *structure*, not vocabulary.

**Hierarchy-preserving chunking — manuals and prose.** Fixed-window chunking
severs a procedure from the equipment it belongs to, producing passages that are
locally coherent and globally meaningless. Long documents are chunked along their
own sectional hierarchy, and a language model maps the resulting text onto a
**closed ontology** — `Equipment`, `FailureMode`, `Procedure`, `RegulationClause`
— extracting typed causal relations such as `HAS_FAILURE` rather than free-form
triples. Constraining the model to a fixed schema is what makes output from
different documents composable.

**Deterministic parsing — tables.** Work orders and inspection records are parsed
with **no language model at all**. This is a deliberate refusal: dates, costs and
sensor readings are exactly the values where a hallucination is undetectable
downstream, and a table already has structure that requires no inference.
Removing the model removes the entire failure class.

Every lane emits *candidates*, never facts — each claim carrying provenance back
to its origin: source document, page, character span or bounding-box region,
extractor version, and a confidence score. That record is what makes §3.5
possible.

---

## 3.3 Graph Construction and Denoising: the problem extraction creates

Extraction succeeds and immediately produces a worse problem than it solved.

"Pump 101A", "P-101A" and "Boiler Feed Pump A" arrive from three document systems
and denote one physical asset. Unmerged, the graph fragments into disconnected
islands — and critically, **reasoning does not fail loudly**. A path query simply
finds no route and returns nothing, and an absent answer is indistinguishable
from an absent problem. A fragmented graph is more dangerous than no graph
because it is confidently silent.

Three mechanisms operate at different timescales.

**Entity resolution — synchronous, before the write.** Surface forms are
intercepted and mapped to canonical identifiers: deterministic rules first (tag
grammars, exact matches), string-distance comparison only where those are
exhausted. Deterministic-first ordering keeps the common case reproducible and
confines fuzzy matching to genuine ambiguity.

**Versioned batch commitment.** Resolved subgraphs are buffered and committed by
a **single writer**, one batch per transaction, each incrementing a global graph
version. Nodes are merged rather than appended and every edge carries a
provenance hash, so re-processing a document converges instead of duplicating.
That version number is later stamped on every answer and artifact the system
produces, so any output can state which state of the plant it reasoned against.

**Semantic reclassification — asynchronous, out of band.** Vocabulary drift is
not a tag-matching problem: a technician writes "SEAL LEAK" where a manual says
"GLAND LEAK" — lexically distant, semantically identical. A periodic denoising
pass performs two operations:

- *Pruning* — extraction occasionally lifts a document reference into the graph
  as though it were a plant entity. These are identified and removed, so the
  topology contains only things that physically exist.
- *Reconciliation* — for each equipment item, synonymous failure modes are merged
  into a canonical node and `CAUSES` edges inferred where a mechanism-to-symptom
  relationship is implied but never explicitly stated.

Reconciliation proposals are **validated against the labels supplied to the
model** — any canonical or cause it invents is discarded before touching the
graph. The denoiser proposes; it does not get to fabricate. Because it runs
asynchronously with per-equipment isolation, a degraded pass leaves the graph
exactly as extracted rather than blocking ingestion or corrupting neighbours.

---

## 3.4 The Retrieval and Answer Pipeline

The graph is now connected, versioned and consistent. Standard retrieval still
cannot use it.

Consider *"What equipment fails if P-101A stops?"* Semantic search retrieves
documents that **sound like** that sentence — most likely the pump's own manual,
the one document that cannot answer it. The answer lives in equipment the query
never names, reachable only by traversal. Vector similarity has no notion of
physical topology or causal direction, so this class of question is not answered
badly; it is unanswerable in principle.

The pipeline below (see Figure) treats retrieval as a **flow problem over a
graph**, in twelve stages.

### Stages 1–3 · Ingestion, embedding and the semantic cache

**(1) Condensing.** A follow-up such as *"what about its sibling?"* is meaningless
alone. The thread is condensed into one standalone question — *"P-101B seal
failures"* — and everything downstream, **including the cache key**, keys on that
resolved form rather than the words typed.

**(2) Embedding.** The standalone question is embedded into a 1536-dimension
vector.

**(3) Answer cache.** Before any retrieval, that vector is compared by cosine
similarity against stored question embeddings. This is a *semantic* cache, not a
string cache: a question phrased differently but meaning the same thing still
hits. Above the similarity threshold the stored answer is returned immediately,
with citations re-resolved to current filenames. Each entry stores the answer,
its embedding, the **node identifiers the answer depended on**, the graph
version, timestamp and confidence — and those node identifiers are what allow
targeted invalidation when the graph changes beneath a cached answer, rather than
blanket expiry.

### Stages 4–5 · Linking and routing

**(4) Entity linking.** Plant tags are extracted from the question and resolved to
actual graph nodes, producing *seeds*.

**(5) Routing.** The query's shape selects the strategy — no seeds routes to
vector search; one seed to its local neighbourhood; two or more seeds, or causal
phrasing, to path retrieval. A single-fact lookup never pays for traversal, and a
causal question is never answered from disconnected passages. This is the
decision that makes one system serve both.

### Stage 6 · Three retrieval strategies

**(6A) Vector retrieval.** Top-k chunks from the vector index by similarity — the
correct behaviour when no plant entity was recognised.

**(6B) Local retrieval, deliberately hybrid.** The seed's relations give the exact
neighbourhood; chunks *containing the tag* give literal mentions; and a small
vector top-k is added because **the passage that answers may never name the
equipment**. Torque steps inside a pump's SOP are the canonical case: relevant,
but the tag appears only in the document title. Exact and semantic retrieval are
unioned rather than chosen between.

**(6C) Path retrieval — PathRAG.** *Pathfinder* enumerates routes: between each
pair when several seeds exist, radiating outward to evidence-bearing nodes when
only one does, bounded by a hop limit. *Flow Pruner* then makes the approach
tractable — traversing a dense industrial graph produces a combinatorial
explosion of candidates, and ranking them with a language model would be slow and
expensive. Instead each path is scored by **network-flow mathematics**: score
decays with length, and is **damped by the degree of the nodes it crosses** — a
hub connected to everything explains nothing, so routes through it are penalised
while routes through specific, sparsely-connected relationships are rewarded.
Paths overlapping more than 70% are dropped so the context is not filled with
variants of one route, and the strongest few survive. Path selection is therefore
**deterministic, auditable and costs no inference.** *Assembler* converts survivors
into causal prose, appending a small vector top-k as related passages so the model
receives the topology *and* the narrative evidencing it.

If no viable path exists, the pipeline **degrades to vector retrieval** rather
than returning nothing.

### Stages 7–9 · Augmentation and generation

**(7) Plant digest (conditional).** Plant-wide questions — "how many", "which
overall" — cannot be answered from retrieved passages, because the answer is an
aggregate. Detecting that shape triggers live aggregate queries: overdue
inspections, failure-mode tallies, asset counts. This is computed at query time,
never retrieved.

**(8) Corrections — highest trust tier.** Any evidence document an engineer has
overruled contributes its correction, placed **first, above the material it
overrides**. Ordering is load-bearing: a model that reads the correction last has
already formed the answer the correction exists to prevent.

**(9) Answerer.** The model generates from the assembled context — retrieved
evidence, digest if present, corrections if any — streamed token-by-token to the
interface.

### Stages 10–12 · Verification, citation and cache write-back

**(10) Build meta.** Confidence and grounding are computed **from what the answer
actually cited**, not asserted in advance — which is why this can only happen
after generation completes. The result is stamped with the current graph version
alongside sources and timestamp.

**(11) Name citations.** Content hashes are resolved to human-readable filenames.
This touches only the display name: the identifier, the prompt and the grounding
verdict are untouched, so this step cannot change what the answer says — only how
a source reads on screen.

**(12) Cache put.** The answer, its embedding, the node identifiers it depended
on, graph version, timestamp and confidence are stored — closing the loop back to
stage 3 and enabling both semantic reuse and precise invalidation.

---

## 3.5 Epistemic Grounding: hallucination as a safety hazard

In consumer applications a hallucination is an annoyance. In heavy industry a
fabricated pressure rating or invented valve tag can cause equipment failure or
loss of life. Hallucination is therefore treated not as an edge case to reduce
but as a **primary engineering constraint** with structural countermeasures.

**Immutable provenance.** No fact enters the graph without recording its source
document, page, character span or bounding-box region, extractor version and
confidence. Region-level provenance is what allows a citation to resolve to a
precise location inside a drawing, not merely to a document.

**Interceptive verification.** Generated answers are not returned directly. A
deterministic verifier extracts every equipment tag and claim the model asserted
and checks each against the evidence actually supplied. Claims present in the
answer but absent from the evidence are flagged unverified and surfaced as such.
The system may be uncertain; it may not be quietly wrong.

**Harvested facts versus generated prose.** Where the system produces a
structured artifact — an impact assessment, a work order, a permit — the fact
lists are lifted directly from tool results and the model can write only into the
narrative fields. It cannot invent an asset into a list it did not retrieve.

**Human correction as graph structure.** Source documents are themselves often
wrong: manuals go out of date, and legacy procedures encode errors operators
bypass through undocumented practice. A correction is not filed in a feedback
table — it is **injected into the graph as a node**, linked by a `CORRECTED_BY`
edge to the offending document and permanently embedded in the topology. Stage 8
then guarantees every future answer sees it first. The graph "unlearns" bad
source knowledge with no retraining and no document edit.

---

## 3.6 Autonomous Runtime: removing the requirement to ask

Grounding makes the system trustworthy. It remains **reactive** — idle until a
human types a question. During a developing incident operators are saturated with
alarms and have no spare attention to interrogate a chatbot: the moment the
knowledge is most valuable is the moment nobody is free to request it.

**Change-driven watchers.** Every commit publishes a delta describing what changed
onto an append-only event stream. Deterministic watchers — scripted graph queries,
no model — consume it continuously. New work-order data introducing a seal failure
causes an immediate check of whether sibling equipment in the same unit has
suffered comparable failures recently. An append-only stream rather than a
broadcast channel is deliberate: each consumer holds its own position, so a
restarted watcher resumes exactly where it stopped without replaying history or
skipping what arrived while it was down.

**Agentic investigation.** A statistical pattern is not a diagnosis, so a
confirmed pattern triggers an investigator running a reason-and-act loop. It
autonomously selects graph tools — failure history, connected equipment,
governing clauses, prior work orders — inspects each result and decides what to
examine next, behaving as a reliability engineer tracing a systemic root cause
rather than executing a fixed query plan. Its conclusions are published as a
grounded alert and drafted into a corrective work order for human approval.

**Speculative caching — closing the loop.** An investigation spanning several tool
calls and a synthesis step takes tens of seconds, unacceptable if incurred while
an operator waits. But the investigation *already performed* to raise the alert
contains the answers to the questions that alert will provoke. So at publication
time the runtime derives the natural follow-ups directly from the trigger — what
to do about this failure, this equipment's history, whether siblings are
implicated — embeds them, and writes the fully-researched answers into the
semantic cache.

When the operator opens the alert and asks, the request resolves at **stage 3** of
the pipeline as a cosine comparison against pre-computed entries. The answer
returns essentially instantly at **zero additional inference cost**, because the
reasoning was performed at write time rather than read time.

# 4. Graph-Based Retrieval: From Similarity to Topology

> **Verify every citation below on arXiv/Scholar before submission.**

The research community reached the same conclusion as §1–3 independently, and a
distinct line of work now replaces the flat index with an explicit graph.

## 4.1 From Passages to Graphs

Standard retrieval descends from Dense Passage Retrieval [11], which assumes
relevance is a *pairwise* property between query and passage. Multi-hop questions
violate this directly: the passage completing the reasoning chain may share no
vocabulary with the question.

**GraphRAG** [3] responded by extracting an entity-relation graph, partitioning
it by community detection, and pre-generating a summary per community. This
excels at query-focused summarisation, but carries two costs for our setting: an
LLM call per community makes continuous re-indexing untenable, and community
summarisation is a *lossy abstraction*. "What fails if P-101A stops" is not
answered by a thematic summary — it needs the specific physical path downstream.

**LightRAG** [12] reduces that cost with dual-level (entity + theme) retrieval and
incremental updates, but remains keyed on neighbourhoods rather than on the
structure connecting them.

## 4.2 Paths as the Retrieval Unit

**PathRAG** [13] makes the decisive shift: retrieve the *relational paths*
connecting relevant nodes. Its core contribution addresses redundancy — naive
enumeration over a dense graph yields vast numbers of overlapping routes, and
stuffing them into context reproduces the "lost in the middle" effect [4] on
graph evidence. PathRAG introduces **flow-based pruning with distance-aware
decay**: retrieval resource propagates from seed nodes and dissipates per hop, so
longer, more diffuse paths score lower.

**PlantForge adopts this formulation and extends it with two domain-motivated
terms:**

- **Degree dilution** — resource divides across a node's outgoing edges, so paths
  crossing high-degree hubs are penalised. A shared header connects to nearly
  everything; a route through it is topologically valid and explanatorily
  worthless.
- **Provenance weighting** — each edge carries an extraction confidence (§3.2)
  that multiplies into the flow, so a deterministically parsed table fact
  outranks a hedged model extraction along an otherwise identical path.

The second couples *retrieval ranking* to *extraction reliability*. To our
knowledge this is absent from prior work, and it follows directly from the
multi-lane extraction design rather than being an independent addition.

## 4.3 Related Directions

**HippoRAG** [14] runs Personalised PageRank from query-linked entities, achieving
multi-hop retrieval in a single propagation step. Our local-neighbourhood mode is
conceptually aligned, but diffusion scores *nodes*, not the *route* between them —
which is what a causal question requires. **RAPTOR** [15] builds a recursive
summarisation tree, again trading specificity for abstraction. **Self-RAG** [16]
adds learned self-critique; our grounding check is instead a deterministic
comparison of asserted entities against supplied evidence — an external
constraint, not a learned behaviour. Our investigator follows the **ReAct** [17]
pattern, triggered by a change in the data rather than a user question. Pan et
al. [18] survey LLM–KG integration broadly.

## 4.4 The Residual Gap

| Approach | Contribution | Gap here |
|---|---|---|
| GraphRAG [3] | Global sensemaking | Costly re-indexing; abstraction loses causal links |
| LightRAG [12] | Cheap incremental retrieval | Neighbourhood-keyed, not path-keyed |
| PathRAG [13] | Paths + flow pruning | Assumes a clean graph; no provenance weighting |
| HippoRAG [14] | Single-step multi-hop | Scores nodes, not connecting routes |
| RAPTOR [15] | Multi-level abstraction | Summarisation discards specifics |

**Every method above presumes the graph already exists.** The industrial problem
is that it does not — it must be built from drawings where relations are
geometric, manuals where they are prose, and tables where they are rows, then
reconciled across a vocabulary in which one asset carries four names.

PlantForge sits at that junction: ontology-constrained multi-lane extraction to
*construct* the graph these methods assume, a provenance- and degree-weighted
extension of flow-based pruning, and deterministic grounding that treats
hallucination as a safety constraint rather than a quality metric.

---

## Additional References

- [11] Karpukhin, V., et al. (2020). "Dense Passage Retrieval for Open-Domain
  Question Answering." *EMNLP 2020*. arXiv:2004.04906.
- [12] Guo, Z., Xia, L., Yu, Y., Ao, T., & Huang, C. (2024). "LightRAG: Simple and
  Fast Retrieval-Augmented Generation." arXiv:2410.05779.
- [13] Chen, B., Guo, Z., Yang, Z., et al. (2025). "PathRAG: Pruning Graph-based
  Retrieval Augmented Generation with Relational Paths." arXiv:2502.14902.
- [14] Gutiérrez, B. J., Shu, Y., Gu, Y., Yasunaga, M., & Su, Y. (2024).
  "HippoRAG: Neurobiologically Inspired Long-Term Memory for Large Language
  Models." *NeurIPS 2024*. arXiv:2405.14831.
- [15] Sarthi, P., et al. (2024). "RAPTOR: Recursive Abstractive Processing for
  Tree-Organized Retrieval." *ICLR 2024*. arXiv:2401.18059.
- [16] Asai, A., Wu, Z., Wang, Y., Sil, A., & Hajishirzi, H. (2024). "Self-RAG:
  Learning to Retrieve, Generate, and Critique through Self-Reflection."
  *ICLR 2024*. arXiv:2310.11511.
- [17] Yao, S., et al. (2023). "ReAct: Synergizing Reasoning and Acting in
  Language Models." *ICLR 2023*. arXiv:2210.03629.
- [18] Pan, S., Luo, L., Wang, Y., Chen, C., Wang, J., & Wu, X. (2024). "Unifying
  Large Language Models and Knowledge Graphs: A Roadmap." *IEEE TKDE*.
  arXiv:2306.08302.

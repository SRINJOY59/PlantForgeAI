"""Turning an engineer's correction into graph facts.

This is the lane that makes the brain a brain. Everywhere else the graph is a
readout of documents the plant already had; here a person who knows better
says so, and the plant learns something no document contains.

It produces two different things, and the difference matters:

  The corrected fact, at Source.HUMAN and confidence 1.0. It goes in beside
  the document facts and outranks them - the pruner multiplies flow by edge
  confidence, so a human-stated fact beats a hedged LLM extraction on the same
  question without any special case anywhere downstream.

  A CORRECTED_BY edge from every document the wrong answer leaned on, to this
  correction. That is the graph of mistakes: not "what is true" but "what we
  got wrong, and where". Once it exists, an answer that cites a corrected
  document can say so, and the denoise pass can leave both alone.

Nothing here overwrites anything. The old fact stays, the correction sits next
to it with a higher tier and an edge between them, and the disagreement is
visible rather than silently resolved. A plant that hides which of its records
were wrong is not a brain, it is a filing cabinet with opinions.
"""

from pydantic import BaseModel, Field

from plantmind_core.llm import Tier
from plantmind_core.schemas import (CandidateEdge, CandidateNode,
                                    CandidateSubgraph, EdgeType, NodeType,
                                    Provenance, Source)
from plantmind_core.telemetry import get_logger

log = get_logger("extraction.correction")

VERSION = "correction/1"

PROMPT = """An engineer at this plant is correcting something our assistant \
got wrong. Read their correction and pull out the facts they are asserting.

Only extract what the engineer actually states. They are the authority here, \
so do not soften, hedge, generalise or add anything they did not say. If they \
correct one detail and mention three others in passing, extract the four \
facts they stated and nothing more.

Node types: {node_types}
Edge types: {edge_types}

Use the equipment tags exactly as written (P-101A, V-203, PSV-204).

THE QUESTION THAT WAS ASKED:
{question}

WHAT WE ANSWERED (which the engineer says is wrong):
{answer}

THE ENGINEER'S CORRECTION:
{correction}
"""


class ExtractedNode(BaseModel):
    type: str = Field(description="one of the node types listed")
    surface_form: str = Field(description="the tag or name exactly as written")


class ExtractedEdge(BaseModel):
    type: str = Field(description="one of the edge types listed")
    src: str
    dst: str
    note: str = Field(default="", description="what the engineer said about it")


class CorrectionFacts(BaseModel):
    nodes: list[ExtractedNode] = Field(default_factory=list)
    edges: list[ExtractedEdge] = Field(default_factory=list)


class CorrectionExtractor:
    def __init__(self, llm):
        self._llm = llm

    async def extract(self, doc_id: str, content_hash: str, question: str,
                      answer: str, correction: str, author: str,
                      wrong_doc_ids: list) -> CandidateSubgraph:
        facts = await self._facts(question, answer, correction)

        provenance = Provenance(
            doc_id=doc_id,
            extractor_version=VERSION,
            # a human saying it IS the evidence. There is no more reliable
            # source in the building, and nothing downstream should discount it
            confidence=1.0,
            source=Source.HUMAN)

        nodes, edges = [], []
        seen = set()
        for node in facts.nodes:
            if node.surface_form in seen:
                continue
            seen.add(node.surface_form)
            nodes.append(CandidateNode(type=_node_type(node.type),
                                       surface_form=node.surface_form,
                                       confidence=1.0))

        for edge in facts.edges:
            edge_type = _edge_type(edge.type)
            if edge_type is None:
                log.warning("dropping an edge type we do not model",
                            type=edge.type, doc_id=doc_id)
                continue
            edges.append(CandidateEdge(
                type=edge_type, src=edge.src, dst=edge.dst,
                provenance=provenance,
                props={"note": edge.note, "corrected_by": author}))

        nodes, edges = self._add_mistake_record(nodes, edges, doc_id,
                                                wrong_doc_ids, provenance,
                                                author, correction)
        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=nodes, edges=edges)

    @staticmethod
    def _add_mistake_record(nodes, edges, doc_id, wrong_doc_ids, provenance,
                            author, correction):
        """The correction itself becomes a node, and every document the bad
        answer cited points at it. This is what lets the graph answer 'has
        anything we said from this document been challenged?'"""
        if not wrong_doc_ids:
            return nodes, edges

        nodes.append(CandidateNode(
            type=NodeType.DOCUMENT, surface_form=doc_id,
            # the engineer's own words ride on the node: retrieval can warn
            # that a document was corrected, but that is only useful if it can
            # also say what to
            props={"kind": "correction", "author": author,
                   "text": correction[:1000]},
            confidence=1.0))
        for wrong in dict.fromkeys(wrong_doc_ids):     # dedupe, keep order
            if wrong == doc_id:
                continue
            nodes.append(CandidateNode(type=NodeType.DOCUMENT,
                                       surface_form=wrong, confidence=1.0))
            edges.append(CandidateEdge(
                type=EdgeType.CORRECTED_BY, src=wrong, dst=doc_id,
                provenance=provenance, props={"corrected_by": author}))
        return nodes, edges

    async def _facts(self, question, answer, correction) -> CorrectionFacts:
        prompt = PROMPT.format(
            node_types=", ".join(t.value for t in NodeType),
            edge_types=", ".join(t.value for t in EdgeType),
            question=question, answer=answer, correction=correction)
        try:
            return await self._llm.structured(
                [{"role": "user", "content": prompt}], CorrectionFacts,
                tier=Tier.MID, max_tokens=2048)
        except Exception as e:
            # the mistake record below is still worth writing: we know which
            # documents were challenged even if we could not parse the fix
            log.warning("could not extract facts from a correction",
                        error=str(e)[:160])
            return CorrectionFacts()


def _node_type(raw: str):
    try:
        return NodeType(raw)
    except ValueError:
        return NodeType.EQUIPMENT      # the commonest thing an engineer names


def _edge_type(raw: str):
    try:
        return EdgeType(raw)
    except ValueError:
        return None

"""Shapes that cross service boundaries. Changing anything here touches
every service, so think twice."""

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    EQUIPMENT = "Equipment"
    INSTRUMENT = "Instrument"
    LINE = "Line"
    DOCUMENT = "Document"
    SECTION = "Section"
    CHUNK = "Chunk"
    WORK_ORDER = "WorkOrder"
    FAILURE_MODE = "FailureMode"
    PROCEDURE = "Procedure"
    REGULATION_CLAUSE = "RegulationClause"
    PERSON = "Person"


class EdgeType(str, Enum):
    CONNECTED_TO = "CONNECTED_TO"
    PART_OF = "PART_OF"
    MENTIONED_IN = "MENTIONED_IN"
    HAS_FAILURE = "HAS_FAILURE"
    FIXED_BY = "FIXED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    PRECEDES = "PRECEDES"
    SUPERSEDES = "SUPERSEDES"
    CAUSES = "CAUSES"                # recovered by denoise: mechanism -> mode
    MERGED_INTO = "MERGED_INTO"      # denoise: variant node -> canonical node
    # the "graph of mistakes": knowledge about what went wrong, not just facts
    FAILED_FIX = "FAILED_FIX"        # a repair that did not hold
    CONTRADICTS = "CONTRADICTS"      # two sources disagree
    CORRECTED_BY = "CORRECTED_BY"    # a human/outcome overturned a claim


class Source(str, Enum):
    """How a fact came to be known - its epistemic tier. Only DOCUMENT is
    ground truth; AGENT facts are hypotheses; HUMAN facts are confirmed.
    Nothing above DOCUMENT is written until it clears the verifier."""
    DOCUMENT = "document"
    AGENT = "agent"
    HUMAN = "human"


class Provenance(BaseModel):
    doc_id: str
    page: Optional[int] = None
    span: Optional[tuple[int, int]] = None      # char offsets for text
    bbox: Optional[tuple[float, float, float, float]] = None  # for drawings
    extractor_version: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: Source = Source.DOCUMENT


class CandidateNode(BaseModel):
    type: NodeType
    surface_form: str                            # raw text as seen in the doc
    props: dict = Field(default_factory=dict)
    confidence: float = 1.0
    # filled in by resolution service:
    resolved_id: Optional[str] = None


class CandidateEdge(BaseModel):
    type: EdgeType
    src: str                                     # surface_form ref pre-resolution
    dst: str
    provenance: Provenance
    props: dict = Field(default_factory=dict)


class CandidateSubgraph(BaseModel):
    """Output of every extractor; input to resolution. Never written directly."""
    doc_id: str
    content_hash: str
    nodes: list[CandidateNode]
    edges: list[CandidateEdge]


class GraphDelta(BaseModel):
    """Published on Redis stream 'graph:deltas' after each committed batch."""
    graph_version: int
    touched_node_ids: list[str]
    new_edge_types: list[EdgeType]
    source_doc_ids: list[str]


class QueryMode(str, Enum):
    VECTOR = "vector"          # single-fact lookup
    LOCAL = "local"            # asset-centric (PPR neighborhood)
    PATH = "path"              # causal / multi-entity (PathRAG)


class Citation(BaseModel):
    doc_id: str
    page: Optional[int] = None
    snippet: str


class CorrectionNote(BaseModel):
    """A document behind this answer that an engineer has already overturned.

    Carried on the answer so the UI can say so out loud. The correction is in
    the model's prompt either way, but "trust me, I read it" is not something a
    reader can check - this is.
    """
    doc_id: str                                  # the document that was wrong
    correction_id: str                           # the correction record
    author: str
    text: str


class Answer(BaseModel):
    text: str
    citations: list[Citation]
    corrections: list[CorrectionNote] = Field(default_factory=list)
    mode: QueryMode                              # how we retrieved
    confidence: Literal["high", "medium", "low"]
    # Where the answer came from, checked against its own citations rather
    # than asserted. "documents" = it cited sources we gave it. "general" = it
    # cited nothing, so it answered from what the model knows - true for
    # "what is barg", and not a fact about this plant. "unverified" = it cited
    # a document that was never in its context, which is a fabricated
    # provenance claim.
    grounding: Literal["documents", "general", "unverified"] = "documents"
    graph_version: int                           # for cache freshness checks


class Turn(BaseModel):
    """One past exchange, sent back with a follow-up so it can be understood.

    The client owns its session and hands the history in on every ask, so the
    gateway and retrieval stay stateless: no session store to expire, and no
    way for one user's thread to leak into another's.
    """
    question: str
    answer: str = ""


class WebSource(BaseModel):
    """A page a watcher read on the open web.

    Deliberately not a Citation. A Citation points at a document this plant
    owns, sitting in our object store, that we parsed ourselves - the strongest
    thing we have. A web page is somebody else's claim. Keeping them in
    separate fields means the UI cannot accidentally present one as the other,
    and neither can we.
    """
    url: str
    title: str = ""


class Alert(BaseModel):
    """Raised by the agents service onto the alert stream; the UI shows it."""
    kind: Literal["failure_pattern", "compliance", "standard_revision"]
    severity: Literal["info", "warning", "critical"]
    title: str
    body: str
    equipment: Optional[str] = None
    citations: list[Citation] = Field(default_factory=list)
    web_sources: list[WebSource] = Field(default_factory=list)
    fingerprint: str                             # dedup key, one alert per fact
    graph_version: int = 0
    # grounding: did every tag the agent named actually appear in its
    # evidence? unverified alerts are shown but marked, never trusted blindly
    verified: bool = True
    unverified_claims: list[str] = Field(default_factory=list)


class ChangeProposal(BaseModel):
    """A change somebody wants to make, before they make it.

    Deliberately loose. The plant's own MOC form has thirty fields; none of
    them help the graph decide what a change touches, and demanding them up
    front is how the tool goes unused. A tag and a sentence is enough to
    start walking.
    """
    tag: str                                     # P-101A
    summary: str                                 # "replace mechanical seal ..."
    proposed_by: str = ""


class ImpactAssessment(BaseModel):
    """What a proposed change touches - the section of a Management of Change
    review that is filled in from memory today.

    There is no verdict here, on purpose. Approving a change is a legal act by
    a competent person; a system that prints "proceed" is either ignored or
    dangerous. This is evidence for the human who signs, not the signature.

    The lists are harvested from what the tools returned, not from what the
    model wrote - so the model cannot invent a clause into governing_clauses,
    only into body, where check_grounding catches it.
    """
    proposal: ChangeProposal
    body: str
    affected_equipment: list[str] = Field(default_factory=list)
    documents_to_revise: list[str] = Field(default_factory=list)
    governing_clauses: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    graph_version: int = 0
    verified: bool = True
    unverified_claims: list[str] = Field(default_factory=list)

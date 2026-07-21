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
    doc_id: str                                  # the fetch key, a content hash
    page: Optional[int] = None
    snippet: str
    # the name a person can read. A doc_id is a content hash - correct as an
    # identity, useless on screen ("revise 6d6d71a9..." is not a task). Filled
    # in from the graph after the answer is built; the doc_id still drives the
    # click. Optional so an unresolved citation degrades to showing the hash
    # rather than breaking.
    filename: Optional[str] = None


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


class PermitRequest(BaseModel):
    """What a technician intends to do, before a work permit is issued.

    A tag, a description of the work, and who is requesting it.  The agent
    needs nothing more to walk the isolation boundary, surface the known
    hazards, and draft what the permit authority must verify.
    """
    tag: str                            # primary equipment being worked on
    work_description: str               # "replace mechanical seal on pump"
    requested_by: str = ""


class WorkPermit(BaseModel):
    """Structured output of the Permit-to-Work agent.

    There is no 'approved / rejected' field here, on purpose.  Signing a hot-
    work or confined-space permit is a legal act by a competent person.  This
    is the pre-populated checklist the permit authority reviews and signs —
    not the signature itself.

    The lists (isolation_points, hazards, governing_clauses) are harvested
    directly from tool results, not from model prose, so they are facts about
    the graph rather than claims about it.
    """
    request: PermitRequest
    body: str                                          # LLM-written narrative
    permit_type: str = "General"                       # Hot-Work / Cold-Work / CSE / …
    isolation_points: list[str] = Field(default_factory=list)  # tags to lock out
    identified_hazards: list[str] = Field(default_factory=list)
    required_ppe: list[str] = Field(default_factory=list)
    governing_clauses: list[str] = Field(default_factory=list)
    procedures_to_follow: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    graph_version: int = 0
    verified: bool = True
    unverified_claims: list[str] = Field(default_factory=list)


class WorkOrderDraftProse(BaseModel):
    """The only two fields the model is allowed to write. Split out so the
    structured call can be schema-constrained to exactly this and nothing
    else - it cannot reach the fact lists even by accident."""
    root_cause: str
    recommended_fix: str


class WorkOrderDraft(BaseModel):
    """A maintenance work order drafted off a failure investigation, for a
    planner to approve before anything reaches SAP.

    Same split as ImpactAssessment and WorkPermit, for the same reason: the
    lists are harvested from what the investigation's tools actually returned,
    so the model cannot invent an asset, a prior work order or a procedure
    into them. It can only invent inside root_cause / recommended_fix, where
    check_grounding catches it and `verified` says so out loud.

    priority and order_type are derived from the trigger and the graph, never
    asked of the model: 'how urgent is this' is a scheduling decision with a
    rule behind it, and a model that can choose it will drift.

    There is no approved/rejected field here. Approving a work order commits
    money and a technician's shift; that is a planner's act, recorded against
    the draft rather than stored inside it - which is also what keeps the
    draft itself immutable and replayable off the stream.
    """
    equipment: str
    failure_mode: str = ""

    # --- harvested from the investigation trace; model cannot write these ---
    affected_equipment: list[str] = Field(default_factory=list)
    prior_work_orders: list[str] = Field(default_factory=list)
    procedures: list[str] = Field(default_factory=list)
    governing_clauses: list[str] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    # --- model prose, grounding-checked ---
    root_cause: str = ""
    recommended_fix: str = ""

    # --- derived, deterministic ---
    # SAP order types: PM01 corrective (something broke), PM02 preventive.
    # A failure investigation is corrective by definition.
    order_type: str = "PM01"
    priority: Literal["immediate", "high", "medium", "low"] = "medium"

    # --- provenance ---
    graph_version: int = 0
    verified: bool = True
    unverified_claims: list[str] = Field(default_factory=list)

"""Data contracts shared by every service. These are the ONLY shapes that
cross service boundaries — change here means change everywhere, so keep stable."""

from enum import Enum
from typing import Literal, Optional
from pydantic import BaseModel, Field


class NodeType(str, Enum):
    EQUIPMENT = "Equipment"
    INSTRUMENT = "Instrument"
    LINE = "Line"
    DOCUMENT = "Document"
    CHUNK = "Chunk"
    WORK_ORDER = "WorkOrder"
    FAILURE_MODE = "FailureMode"
    PROCEDURE = "Procedure"
    REGULATION_CLAUSE = "RegulationClause"


class EdgeType(str, Enum):
    CONNECTED_TO = "CONNECTED_TO"
    PART_OF = "PART_OF"
    MENTIONED_IN = "MENTIONED_IN"
    HAS_FAILURE = "HAS_FAILURE"
    FIXED_BY = "FIXED_BY"
    GOVERNED_BY = "GOVERNED_BY"
    PRECEDES = "PRECEDES"
    SUPERSEDES = "SUPERSEDES"


class Provenance(BaseModel):
    doc_id: str
    page: Optional[int] = None
    span: Optional[tuple[int, int]] = None      # char offsets for text
    bbox: Optional[tuple[float, float, float, float]] = None  # for drawings
    extractor_version: str
    confidence: float = Field(ge=0.0, le=1.0)


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


class Answer(BaseModel):
    text: str
    citations: list[Citation]
    mode: QueryMode
    confidence: Literal["high", "medium", "low"]
    graph_version: int                           # for cache freshness checks

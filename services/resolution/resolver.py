"""Entity resolution, rule tier. Canonical ids are deterministic functions
of (type, normalized surface form): the same pump named 'P-101A', 'p 101a'
or 'P101A' in any document always resolves to equip:P-101A, so identical
entities collapse at MERGE time with no coordination between workers.
The embedding + LLM adjudication tiers (for same-meaning-different-words
cases like SEAL-LEAK vs GLAND-LEAK) slot in behind this - that is when
per-key locks become necessary; a pure function needs none."""

import re

from plantmind_core import tags
from plantmind_core.schemas import CandidateSubgraph, NodeType

ID_PREFIX = {
    NodeType.EQUIPMENT: "equip",
    NodeType.INSTRUMENT: "inst",
    NodeType.LINE: "line",
    NodeType.DOCUMENT: "doc",
    NodeType.SECTION: "sec",
    NodeType.CHUNK: "chunk",
    NodeType.WORK_ORDER: "wo",
    NodeType.FAILURE_MODE: "fm",
    NodeType.PROCEDURE: "proc",
    NodeType.REGULATION_CLAUSE: "reg",
    NodeType.PERSON: "person",
}

TAG_TYPES = {NodeType.EQUIPMENT, NodeType.INSTRUMENT, NodeType.LINE}
DOC_SCOPED = {NodeType.DOCUMENT, NodeType.SECTION, NodeType.CHUNK}


def slug(text: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", text.lower())).strip("-")


class Resolver:
    def resolve(self, csg: CandidateSubgraph) -> CandidateSubgraph:
        for node in csg.nodes:
            node.resolved_id = self.canonical(node.type, node.surface_form)
        return csg

    @staticmethod
    def canonical(node_type: NodeType, surface: str) -> str:
        prefix = ID_PREFIX[node_type]
        if node_type in TAG_TYPES:
            return f"{prefix}:{tags.normalize(surface)}"
        if node_type in DOC_SCOPED:
            return f"{prefix}:{surface}"          # already unique per document
        if node_type == NodeType.WORK_ORDER:
            return f"{prefix}:{surface.strip().upper()}"
        return f"{prefix}:{slug(surface)}"        # failure modes, procedures...

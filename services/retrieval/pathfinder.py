"""Candidate path enumeration. The edge whitelist per intent is what keeps
paths meaningful - without it every pair of entities connects through some
document they are both mentioned in."""

from plantmind_core.config import get_settings

CAUSAL_TYPES = ["CONNECTED_TO", "HAS_FAILURE", "FIXED_BY"]
COMPLIANCE_TYPES = ["GOVERNED_BY", "MENTIONED_IN"]
EVIDENCE_LABELS = ["FailureMode", "Procedure", "RegulationClause"]

COMPLIANCE_WORDS = ("standard", "regulation", "compliance", "overdue",
                    "inspection", "governed", "oisd", "ibr", "statutory")


class PathFinder:
    def __init__(self, reader):
        self._reader = reader
        self._max_hops = get_settings().pathrag_max_hops

    def find(self, question: str, seeds: list) -> tuple:
        """-> (paths, degrees) with degrees covering every node on a path."""
        types = self._types_for(question)

        paths = []
        if len(seeds) >= 2:
            for i, a in enumerate(seeds):
                for b in seeds[i + 1:]:
                    paths += self._reader.paths_between(
                        a.node_id, b.node_id, types, self._max_hops)
        elif seeds:
            paths = self._reader.paths_outward(
                seeds[0].node_id, EVIDENCE_LABELS, types, self._max_hops)

        node_ids = set()
        for path in paths:
            node_ids |= path.node_ids()
        degrees = self._reader.out_degrees(node_ids, types) if node_ids else {}
        return paths, degrees

    @staticmethod
    def _types_for(question: str) -> list:
        q = question.lower()
        if any(w in q for w in COMPLIANCE_WORDS):
            return COMPLIANCE_TYPES + CAUSAL_TYPES
        return CAUSAL_TYPES

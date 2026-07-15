"""PathRAG flow-based pruning. Pure math over Path objects - no I/O, which
is why this file carries the heaviest test coverage in the service.

Each seed pours 1.0 units of resource into its paths. Crossing an edge
costs: decay (long paths are weaker evidence), a split across the source
node's other edges (paths through hubs dilute), and the edge's extraction
confidence (a rule-parsed fact outranks a hedged LLM extraction). A path's
score is whatever resource survives to the far end."""

from plantmind_core.config import get_settings

from retrieval.models import Path

MIN_CONFIDENCE_FACTOR = 0.3   # low confidence weakens a path, never erases it


class FlowPruner:
    def __init__(self, alpha=None, top_k=None, overlap_threshold=0.7):
        s = get_settings()
        self.alpha = alpha if alpha is not None else s.pathrag_decay_alpha
        self.top_k = top_k if top_k is not None else s.pathrag_top_paths
        self.overlap_threshold = overlap_threshold

    def prune(self, paths: list, degrees: dict) -> list:
        """Score, rank, drop near-duplicates, keep top_k."""
        for path in paths:
            path.score = self.score(path, degrees)

        kept = []
        for path in sorted(paths, key=lambda p: p.score, reverse=True):
            if len(kept) >= self.top_k:
                break
            if not self._redundant(path, kept):
                kept.append(path)
        return kept

    def score(self, path: Path, degrees: dict) -> float:
        flow = 1.0
        for step in path.steps:
            branching = max(degrees.get(step.src, 1) - 1, 1)  # minus the way in
            confidence = max(float(step.props.get("confidence", 1.0)),
                             MIN_CONFIDENCE_FACTOR)
            flow *= self.alpha * confidence / branching
        return flow

    def _redundant(self, path: Path, kept: list) -> bool:
        edges = path.edge_keys()
        if not edges:
            return True
        for other in kept:
            shared = edges & other.edge_keys()
            smaller = min(len(edges), len(other.edge_keys()))
            if smaller and len(shared) / smaller > self.overlap_threshold:
                return True
        return False

"""Internal shapes for the retrieval pipeline. The public answer shape
(Answer/Citation) lives in plantmind_core.schemas - these never leave the
service."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Seed:
    """A graph node the question was linked to."""
    node_id: str
    surface: str
    label: str


@dataclass(frozen=True)
class Step:
    """One edge of a path, with the direction it was traversed in."""
    type: str
    src: str
    dst: str
    props: dict

    def key(self):
        # undirected identity: the same pipe walked either way is one edge
        return (self.type, frozenset((self.src, self.dst)))


@dataclass
class Path:
    nodes: dict                      # node_id -> {"surface", "label"}
    steps: list                      # [Step]
    score: float = 0.0

    def edge_keys(self) -> set:
        return {s.key() for s in self.steps}

    def node_ids(self) -> set:
        return set(self.nodes)


@dataclass
class Evidence:
    """A source passage backing one or more steps/chunks in the context."""
    doc_id: str
    text: str
    context: str = ""
    page: int = None
    chunk_id: str = ""

from plantmind_core.schemas import CandidateSubgraph
from plantmind_core.telemetry import get_logger

from resolution.resolver import Resolver

log = get_logger("resolution.service")


class ResolutionService:
    """Stamps every node with its canonical id. Pure logic - the resolved
    subgraph's onward journey (the write buffer) is the task adapter's
    concern. The embedding and LLM merge tiers will grow inside this class."""

    def __init__(self, resolver: Resolver = None):
        self._resolver = resolver or Resolver()

    def resolve(self, payload: dict) -> CandidateSubgraph:
        csg = CandidateSubgraph.model_validate(payload)
        csg = self._resolver.resolve(csg)
        log.info("subgraph resolved", doc_id=csg.doc_id,
                 nodes=len(csg.nodes), edges=len(csg.edges))
        return csg

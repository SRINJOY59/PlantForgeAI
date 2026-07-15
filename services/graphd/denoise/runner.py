"""Orchestrates one denoise pass in the safe->novel order:

  1. PRUNE   - deterministic: drop document-id nodes miscaught as equipment
  2. MERGE   - reconcile synonymous failure modes into one canonical node
  3. RECLASSIFY - add the recovered CAUSES edges (mechanism -> mode)

Returns a stats dict so the effect is measurable (nodes pruned, modes
merged, causal links recovered) - the before/after that proves 'less is
more' on the plant."""

from plantmind_core.telemetry import get_logger

from graphd.denoise.graph import DenoiseGraph
from graphd.denoise.lexicon import is_doc_reference
from graphd.denoise.reconciler import Reconciler

log = get_logger("graphd.denoise.runner")


class DenoiseRunner:
    def __init__(self, graph: DenoiseGraph, reconciler: Reconciler):
        self._graph = graph
        self._reconciler = reconciler

    @classmethod
    def from_settings(cls) -> "DenoiseRunner":
        from plantmind_core.llm import get_llm
        return cls(DenoiseGraph.from_settings(), Reconciler(get_llm()))

    async def run(self) -> dict:
        stats = {"pruned": 0, "merged": 0, "causal_added": 0, "equipment": 0}
        self._prune_doc_refs(stats)
        await self._reconcile_failures(stats)
        log.info("denoise pass complete", **stats)
        return stats

    def _prune_doc_refs(self, stats):
        for node in self._graph.doc_reference_nodes():
            if is_doc_reference(node["surface"]):
                stats["pruned"] += self._graph.prune_node(node["id"])
                log.info("pruned document-id node", surface=node["surface"])

    async def _reconcile_failures(self, stats):
        for row in self._graph.equipment_with_failures():
            labels = [f["label"] for f in row["failures"]]
            if len(labels) < 2:
                continue
            stats["equipment"] += 1
            by_label = {f["label"].upper(): f["id"] for f in row["failures"]}
            plan = await self._reconciler.reconcile(row["tag"], labels)

            # keep a map so causal links resolve to the surviving canonical id
            canonical_of = {}
            for group in plan.groups:
                cid = by_label[group.canonical.upper()]
                for v in group.variants:
                    canonical_of[v.upper()] = cid
                canonical_of[group.canonical.upper()] = cid
                vids = [by_label[v.upper()] for v in group.variants
                        if v.upper() in by_label]
                stats["merged"] += self._graph.merge_failure_modes(cid, vids)

            for link in plan.causal:
                cause_id = canonical_of.get(link.cause.upper(),
                                            by_label.get(link.cause.upper()))
                effect_id = canonical_of.get(link.effect.upper(),
                                             by_label.get(link.effect.upper()))
                if cause_id and effect_id and cause_id != effect_id:
                    stats["causal_added"] += self._graph.add_causal_link(
                        cause_id, effect_id)


def main():
    """Run one denoise pass against the live graph and print the stats.
    usage (needs neo4j + OPENROUTER_API_KEY): python -m graphd.denoise.runner"""
    import asyncio
    print(asyncio.run(DenoiseRunner.from_settings().run()))


if __name__ == "__main__":
    main()

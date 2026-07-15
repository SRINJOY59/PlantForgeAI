import asyncio

from graphd.denoise.lexicon import (
    is_doc_reference, looks_like_mechanism, looks_like_sentence,
)
from graphd.denoise.reconciler import (
    CausalLink, FailureGroup, Reconciliation, validate,
)
from graphd.denoise.runner import DenoiseRunner


# ------------------------------------------------------------ lexicon (pure)
def test_doc_reference_detection():
    assert is_doc_reference("IR-2025")
    assert is_doc_reference("WO-2214")
    assert is_doc_reference("INS-503")
    assert not is_doc_reference("P-101A")
    assert not is_doc_reference("K-301")


def test_mechanism_detection():
    assert looks_like_mechanism("CAVITATION")
    assert looks_like_mechanism("TUBE-FOULING")
    assert not looks_like_mechanism("SEAL-LEAK")


def test_sentence_detection():
    assert looks_like_sentence("DEAD-HEADED-OPERATION-LEADING-TO-MOTOR-TRIP")
    assert not looks_like_sentence("SEAL-LEAK")


# ------------------------------------------------------ reconciler validation
def test_validate_drops_invented_labels():
    plan = Reconciliation(
        groups=[
            FailureGroup(canonical="SEAL-LEAK",
                         variants=["GLAND-LEAK", "INVENTED-MODE"], role="mode"),
            FailureGroup(canonical="MADE-UP", variants=[], role="mode")],
        causal=[CausalLink(cause="CAVITATION", effect="SEAL-LEAK"),
                CausalLink(cause="GHOST", effect="SEAL-LEAK")])

    clean = validate(plan, ["SEAL-LEAK", "GLAND-LEAK", "CAVITATION"])

    assert len(clean.groups) == 1                       # MADE-UP dropped
    g = clean.groups[0]
    assert g.canonical == "SEAL-LEAK"
    assert g.variants == ["GLAND-LEAK"]                 # INVENTED-MODE dropped
    assert len(clean.causal) == 1                       # GHOST link dropped
    assert clean.causal[0].cause == "CAVITATION"


# ------------------------------------------------------------- runner (fakes)
class FakeGraph:
    def __init__(self, equipment, doc_refs=None):
        self._equipment = equipment
        self._doc_refs = doc_refs or []
        self.pruned = []
        self.merges = []
        self.causal = []

    def doc_reference_nodes(self):
        return self._doc_refs

    def equipment_with_failures(self):
        return self._equipment

    def prune_node(self, node_id):
        self.pruned.append(node_id)
        return 1

    def merge_failure_modes(self, canonical_id, variant_ids):
        self.merges.append((canonical_id, variant_ids))
        return len(variant_ids)

    def add_causal_link(self, cause_id, effect_id):
        self.causal.append((cause_id, effect_id))
        return 1


class FakeReconciler:
    def __init__(self, plan):
        self._plan = plan

    async def reconcile(self, tag, labels):
        return self._plan


def test_runner_prunes_doc_reference_nodes():
    graph = FakeGraph(
        equipment=[],
        doc_refs=[{"id": "equip:IR-2025", "surface": "IR-2025"},
                  {"id": "equip:P-101A", "surface": "P-101A"}])

    stats = asyncio.run(DenoiseRunner(graph, FakeReconciler(
        Reconciliation(groups=[], causal=[]))).run())

    assert stats["pruned"] == 1
    assert graph.pruned == ["equip:IR-2025"]            # real equipment kept


def test_runner_merges_and_links_causally():
    graph = FakeGraph(equipment=[{
        "equip_id": "equip:P-101A", "tag": "P-101A",
        "failures": [
            {"id": "fm:seal-leak", "label": "SEAL-LEAK"},
            {"id": "fm:gland-leak", "label": "GLAND-LEAK"},
            {"id": "fm:cavitation", "label": "CAVITATION"}]}])
    plan = Reconciliation(
        groups=[
            FailureGroup(canonical="SEAL-LEAK", variants=["GLAND-LEAK"],
                         role="mode"),
            FailureGroup(canonical="CAVITATION", variants=[],
                         role="mechanism")],
        causal=[CausalLink(cause="CAVITATION", effect="SEAL-LEAK")])

    stats = asyncio.run(DenoiseRunner(graph, FakeReconciler(plan)).run())

    assert stats["merged"] == 1
    assert graph.merges == [("fm:seal-leak", ["fm:gland-leak"])]
    assert stats["causal_added"] == 1
    assert graph.causal == [("fm:cavitation", "fm:seal-leak")]
    assert stats["equipment"] == 1


def test_runner_skips_equipment_with_one_failure():
    graph = FakeGraph(equipment=[{
        "equip_id": "equip:E-204", "tag": "E-204",
        "failures": [{"id": "fm:fouling", "label": "FOULING"}]}])

    stats = asyncio.run(DenoiseRunner(graph, FakeReconciler(
        Reconciliation(groups=[], causal=[]))).run())

    assert stats["equipment"] == 0 and graph.merges == []

from agents.watchers import FailureWatcher, family_of
from conftest import FakeAgentReader


def test_family_of_strips_trailing_letters():
    assert family_of("P-101A") == "P-101"
    assert family_of("P-101B") == "P-101"
    assert family_of("K-301") == "K-301"


def test_sibling_pattern_produces_trigger():
    reader = FakeAgentReader()
    reader.failures["equip:P-101B"] = [
        {"tag": "P-101B", "mode": "SEAL-LEAK", "count": 1,
         "causes": [], "docs": ["wo200"]}]
    reader.family[("P-101", "SEAL-LEAK")] = [
        {"tag": "P-101A", "count": 3, "causes": ["cavitation"], "docs": ["wo"]}]

    triggers = FailureWatcher(reader).detect(["equip:P-101B"], graph_version=5)

    assert len(triggers) == 1
    t = triggers[0]
    assert t.tag == "P-101B" and t.mode == "SEAL-LEAK"
    assert t.family == "P-101"
    assert t.siblings[0]["tag"] == "P-101A"
    assert t.graph_version == 5


def test_recurrence_alone_triggers():
    reader = FakeAgentReader()
    reader.failures["equip:P-101A"] = [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "causes": ["cavitation"], "docs": ["wo"]}]

    triggers = FailureWatcher(reader).detect(["equip:P-101A"], 1)
    assert len(triggers) == 1 and triggers[0].count == 3


def test_isolated_first_failure_is_silent():
    reader = FakeAgentReader()
    reader.failures["equip:E-210"] = [
        {"tag": "E-210", "mode": "CORROSION", "count": 1,
         "causes": [], "docs": ["wo"]}]

    assert FailureWatcher(reader).detect(["equip:E-210"], 1) == []


def test_non_equipment_nodes_skipped():
    reader = FakeAgentReader()
    reader.failures["fm:seal-leak"] = [{"tag": "x", "mode": "y", "count": 9,
                                        "causes": [], "docs": []}]
    assert FailureWatcher(reader).detect(["fm:seal-leak", "doc:abc"], 1) == []

"""The work order is the artifact that puts a spanner on live plant, so the
thing worth pinning is that the model cannot write into the parts a technician
acts on, and that urgency follows a rule rather than a mood."""

from agents.usecases.work_order import derive_priority, harvest


class Trigger:
    def __init__(self, tag="P-101A", mode="SEAL-LEAK", family="P-101",
                 siblings=None, count=1, graph_version=7):
        self.tag, self.mode, self.family = tag, mode, family
        self.siblings = siblings if siblings is not None else []
        self.count, self.graph_version = count, graph_version


TRACE = [
    ("get_sibling_history", {}, [{"tag": "P-101B", "count": 2, "docs": ["d1"]}]),
    ("get_connected_equipment", {}, [{"tag": "FT-103", "label": "Instrument"}]),
    ("get_work_orders", {}, [{"wo_id": "WO-2257", "date": "2024-03-01"},
                             {"wo_id": "WO-2257", "date": "2024-03-01"}]),
    ("get_fix_procedures", {}, [{"procedure": "SOP-PUMP-SEAL", "docs": ["d2"]}]),
    ("get_governing_clauses", {}, [{"clause": "OISD-STD-129 5.2"}]),
    ("get_failure_history", {}, [{"mode": "SEAL-LEAK", "count": 3}]),
]


def test_facts_are_harvested_from_the_tools_not_the_prose():
    f = harvest(TRACE)
    assert f["affected_equipment"] == ["P-101B", "FT-103"]
    assert f["prior_work_orders"] == ["WO-2257"]
    assert f["procedures"] == ["SOP-PUMP-SEAL"]
    assert f["governing_clauses"] == ["OISD-STD-129 5.2"]


def test_duplicates_collapse_but_order_survives():
    # a planner reading 'WO-2257, WO-2257' stops trusting the document, and
    # alphabetising would scramble the order the investigation found things in
    assert harvest(TRACE)["prior_work_orders"] == ["WO-2257"]


def test_a_tool_that_returned_nothing_contributes_nothing():
    assert harvest([("get_work_orders", {}, [])])["prior_work_orders"] == []


def test_an_unknown_tool_cannot_smuggle_facts_in():
    # only the tools in HARVEST may write into the fact lists, so a future
    # tool returning a 'tag' key cannot silently become affected equipment
    f = harvest([("some_new_tool", {}, [{"tag": "X-999"}])])
    assert f["affected_equipment"] == []


def test_recurring_failure_under_a_statutory_clause_is_immediate():
    t = Trigger(siblings=[{"tag": "P-101B"}], count=3)
    assert derive_priority(t, ["OISD-STD-129 5.2"], verified=True) == "immediate"


def test_recurring_alone_is_high():
    t = Trigger(siblings=[{"tag": "P-101B"}], count=2)
    assert derive_priority(t, [], verified=True) == "high"


def test_a_one_off_with_no_clause_is_low():
    assert derive_priority(Trigger(count=1), [], verified=True) == "low"


def test_ungrounded_drafts_cannot_be_urgent():
    """The cap that matters: if we could not trace what the model said, we are
    not entitled to tell a planner to drop everything for it."""
    t = Trigger(siblings=[{"tag": "P-101B"}], count=3)
    assert derive_priority(t, ["OISD-STD-129 5.2"], verified=False) == "medium"
    assert derive_priority(Trigger(count=1), [], verified=False) == "low"

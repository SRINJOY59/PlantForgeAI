"""The compliance position is what an auditor is shown, so the boundaries of
'overdue' and 'due soon' are the part worth pinning - and the counts must be
derived from the same items the page lists, never counted twice."""

from agents.usecases.compliance import DUE_SOON_DAYS, item_id, position
from agents.usecases.work_order import from_compliance

TODAY = "2026-07-21"


def row(equipment="V-201", standard="API 510", next_due="2026-01-01", **kw):
    base = {"equipment": equipment, "standard": standard, "next_due": next_due,
            "inspection_type": "Pressure Vessel Inspection",
            "last_inspection": "2024-01-01", "revision": "2024",
            "doc_id": "abc123", "page": 4}
    base.update(kw)
    return base


def test_a_past_due_date_is_overdue():
    p = position([row(next_due="2026-07-20")], today=TODAY)
    assert p["items"][0]["status"] == "overdue"


def test_today_is_not_yet_overdue():
    # the inspection has until the end of the day it is due
    p = position([row(next_due=TODAY)], today=TODAY)
    assert p["items"][0]["status"] == "due_soon"


def test_inside_the_window_is_due_soon_and_outside_is_compliant():
    from datetime import date, timedelta
    edge = (date.fromisoformat(TODAY) + timedelta(days=DUE_SOON_DAYS)).isoformat()
    beyond = (date.fromisoformat(TODAY) + timedelta(days=DUE_SOON_DAYS + 1)).isoformat()
    assert position([row(next_due=edge)], today=TODAY)["items"][0]["status"] == "due_soon"
    assert position([row(next_due=beyond)], today=TODAY)["items"][0]["status"] == "compliant"


def test_obligations_without_a_due_date_are_not_invented_into_the_position():
    assert position([row(next_due="")], today=TODAY)["items"] == []


def test_counts_match_the_items_listed():
    p = position([row(next_due="2026-01-01"), row(next_due="2026-08-01"),
                  row(next_due="2030-01-01")], today=TODAY)
    assert p["counts"] == {"overdue": 1, "due_soon": 1, "compliant": 1}
    assert sum(p["counts"].values()) == len(p["items"])


def test_overdue_sorts_first_then_soonest():
    p = position([row(equipment="A", next_due="2030-01-01"),
                  row(equipment="B", next_due="2026-01-01"),
                  row(equipment="C", next_due="2026-08-01")], today=TODAY)
    assert [i["equipment"] for i in p["items"]] == ["B", "C", "A"]


def test_item_id_is_stable_across_reads():
    # a scheduling decision taken against one of these has to still refer to
    # the same obligation on the next page load
    assert item_id(row()) == item_id(row())


def test_scheduling_an_overdue_obligation_drafts_a_grounded_pm02():
    item = position([row(next_due="2026-01-01")], today=TODAY)["items"][0]
    wo = from_compliance(item, graph_version=9)
    assert wo.order_type == "PM02"          # preventive: it is due, not broken
    assert wo.priority == "high"            # overdue exposure grows with time
    assert wo.equipment == "V-201"
    assert wo.governing_clauses == ["API 510"]
    assert [c.doc_id for c in wo.citations] == ["abc123"]
    assert wo.graph_version == 9
    # no LLM ran, so there is nothing ungrounded by construction
    assert wo.verified is True
    assert wo.unverified_claims == []


def test_an_approaching_obligation_is_not_urgent():
    item = position([row(next_due="2026-08-01")], today=TODAY)["items"][0]
    assert from_compliance(item).priority == "medium"

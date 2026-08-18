"""The matcher - scoring a live signature against the learned library.

Hand-built signatures only. The three things the score must respect, each
isolated: a fault matches itself best, a conflicting direction is disconfirming
(not neutral), and the cascade order refines the ranking without ever vetoing a
match outright. No simulator, no database.
"""

import pytest

from plantmind_core.schemas import (
    DiagnosisMatch, FaultMode, FaultSignature, TagDeviation,
)
from diagnostics.matcher import match_signature


def dev(tag, direction, rank, magnitude=8.0, offset=1.0):
    return TagDeviation(tag_id=tag, direction=direction, magnitude=magnitude,
                        onset_offset_s=offset, first_mover_rank=rank)


def sig(devs, cause_id=None, source="plant"):
    return FaultSignature(deviations=devs, window_s=300.0, source=source,
                          cause_id=cause_id)


def mode(idv, devs, areas=None):
    return FaultMode(
        id=f"faultmode:IDV-{idv}", cause_id=f"IDV-{idv}",
        cause_label=f"fault {idv}", unit_areas=areas or ["REACTOR"],
        signature=sig(devs, cause_id=f"IDV-{idv}", source="sim"),
    )


# a small library: two faults that share a tag but differ in shape
LIB = [
    mode(4, [dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)]),
    mode(6, [dev("REACTOR.P", "high", 0), dev("SEPARATOR.Level", "low", 1)]),
]


def test_a_signature_matches_its_own_fault_best():
    query = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)])
    matches = match_signature(query, LIB)

    assert matches[0].fault_mode_id == "faultmode:IDV-4"
    assert matches[0].confidence == pytest.approx(1.0)
    assert matches[0].cause_id == "IDV-4"
    assert matches[0].unit_areas == ["REACTOR"]


def test_a_conflicting_direction_disconfirms():
    # same two tags as IDV-4, but REACTOR.T moves the *opposite* way
    query = sig([dev("REACTOR.T", "low", 0), dev("REACTOR.P", "high", 1)])
    matches = match_signature(query, LIB)

    by_id = {m.fault_mode_id: m.confidence for m in matches}
    # IDV-4: one agree (P), one conflict (T) -> nets to zero overlap -> dropped
    assert "faultmode:IDV-4" not in by_id
    # IDV-6 still shares REACTOR.P high -> a weak but real match survives
    assert by_id.get("faultmode:IDV-6", 0) > 0


def test_wrong_cascade_order_still_matches_but_ranks_lower():
    exact = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)])
    reversed_order = sig([dev("REACTOR.T", "high", 1), dev("REACTOR.P", "high", 0)])

    exact_conf = match_signature(exact, LIB)[0].confidence
    rev_conf = match_signature(reversed_order, LIB)[0].confidence

    # same signed tags, so it still matches IDV-4 top...
    assert match_signature(reversed_order, LIB)[0].fault_mode_id == "faultmode:IDV-4"
    # ...but the flipped cascade costs it, without collapsing to nothing
    assert rev_conf < exact_conf
    assert rev_conf >= 0.5


def test_disjoint_tags_do_not_match():
    query = sig([dev("STRIPPER.T", "high", 0), dev("COMPRESSOR.Power", "high", 1)])
    assert match_signature(query, LIB) == []


def test_extra_query_tags_dilute_confidence():
    exact = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)])
    noisy = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1),
                 dev("STRIPPER.T", "high", 2)])   # a real tag IDV-4 doesn't have

    exact_conf = match_signature(exact, LIB)[0].confidence
    noisy_conf = match_signature(noisy, LIB)[0].confidence
    assert noisy_conf < exact_conf              # union grew, overlap fell


def test_partial_overlap_ranks_beneath_full():
    # shares only REACTOR.P with IDV-4 and IDV-6; both partial, neither perfect
    query = sig([dev("REACTOR.P", "high", 0)])
    matches = match_signature(query, LIB)
    assert all(m.confidence < 1.0 for m in matches)
    assert len(matches) == 2                    # both share the one tag


def test_top_k_and_min_confidence_bound_the_result():
    query = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)])
    one = match_signature(query, LIB, top_k=1)
    assert len(one) == 1 and one[0].fault_mode_id == "faultmode:IDV-4"

    none = match_signature(query, LIB, min_confidence=0.99)
    assert [m.fault_mode_id for m in none] == ["faultmode:IDV-4"]  # only the 1.0


def test_empty_library_and_empty_query():
    query = sig([dev("REACTOR.T", "high", 0)])
    assert match_signature(query, []) == []
    assert match_signature(sig([]), LIB) == []


def test_matches_are_sorted_by_confidence_descending():
    query = sig([dev("REACTOR.T", "high", 0), dev("REACTOR.P", "high", 1)])
    confs = [m.confidence for m in match_signature(query, LIB)]
    assert confs == sorted(confs, reverse=True)

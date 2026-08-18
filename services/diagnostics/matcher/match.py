"""Score a live fault signature against the learned library.

The other half of the memory layer. The extractor turns a telemetry window into
a FaultSignature; this turns a signature the plant is showing *now* into a
ranked list of the known faults it resembles. Same pure, offline discipline - a
query signature and a list of FaultModes in, DiagnosisMatches out, no model and
no database - so it is unit-tested against hand-built signatures.

The similarity is deliberately the one a control engineer would defend, decomposed
into three questions asked in order of how much they separate faults:

  1. Did the same variables move?      (directional overlap - the coarse filter)
  2. Did they move the same way?       (a tag going the opposite way is evidence
                                        *against*, not neutral)
  3. Did they move in the same order?  (the cascade - what tells apart two faults
                                        that light up the same tags in different
                                        sequence; a refinement, never a veto)

Overlap and direction fold into one signed score over the union of tags, so
extra or missing tags cost and a conflicting direction subtracts. Cascade order
then scales it down when the sequence disagrees, but only to a floor - a fault
with the same signed tags in a different order is still probably a relative, and
the ranking should say so rather than hide it.
"""

from __future__ import annotations

from plantmind_core.schemas import DiagnosisMatch, FaultMode, FaultSignature

DEFAULT_TOP_K = 5

# Below this a "match" is noise - one incidental shared tag out of many. Kept low
# so a weak-but-real resemblance still surfaces, ranked honestly beneath the
# strong ones, rather than being silently dropped.
MIN_CONFIDENCE = 0.05

# The cascade term scales the score to this floor at worst, never to zero: the
# same signed tags in the wrong order is a weaker match, not a non-match.
RANK_FLOOR = 0.5


def match_signature(
    query: FaultSignature,
    library: list[FaultMode],
    *,
    top_k: int = DEFAULT_TOP_K,
    min_confidence: float = MIN_CONFIDENCE,
) -> list[DiagnosisMatch]:
    """Rank the library by resemblance to `query`. Highest confidence first;
    ties break on fault_mode_id for a stable order."""
    matches: list[DiagnosisMatch] = []
    for fm in library:
        conf = _score(query, fm.signature)
        if conf >= min_confidence:
            matches.append(DiagnosisMatch(
                fault_mode_id=fm.id,
                cause_id=fm.cause_id,
                cause_label=fm.cause_label,
                confidence=round(conf, 4),
                unit_areas=fm.unit_areas,
            ))
    matches.sort(key=lambda m: (-m.confidence, m.fault_mode_id))
    return matches[:top_k]


def _score(query: FaultSignature, candidate: FaultSignature) -> float:
    """Similarity in [0, 1] between two signatures."""
    q = {d.tag_id: d for d in query.deviations}
    c = {d.tag_id: d for d in candidate.deviations}
    if not q or not c:
        return 0.0

    union = set(q) | set(c)
    shared = set(q) & set(c)
    agree = [t for t in shared if q[t].direction == c[t].direction]
    conflict = shared - set(agree)

    # signed overlap: agreeing tags count for, conflicting tags count against,
    # and tags in only one signature dilute both by inflating the union
    directional_overlap = (len(agree) - len(conflict)) / len(union)
    if directional_overlap <= 0.0:
        return 0.0

    rank = _rank_agreement(agree, q, c)
    return directional_overlap * (RANK_FLOOR + (1.0 - RANK_FLOOR) * rank)


def _rank_agreement(tags: list[str], q: dict, c: dict) -> float:
    """How much the two signatures agree on the *order* the shared tags moved,
    as a fraction of concordant pairs (a Kendall-tau in [0, 1]). Undefined for
    fewer than two tags, where there is no order to disagree about - returns 1.0
    so a single-tag match is judged on direction and overlap alone."""
    if len(tags) < 2:
        return 1.0
    pairs = concordant = 0
    for i in range(len(tags)):
        for j in range(i + 1, len(tags)):
            a, b = tags[i], tags[j]
            q_order = q[a].first_mover_rank - q[b].first_mover_rank
            c_order = c[a].first_mover_rank - c[b].first_mover_rank
            if q_order == 0 or c_order == 0:
                continue                     # a tie carries no ordering evidence
            pairs += 1
            if (q_order > 0) == (c_order > 0):
                concordant += 1
    if pairs == 0:
        return 1.0
    return concordant / pairs

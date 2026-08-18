"""Turn a telemetry window into a FaultSignature.

The heart of the memory layer, and deliberately the dumbest defensible thing
that works: no model, no training, just statistics a control engineer would
recognise. A window brackets a fault - a lead-in at nominal, then the reaction.
The lead-in gives each tag its own baseline (mean and spread); the reaction is
scored against that baseline. A tag counts as part of the fault when it leaves
its baseline band and stays out, and its role is three numbers: which way it
went, how far (in baseline std, so tags on wildly different scales compare),
and - the part that carries causality - how soon it moved relative to the rest.

Pure and offline: it takes a list of samples and returns a FaultSignature, so
it runs the same over a historian window (building the library) or a live
buffer (diagnosing the plant), and it is unit-tested without a database.
"""

from __future__ import annotations

from collections import defaultdict

from plantmind_core.schemas import FaultSignature, TagDeviation

# A tag is "deviating" once it sits this many baseline std-devs off its own
# nominal mean. 4 sigma is well outside noise but easily cleared by a real
# excursion - the same order the envelope alarms trip at.
DEVIATION_SIGMA = 4.0

# Floor on the baseline spread, so a rock-steady tag (near-zero std in the
# lead-in) doesn't turn a sensor-noise wiggle into an infinite z-score.
MIN_BASELINE_STD = 1e-6

# A tag has to stay out this fraction of the post-onset window to count. Filters
# a single noisy sample that pokes past the band and comes straight back.
MIN_BREACH_FRACTION = 0.2


def _mean_std(values: list[float]) -> tuple[float, float]:
    n = len(values)
    if n == 0:
        return 0.0, MIN_BASELINE_STD
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    return mean, max(var ** 0.5, MIN_BASELINE_STD)


def extract_signature(
    samples: list,                 # TelemetryRow-likes: .ts, .tag_id, .value
    onset_ts,                      # datetime the fault was injected
    *,
    severity: str = "warning",
    source: str = "sim",
    cause_id: str | None = None,
    cause_label: str = "",
) -> FaultSignature:
    """Build the signature of the episode in `samples`, split at `onset_ts`.

    Samples before onset are the per-tag baseline; samples at/after onset are
    scored against it. Ordering within the list does not matter - everything is
    bucketed by tag and sorted by time here.
    """
    by_tag: dict[str, list] = defaultdict(list)
    for s in samples:
        if s.value is not None:
            by_tag[s.tag_id].append(s)

    window_s = _window_span(samples)
    deviations: list[TagDeviation] = []

    for tag_id, rows in by_tag.items():
        rows.sort(key=lambda r: r.ts)
        pre = [r.value for r in rows if r.ts < onset_ts]
        post = [r for r in rows if r.ts >= onset_ts]
        if len(pre) < 2 or not post:
            continue                      # no baseline or no reaction to score

        mean, std = _mean_std(pre)

        breaches = [r for r in post if abs(r.value - mean) >= DEVIATION_SIGMA * std]
        if len(breaches) < max(1, int(len(post) * MIN_BREACH_FRACTION)):
            continue                      # a blip, not a sustained deviation

        first = breaches[0]
        peak = max(post, key=lambda r: abs(r.value - mean))
        deviations.append(TagDeviation(
            tag_id=tag_id,
            direction="high" if peak.value >= mean else "low",
            magnitude=round(abs(peak.value - mean) / std, 3),
            onset_offset_s=round((first.ts - onset_ts).total_seconds(), 3),
            first_mover_rank=0,           # assigned after all tags are known
        ))

    # Rank by who moved first: the head of the cascade is the causal lead, and
    # ordering is what separates faults that light up the same tags in different
    # sequence. Ties break on larger magnitude, then tag_id for determinism.
    deviations.sort(key=lambda d: (d.onset_offset_s, -d.magnitude, d.tag_id))
    for rank, d in enumerate(deviations):
        d.first_mover_rank = rank

    return FaultSignature(
        deviations=deviations,
        window_s=window_s,
        severity=severity,
        source=source,
        cause_id=cause_id,
        cause_label=cause_label,
    )


def _window_span(samples: list) -> float:
    if not samples:
        return 0.0
    ts = [s.ts for s in samples]
    return round((max(ts) - min(ts)).total_seconds(), 3)

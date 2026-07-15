"""Per-equipment failure reconciliation. Given all the failure-mode labels
on one equipment, the model returns a plan: which labels are synonyms
(merge), and which are causes of others (the recovered causal structure).

The plan is validated before it can touch the graph - every label it
references must be one we handed it. A canonical or cause the model invented
is rejected, exactly like the agent grounding check: the reconciler proposes,
it does not get to fabricate."""

from typing import Literal

from pydantic import BaseModel

from plantmind_core.llm import Tier
from plantmind_core.telemetry import get_logger

from graphd.denoise.lexicon import looks_like_mechanism

log = get_logger("graphd.denoise.reconciler")


class FailureGroup(BaseModel):
    canonical: str            # the label to keep - MUST be one of the inputs
    variants: list[str]       # other input labels that mean the same thing
    role: Literal["mode", "mechanism"]


class CausalLink(BaseModel):
    cause: str                # an input label (usually a mechanism)
    effect: str               # an input label (a mode)


class Reconciliation(BaseModel):
    groups: list[FailureGroup]
    causal: list[CausalLink]


PROMPT = """You are reconciling the failure records of ONE piece of plant
equipment ({tag}). Its failure-mode labels, as extracted from documents,
are often fragmented: the same failure appears under several names, and some
"failure modes" are really the CAUSE of another (a mechanism), or a whole
cause-effect sentence flattened into one label.

Failure labels on {tag}:
{labels}

Return:
- groups: cluster labels that mean the SAME failure. Pick the clearest
  existing label as `canonical`; list the rest as `variants`. role='mode'
  for an actual failure, role='mechanism' for a cause (e.g. cavitation,
  corrosion, fouling, dead-head).
- causal: where one label is the CAUSE of another (mechanism -> mode, e.g.
  cavitation causes seal leak; high discharge temperature causes trip),
  add {{cause, effect}}.

Use ONLY the labels listed above - never invent a new label. Every label
should appear in exactly one group."""


class Reconciler:
    def __init__(self, llm):
        self._llm = llm

    async def reconcile(self, tag: str, labels: list) -> Reconciliation:
        if len(labels) < 2:
            return Reconciliation(groups=[], causal=[])
        hints = "\n".join(
            f"- {l}" + ("  (looks like a mechanism/cause)"
                        if looks_like_mechanism(l) else "")
            for l in labels)
        plan = await self._llm.structured(
            [{"role": "user", "content": PROMPT.format(tag=tag, labels=hints)}],
            Reconciliation, tier=Tier.CHEAP)
        return validate(plan, labels)


def validate(plan: Reconciliation, labels: list) -> Reconciliation:
    """Drop anything referencing a label we did not supply (anti-hallucination)
    and any group that collapses to nothing."""
    allowed = {l.upper() for l in labels}

    def ok(label: str) -> bool:
        return label.upper() in allowed

    groups = []
    for g in plan.groups:
        if not ok(g.canonical):
            log.warning("dropped group with invented canonical",
                        canonical=g.canonical)
            continue
        variants = [v for v in g.variants if ok(v) and v.upper() != g.canonical.upper()]
        groups.append(FailureGroup(canonical=g.canonical, variants=variants,
                                   role=g.role))

    causal = [c for c in plan.causal if ok(c.cause) and ok(c.effect)
              and c.cause.upper() != c.effect.upper()]
    return Reconciliation(groups=groups, causal=causal)

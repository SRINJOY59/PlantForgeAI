"""Reproduces the failure that took out a whole denoise pass:

    Task graphd.tasks.run_denoise failed permanently after exhausting all
    retries. 1 validation error for Reconciliation: Invalid JSON: EOF while
    parsing a value at line 1 column 0 [input_value='']

The model returned an empty string, pydantic reported it as malformed JSON,
and the exception escaped far enough to abort every other equipment in the
pass - which celery then retried in full, hitting the same row each time.
"""

import asyncio

import pytest
from pydantic import BaseModel

from plantmind_core.llm import EmptyCompletion
from plantmind_core.llm.client import LLMClient
from graphd.denoise.reconciler import Reconciler, Reconciliation
from graphd.denoise.runner import DenoiseRunner


class Shape(BaseModel):
    value: str


class EmptyLLM:
    """A model that returns nothing - a reasoning model that spent its whole
    budget thinking, or a provider hiccup."""

    def __init__(self):
        self.calls = 0

    async def structured(self, messages, schema, tier=None, **kw):
        self.calls += 1
        return LLMClient._parse(schema, "")


def test_an_empty_completion_is_named_as_such_not_reported_as_broken_json():
    with pytest.raises(EmptyCompletion) as e:
        LLMClient._parse(Shape, "")
    assert "empty completion" in str(e.value)
    assert "Shape" in str(e.value)


def test_whitespace_and_empty_fences_count_as_empty():
    for raw in ("", "   \n ", "```json\n\n```"):
        with pytest.raises(EmptyCompletion):
            LLMClient._parse(Shape, raw)


def test_reconciler_degrades_to_no_plan_instead_of_raising():
    """Declining to merge leaves the labels exactly as extracted - the state
    the graph was already in. Raising would cost every other equipment."""
    r = Reconciler(EmptyLLM())
    plan = asyncio.run(r.reconcile("P-101A", ["SEAL LEAK", "SEAL FAILURE"]))
    assert plan == Reconciliation(groups=[], causal=[])


class ExplodingReconciler:
    async def reconcile(self, tag, labels):
        raise RuntimeError(f"boom on {tag}")


class FakeGraph:
    def __init__(self, rows):
        self._rows = rows
        self.merged = []

    def equipment_with_failures(self):
        return self._rows

    def doc_reference_nodes(self):
        return []

    def merge_failure_modes(self, cid, vids):
        self.merged.append((cid, vids))
        return len(vids)

    def add_causal_link(self, a, b):
        return 1


def _row(tag):
    return {"tag": tag, "failures": [{"label": "SEAL LEAK", "id": f"{tag}:1"},
                                     {"label": "SEAL FAILURE", "id": f"{tag}:2"}]}


def test_one_bad_equipment_does_not_abort_the_pass():
    """The actual regression: the pass must survive a row that always fails,
    or celery retries the whole thing and it dies having done nothing."""
    graph = FakeGraph([_row("P-101A"), _row("P-101B"), _row("K-301")])
    runner = DenoiseRunner(graph, ExplodingReconciler())
    stats = asyncio.run(runner.run())
    assert stats["skipped"] == 3           # every row failed, none escaped
    assert stats["merged"] == 0            # and nothing was written


def test_a_group_naming_an_unknown_canonical_is_skipped_not_raised():
    """validate() should have dropped it, but a canonical with no id used to
    KeyError mid-loop and cost the remaining equipment."""
    class Ghost:
        async def reconcile(self, tag, labels):
            from graphd.denoise.reconciler import FailureGroup
            return Reconciliation(
                groups=[FailureGroup(canonical="NOT-A-REAL-LABEL",
                                     variants=["SEAL LEAK"], role="mode")],
                causal=[])

    graph = FakeGraph([_row("P-101A")])
    stats = asyncio.run(DenoiseRunner(graph, Ghost()).run())
    assert stats.get("skipped", 0) == 0    # handled inline, not by the catch
    assert graph.merged == []              # and nothing was merged

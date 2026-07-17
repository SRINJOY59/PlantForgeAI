"""Deterministic detection: deciding THAT something is worth investigating.

Cheap, reliable Cypher - never an LLM for a yes/no this crisp. What a trigger
MEANS is the job of a use-case; this only decides that there is something to
mean. The scanners that emit a finished artifact rather than a trigger live in
usecases/ instead.
"""

import re
from dataclasses import dataclass

FAMILY_SUFFIX = re.compile(r"[A-Z]+$")   # P-101A -> family P-101


def family_of(tag: str) -> str:
    return FAMILY_SUFFIX.sub("", tag)


@dataclass
class Trigger:
    tag: str
    mode: str
    count: int
    family: str
    siblings: list           # sibling rows that share the mode
    graph_version: int


class FailureWatcher:
    def __init__(self, reader):
        self._reader = reader

    def detect(self, touched_node_ids: list, graph_version: int) -> list:
        triggers = []
        for node_id in touched_node_ids:
            if not node_id.startswith("equip:"):
                continue
            for row in self._reader.equipment_failures(node_id):
                trigger = self._trigger(row, graph_version)
                if trigger:
                    triggers.append(trigger)
        return triggers

    def _trigger(self, row, graph_version):
        tag, mode, count = row["tag"], row["mode"], row["count"]
        family = family_of(tag)
        siblings = self._reader.family_history(family, mode, exclude_tag=tag)
        if not siblings and count < 2:
            return None      # isolated first-time failure: nothing to learn yet
        return Trigger(tag=tag, mode=mode, count=count, family=family,
                       siblings=siblings, graph_version=graph_version)

"""Deterministic detection. FailureWatcher decides THAT a failure pattern
is worth investigating (cheap, reliable Cypher - never an LLM for a yes/no
this crisp); the InvestigatorAgent then reasons about it. ComplianceScanner
stays fully deterministic - 'is next_due < today' needs no investigation."""

import re
from dataclasses import dataclass

from plantmind_core.schemas import Alert, Citation

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


class ComplianceScanner:
    def __init__(self, reader):
        self._reader = reader

    def scan(self, today: str, graph_version: int) -> list:
        alerts = []
        for row in self._reader.overdue_inspections(today):
            alerts.append(Alert(
                kind="compliance", severity="warning",
                title=f"Overdue inspection: {row['equipment']} "
                      f"{row.get('inspection_type') or ''}".strip(),
                body=f"{row['equipment']} - {row.get('inspection_type') or 'inspection'} "
                     f"per {row['standard']} was due {row['next_due']} and is "
                     f"now overdue.",
                equipment=row["equipment"],
                citations=[Citation(doc_id=row["doc_id"],
                                    page=row.get("page"), snippet="")]
                if row.get("doc_id") else [],
                fingerprint=f"compliance:{row['equipment']}:{row['standard']}:"
                            f"{row['next_due']}",
                graph_version=graph_version))
        return alerts

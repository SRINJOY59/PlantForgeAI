import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))

from plantmind_core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_settings(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class FakeAgentReader:
    def __init__(self):
        self.failures = {}      # node_id -> [rows]
        self.family = {}        # (family, mode) -> [rows]
        self.overdue = []
        self.procedures = {}    # tag -> [rows]
        self.connections = {}   # tag -> [rows]
        self.work_orders = {}   # tag -> [rows]
        self.clauses = {}       # node_id -> [rows]
        self.mentions = {}      # node_id -> [rows]

    def equipment_failures(self, node_id):
        return self.failures.get(node_id, [])

    def governing_clauses(self, node_id):
        return self.clauses.get(node_id, [])

    def documents_mentioning(self, node_id):
        return self.mentions.get(node_id, [])

    def family_history(self, family, mode, exclude_tag):
        return [r for r in self.family.get((family, mode), [])
                if r["tag"] != exclude_tag]

    def procedures_for(self, tag):
        return self.procedures.get(tag, [])

    def connected_equipment(self, tag):
        return self.connections.get(tag, [])

    def work_orders_for(self, tag, limit=10):
        return self.work_orders.get(tag, [])[:limit]

    def overdue_inspections(self, today):
        return self.overdue

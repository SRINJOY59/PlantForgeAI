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

    def equipment_failures(self, node_id):
        return self.failures.get(node_id, [])

    def family_history(self, family, mode, exclude_tag):
        return [r for r in self.family.get((family, mode), [])
                if r["tag"] != exclude_tag]

    def overdue_inspections(self, today):
        return self.overdue

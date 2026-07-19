import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services"))


class FakeGateway:
    """Records calls; returns canned gateway responses."""

    def __init__(self):
        self.asked = []
        self.assessed = []

    def ask(self, question):
        self.asked.append(question)
        return {"text": "Four seal failures [doc:abc123]",
                "confidence": "high",
                "citations": [{"doc_id": "abc123",
                               "filename": "work_orders.csv", "page": None},
                              {"doc_id": "noname99", "page": 2}],
                "corrections": [{"doc_id": "abc123", "author": "eng@plant"}]}

    def assess(self, tag, summary):
        self.assessed.append((tag, summary))
        return {"body": "assessment...", "affected_equipment": ["PI-102"],
                "governing_clauses": ["OISD-STD-119"],
                "documents_to_revise": ["sop.md"], "verified": True,
                "unverified_claims": []}

    def metrics(self):
        return {"graph_version": 25, "queues": {"q_classify": 0}}


class FakeGraph:
    """Records the tag each lookup received."""

    def __init__(self):
        self.calls = []

    def _note(self, name, tag):
        self.calls.append((name, tag))
        return [{"tag": tag}]

    def failure_history(self, tag):
        return self._note("failure_history", tag)

    def connected_equipment(self, tag):
        return self._note("connected_equipment", tag)

    def governing_clauses(self, tag):
        return self._note("governing_clauses", tag)

    def documents_mentioning(self, tag):
        return self._note("documents_mentioning", tag)

    def fix_procedures(self, tag):
        return self._note("fix_procedures", tag)

    def work_orders(self, tag):
        return self._note("work_orders", tag)

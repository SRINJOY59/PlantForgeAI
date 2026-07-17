"""Overdue statutory inspections.

The one use-case with no agent in it. 'is next_due < today' is a crisp
question, and an LLM asked to answer it can only make it less reliable - so
this stays deterministic and produces its Alert directly, without the reason
step in base.py. It sits here rather than beside the watchers because what it
emits is the finished artifact, not a trigger for something else to think about.
"""

from plantmind_core.schemas import Alert, Citation


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

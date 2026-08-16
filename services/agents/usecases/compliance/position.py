"""The plant's compliance position: every statutory obligation and where it
stands today.

Separate from scanner.py on purpose. The scanner answers "what should alarm
right now" and emits Alerts; this answers "what is our position", which is what
a page renders and an auditor asks for. Same graph edges, different question -
and merging them would mean either alerting on things that are merely
approaching, or hiding compliant assets from a compliance view.
"""

from datetime import date, timedelta

# How far ahead counts as "due soon". A statutory inspection needs planning,
# a shutdown window and often a contractor, so a quarter's notice is the point
# at which it becomes someone's problem rather than a date on a list.
DUE_SOON_DAYS = 90


def _status(next_due: str, today: str, horizon: str) -> str:
    if next_due < today:
        return "overdue"
    if next_due <= horizon:
        return "due_soon"
    return "compliant"


def item_id(row: dict) -> str:
    """Stable across reads, so a scheduling decision made against one of these
    still refers to the same obligation on the next page load. Same shape as
    the scanner's alert fingerprint, for the same reason."""
    return (f"compliance:{row.get('equipment', '')}:"
            f"{row.get('standard', '')}:{row.get('next_due', '')}")


def position(rows: list, today: str | None = None) -> dict:
    """Shape the raw GOVERNED_BY rows into what the compliance view needs.

    Returns items plus the counts, computed here rather than in the client:
    two places counting the same thing is how a summary card ends up
    disagreeing with the list underneath it.
    """
    today = today or date.today().isoformat()
    horizon = (date.fromisoformat(today) + timedelta(days=DUE_SOON_DAYS)).isoformat()

    items = []
    for row in rows:
        next_due = row.get("next_due") or ""
        if not next_due:
            continue
        items.append({
            "id": item_id(row),
            "equipment": row.get("equipment") or "",
            "standard": row.get("standard") or "",
            "inspection_type": row.get("inspection_type") or "Inspection",
            "next_due": next_due,
            "last_inspection": row.get("last_inspection") or "",
            "revision": row.get("revision") or "",
            "doc_id": row.get("doc_id") or "",
            "page": row.get("page"),
            "status": _status(next_due, today, horizon),
        })

    counts = {"overdue": 0, "due_soon": 0, "compliant": 0}
    for it in items:
        counts[it["status"]] += 1

    # overdue first, then soonest due - a compliance page is read top-down by
    # someone deciding what to do this week
    order = {"overdue": 0, "due_soon": 1, "compliant": 2}
    items.sort(key=lambda i: (order[i["status"]], i["next_due"]))
    return {"items": items, "counts": counts, "as_of": today,
            "due_soon_days": DUE_SOON_DAYS}

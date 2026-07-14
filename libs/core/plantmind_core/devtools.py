"""Helpers for the module-level smoke tests (python -m <module> <file>)."""

from collections import Counter
from pathlib import Path


def find_file(arg: str) -> Path:
    """Resolve a file argument leniently: as given first, else strip any
    leading ../ and search upward from CWD - so sample paths work no matter
    how deep in the repo the command runs."""
    p = Path(arg)
    if p.exists():
        return p
    bare = Path(*[part for part in p.parts if part not in ("..", ".")])
    for parent in (Path.cwd(), *Path.cwd().parents):
        candidate = parent / bare
        if candidate.exists():
            return candidate
    raise FileNotFoundError(arg)


def summarize(csg) -> None:
    nodes = Counter(n.type.value for n in csg.nodes)
    edges = Counter(e.type.value for e in csg.edges)
    print(f"\ndoc_id: {csg.doc_id}")
    print(f"nodes ({sum(nodes.values())}): {dict(nodes)}")
    print(f"edges ({sum(edges.values())}): {dict(edges)}")

    for n in csg.nodes:
        if n.type.value in ("Equipment", "Instrument", "FailureMode",
                            "Procedure", "RegulationClause", "Person"):
            print(f"  [{n.type.value}] {n.surface_form}"
                  + (f"  {n.props}" if n.props else ""))
    for e in csg.edges:
        if e.type.value not in ("PART_OF", "MENTIONED_IN"):
            print(f"  ({e.src}) -{e.type.value}-> ({e.dst})")

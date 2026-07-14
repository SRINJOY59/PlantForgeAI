"""Turns a list of resolved CandidateSubgraphs into row sets ready for
UNWIND writes. Pure functions — no I/O — so the grouping logic is testable
without a database."""

import hashlib
from dataclasses import dataclass, field

from plantmind_core.schemas import CandidateSubgraph, Provenance


@dataclass
class WriteBatch:
    nodes_by_label: dict = field(default_factory=dict)   # label -> [row]
    edges_by_type: dict = field(default_factory=dict)    # edge type -> [row]
    node_ids: set = field(default_factory=set)
    edge_types: set = field(default_factory=set)
    doc_ids: set = field(default_factory=set)

    @property
    def empty(self) -> bool:
        return not self.nodes_by_label and not self.edges_by_type


def prov_hash(p: Provenance) -> str:
    parts = f"{p.doc_id}|{p.page}|{p.span}|{p.bbox}|{p.extractor_version}"
    return hashlib.sha1(parts.encode()).hexdigest()[:16]


def group_batch(subgraphs: list[CandidateSubgraph]) -> WriteBatch:
    batch = WriteBatch()

    for csg in subgraphs:
        # surface form -> canonical id, so edges written by extractors in
        # surface terms land on resolved nodes
        id_map = {}
        for node in csg.nodes:
            if not node.resolved_id:
                raise ValueError(
                    f"unresolved node '{node.surface_form}' in doc {csg.doc_id}"
                )
            id_map[node.surface_form] = node.resolved_id

            label = node.type.value
            row = {
                "id": node.resolved_id,
                "props": {"surface_form": node.surface_form, **node.props},
            }
            rows = batch.nodes_by_label.setdefault(label, [])
            existing = next((r for r in rows if r["id"] == row["id"]), None)
            if existing:
                existing["props"].update(row["props"])
            else:
                rows.append(row)
            batch.node_ids.add(node.resolved_id)

        for edge in csg.edges:
            row = {
                # endpoints not in the map are taken as already-canonical ids
                # (the resolver emits those for links to pre-existing nodes)
                "src": id_map.get(edge.src, edge.src),
                "dst": id_map.get(edge.dst, edge.dst),
                "prov_hash": prov_hash(edge.provenance),
                "props": {
                    **edge.props,
                    "doc_id": edge.provenance.doc_id,
                    "page": edge.provenance.page,
                    "extractor_version": edge.provenance.extractor_version,
                    "confidence": edge.provenance.confidence,
                },
            }
            batch.edges_by_type.setdefault(edge.type.value, []).append(row)
            batch.edge_types.add(edge.type.value)

        batch.doc_ids.add(csg.doc_id)

    return batch


def main():
    """usage (from plantmind/services):
    ../.venv/Scripts/python -m graphd.batching subgraph.json [...]
    Feed it resolved CandidateSubgraph json files and see the write shapes."""
    import sys
    from pathlib import Path

    subgraphs = [CandidateSubgraph.model_validate_json(Path(a).read_text())
                 for a in sys.argv[1:]]
    batch = group_batch(subgraphs)
    for label, rows in batch.nodes_by_label.items():
        print(f"\n{label}: {len(rows)} rows")
        for row in rows[:3]:
            print(f"   {row}")
    for edge_type, rows in batch.edges_by_type.items():
        print(f"\n{edge_type}: {len(rows)} rows")
        for row in rows[:3]:
            print(f"   {row['src']} -> {row['dst']}  (prov {row['prov_hash']})")


if __name__ == "__main__":
    main()

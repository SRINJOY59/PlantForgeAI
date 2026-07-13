"""Deterministic parser for structured plant exports (work orders,
inspection records). Detects the table kind from its headers. No LLM
anywhere near this path - these files are already machine-shaped."""

import csv
import io

from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)

EXTRACTOR_VERSION = "wo-parser-v1"


class TableParser:
    def parse(self, doc_id: str, content_hash: str, filename: str,
              data: bytes) -> CandidateSubgraph:
        text = data.decode("utf-8-sig", errors="replace")
        rows = [r for r in csv.DictReader(io.StringIO(text)) if any(r.values())]
        if not rows:
            raise ValueError(f"{filename}: no data rows")

        headers = set(rows[0].keys())
        if "wo_id" in headers:
            nodes, edges = self._work_orders(doc_id, rows)
        elif "inspection_type" in headers:
            nodes, edges = self._inspections(doc_id, rows)
        else:
            raise ValueError(f"{filename}: unrecognised table headers {sorted(headers)}")

        nodes.append(CandidateNode(type=NodeType.DOCUMENT, surface_form=doc_id,
                                   props={"filename": filename,
                                          "content_hash": content_hash}))
        return CandidateSubgraph(doc_id=doc_id, content_hash=content_hash,
                                 nodes=nodes, edges=edges)

    def _prov(self, doc_id: str, row_no: int) -> Provenance:
        # row number stands in for page - it's what a human needs to find
        # the source line again
        return Provenance(doc_id=doc_id, page=row_no,
                          extractor_version=EXTRACTOR_VERSION, confidence=1.0)

    def _work_orders(self, doc_id, rows):
        equipment, failures = {}, {}
        nodes, edges = [], []

        for row_no, row in enumerate(rows, start=1):
            wo_id = row["wo_id"].strip()
            tag = row["equipment_tag"].strip()
            code = row["failure_code"].strip()
            prov = self._prov(doc_id, row_no)

            nodes.append(CandidateNode(
                type=NodeType.WORK_ORDER, surface_form=wo_id,
                props={
                    "wo_id": wo_id,
                    "date": row.get("date", "").strip(),
                    "description": row.get("description", "").strip(),
                    "action_taken": row.get("action_taken", "").strip(),
                    "technician": row.get("technician", "").strip(),
                    "downtime_hours": _num(row.get("downtime_hours")),
                },
            ))
            equipment.setdefault(tag, CandidateNode(
                type=NodeType.EQUIPMENT, surface_form=tag))
            failures.setdefault(code, CandidateNode(
                type=NodeType.FAILURE_MODE, surface_form=code, props={"code": code}))

            edges.append(CandidateEdge(
                type=EdgeType.HAS_FAILURE, src=tag, dst=code, provenance=prov,
                props={"wo_id": wo_id, "date": row.get("date", "").strip()}))
            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=tag, dst=wo_id, provenance=prov))
            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=wo_id, dst=doc_id, provenance=prov))

        return nodes + list(equipment.values()) + list(failures.values()), edges

    def _inspections(self, doc_id, rows):
        equipment, standards = {}, {}
        nodes, edges = [], []

        for row_no, row in enumerate(rows, start=1):
            tag = row["equipment_tag"].strip()
            standard = row.get("standard", "").strip()
            prov = self._prov(doc_id, row_no)

            equipment.setdefault(tag, CandidateNode(
                type=NodeType.EQUIPMENT, surface_form=tag))

            if standard:
                standards.setdefault(standard, CandidateNode(
                    type=NodeType.REGULATION_CLAUSE, surface_form=standard))
                edges.append(CandidateEdge(
                    type=EdgeType.GOVERNED_BY, src=tag, dst=standard, provenance=prov,
                    props={
                        "record_id": row.get("record_id", "").strip(),
                        "inspection_type": row.get("inspection_type", "").strip(),
                        "result": row.get("result", "").strip(),
                        "date": row.get("date", "").strip(),
                        "next_due": row.get("next_due", "").strip(),
                        "remarks": row.get("remarks", "").strip(),
                    }))

            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id, provenance=prov))

        return nodes + list(equipment.values()) + list(standards.values()), edges


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None

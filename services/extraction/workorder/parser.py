"""Parser for structured plant exports (work orders, inspection records),
csv or excel. Column layout is resolved once per file by MappingInferrer;
row parsing itself stays deterministic - no LLM near the data."""

import csv
import io
import openpyxl

from plantmind_core.schemas import (
    CandidateEdge, CandidateNode, CandidateSubgraph, EdgeType, NodeType, Provenance,
)

from extraction.workorder.mapping import MappingInferrer, remap_rows

EXTRACTOR_VERSION = "wo-parser-v2"


class TableParser:
    def __init__(self, llm=None):
        self._inferrer = MappingInferrer(llm)

    async def parse(self, doc_id: str, content_hash: str, filename: str,
                    data: bytes) -> CandidateSubgraph:
        rows = _read_rows(filename, data)
        if not rows:
            raise ValueError(f"{filename}: no data rows")

        mapping = await self._inferrer.infer(list(rows[0].keys()), rows)
        rows = remap_rows(rows, mapping)

        if mapping.kind == "work_orders":
            nodes, edges = self._work_orders(doc_id, rows)
        else:
            nodes, edges = self._inspections(doc_id, rows)

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
            wo_id, tag, code = row["wo_id"], row["equipment_tag"], row["failure_code"]
            if not (wo_id and tag):
                continue
            prov = self._prov(doc_id, row_no)

            nodes.append(CandidateNode(
                type=NodeType.WORK_ORDER, surface_form=wo_id,
                props={
                    "wo_id": wo_id,
                    "date": row["date"],
                    "description": row["description"],
                    "action_taken": row["action_taken"],
                    "technician": row["technician"],
                    "downtime_hours": _num(row["downtime_hours"]),
                },
            ))
            equipment.setdefault(tag, CandidateNode(
                type=NodeType.EQUIPMENT, surface_form=tag))

            if code:
                failures.setdefault(code, CandidateNode(
                    type=NodeType.FAILURE_MODE, surface_form=code,
                    props={"code": code}))
                edges.append(CandidateEdge(
                    type=EdgeType.HAS_FAILURE, src=tag, dst=code, provenance=prov,
                    props={"wo_id": wo_id, "date": row["date"]}))

            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=tag, dst=wo_id, provenance=prov))
            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=wo_id, dst=doc_id, provenance=prov))

        return nodes + list(equipment.values()) + list(failures.values()), edges

    def _inspections(self, doc_id, rows):
        equipment, standards = {}, {}
        nodes, edges = [], []

        for row_no, row in enumerate(rows, start=1):
            tag = row["equipment_tag"]
            if not tag:
                continue
            standard = row["standard"]
            prov = self._prov(doc_id, row_no)

            equipment.setdefault(tag, CandidateNode(
                type=NodeType.EQUIPMENT, surface_form=tag))

            if standard:
                standards.setdefault(standard, CandidateNode(
                    type=NodeType.REGULATION_CLAUSE, surface_form=standard))
                edges.append(CandidateEdge(
                    type=EdgeType.GOVERNED_BY, src=tag, dst=standard, provenance=prov,
                    props={
                        "record_id": row["record_id"],
                        "inspection_type": row["inspection_type"],
                        "result": row["result"],
                        "date": row["date"],
                        "next_due": row["next_due"],
                        "remarks": row["remarks"],
                    }))

            edges.append(CandidateEdge(
                type=EdgeType.MENTIONED_IN, src=tag, dst=doc_id, provenance=prov))

        return nodes + list(equipment.values()) + list(standards.values()), edges


def _read_rows(filename: str, data: bytes) -> list[dict]:
    if filename.lower().endswith((".xlsx", ".xlsm", ".xls")):
        return _read_excel(data)
    text = data.decode("utf-8-sig", errors="replace")
    return [r for r in csv.DictReader(io.StringIO(text)) if any(r.values())]


def _read_excel(data: bytes) -> list[dict]:
    wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    try:
        for sheet in wb.worksheets:      # first sheet that actually has a table
            rows = sheet.iter_rows(values_only=True)
            headers = next(rows, None)
            if not headers or not any(headers):
                continue
            headers = [str(h).strip() if h is not None else "" for h in headers]
            out = []
            for values in rows:
                if not any(v is not None and str(v).strip() for v in values):
                    continue
                out.append({h: ("" if v is None else str(v))
                            for h, v in zip(headers, values) if h})
            if out:
                return out
        return []
    finally:
        wb.close()


def _num(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def main():
    """usage (from plantmind/services):
    python -m extraction.workorder.parser ../data/samples/work_orders.csv
    Known header layouts parse without an LLM; alien layouts need
    OPENROUTER_API_KEY in ../.env for the mapping call.
    """
    import asyncio
    import sys
    from pathlib import Path

    from plantmind_core.devtools import find_file, summarize

    llm = None
    try:
        from plantmind_core.llm import get_llm
        from plantmind_core.config import get_settings
        if get_settings().openrouter_api_key:
            llm = get_llm()
    except Exception:
        pass

    for arg in sys.argv[1:]:
        path = find_file(arg)
        csg = asyncio.run(TableParser(llm).parse("smoke-" + path.stem, "smoke-hash", path.name, path.read_bytes()))
        summarize(csg)


if __name__ == "__main__":
    main()

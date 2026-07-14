"""Column-mapping inference so the table parser survives real-world exports.
Known header sets map by rule (no tokens); anything else gets one cheap LLM
call that maps source headers onto our ontology, then parsing stays fully
deterministic over thousands of rows."""

from typing import Literal

from pydantic import BaseModel

from plantmind_core.llm import Tier
from plantmind_core.telemetry import get_logger

log = get_logger("extraction.mapping")

WO_FIELDS = ("wo_id", "equipment_tag", "failure_code", "date", "description",
             "action_taken", "technician", "downtime_hours")
INSPECTION_FIELDS = ("record_id", "equipment_tag", "inspection_type",
                     "standard", "result", "date", "next_due", "remarks")

WO_REQUIRED = {"wo_id", "equipment_tag", "failure_code"}
INSPECTION_REQUIRED = {"equipment_tag", "inspection_type"}


class TableMapping(BaseModel):
    """Every field holds the SOURCE column header that carries that
    information, or "" when the export has no such column."""
    kind: Literal["work_orders", "inspections", "unknown"]
    wo_id: str = ""
    equipment_tag: str = ""
    failure_code: str = ""
    date: str = ""
    description: str = ""
    action_taken: str = ""
    technician: str = ""
    downtime_hours: str = ""
    record_id: str = ""
    inspection_type: str = ""
    standard: str = ""
    result: str = ""
    next_due: str = ""
    remarks: str = ""


PROMPT = """This is an export from an industrial maintenance system.
Decide whether it is a work-order table or an inspection-records table,
then map our fields to the source column headers. Use the exact header
strings. Leave a field "" if no column carries that information.

Field meanings:
- wo_id: work order number   - equipment_tag: asset/equipment identifier
- failure_code: failure mode/code   - downtime_hours: downtime duration
- inspection_type: kind of inspection   - standard: governing standard/code
- next_due: next due date   - result: pass/fail outcome

Headers: {headers}

Sample rows:
{samples}"""


class MappingInferrer:
    def __init__(self, llm=None):
        self._llm = llm

    async def infer(self, headers: list[str], sample_rows: list[dict]) -> TableMapping:
        mapping = self._by_rule(set(headers))
        if mapping is None:
            if self._llm is None:
                raise ValueError(f"unknown table headers and no LLM wired: {headers}")
            samples = "\n".join(str(r) for r in sample_rows[:3])
            mapping = await self._llm.structured(
                [{"role": "user", "content": PROMPT.format(
                    headers=headers, samples=samples)}],
                TableMapping, tier=Tier.CHEAP)
            log.info("mapping inferred by llm", kind=mapping.kind)
        self._validate(mapping, set(headers))
        return mapping

    @staticmethod
    def _by_rule(headers: set) -> TableMapping | None:
        """Exports already using our field names map without any LLM."""
        if WO_REQUIRED <= headers:
            return TableMapping(kind="work_orders", **{
                f: f for f in WO_FIELDS if f in headers})
        if INSPECTION_REQUIRED <= headers:
            return TableMapping(kind="inspections", **{
                f: f for f in INSPECTION_FIELDS if f in headers})
        return None

    @staticmethod
    def _validate(mapping: TableMapping, headers: set):
        if mapping.kind == "unknown":
            raise ValueError("table not recognisable as work orders or inspections")

        required = WO_REQUIRED if mapping.kind == "work_orders" else INSPECTION_REQUIRED
        missing = [f for f in required if not getattr(mapping, f)]
        if missing:
            raise ValueError(f"mapping lacks required fields: {missing}")

        phantom = [f for f in TableMapping.model_fields if f != "kind"
                   and getattr(mapping, f) and getattr(mapping, f) not in headers]
        if phantom:
            raise ValueError(
                f"mapping references headers that do not exist: "
                f"{[getattr(mapping, f) for f in phantom]}")


def remap_rows(rows: list[dict], mapping: TableMapping) -> list[dict]:
    """Rewrite source rows into canonical field names."""
    fields = WO_FIELDS if mapping.kind == "work_orders" else INSPECTION_FIELDS
    out = []
    for row in rows:
        canonical = {}
        for field in fields:
            source = getattr(mapping, field)
            canonical[field] = (row.get(source) or "").strip() if source else ""
        out.append(canonical)
    return out

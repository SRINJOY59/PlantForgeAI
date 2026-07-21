"""What the graph can be asked, in the form an agent can call.

reader.py owns the Cypher; this owns the vocabulary. A tool is a capability of
the graph, not of a use-case: the failure investigation and a change impact
assessment both want to know what a pump is connected to, and neither should
own that question. Use-cases compose the list they need from here.
"""

from plantmind_core.llm import Tool


def _one_tag() -> dict:
    return {"type": "object",
            "properties": {"tag": {"type": "string"}},
            "required": ["tag"]}


def _id_for(tag: str) -> str:
    return f"equip:{tag}"


def failure_history(reader) -> Tool:
    return Tool("get_failure_history",
                "Failure modes and occurrence counts for an equipment tag. "
                "Where an engineer has corrected the documents behind a "
                "failure, 'corrections' carries what they said and "
                "'corrected_by' who said it. A correction overrules the "
                "documents it was filed against: reason from it, not from them.",
                _one_tag(),
                lambda tag: reader.equipment_failures(_id_for(tag)))


def sibling_history(reader) -> Tool:
    return Tool("get_sibling_history",
                "Failure history of sibling equipment (same family stem, "
                "e.g. 'P-101') for a given failure mode.",
                {"type": "object", "properties": {
                    "family": {"type": "string"},
                    "mode": {"type": "string"},
                    "exclude_tag": {"type": "string"}},
                 "required": ["family", "mode", "exclude_tag"]},
                reader.family_history)


def fix_procedures(reader) -> Tool:
    return Tool("get_fix_procedures",
                "Procedures that fix a piece of equipment.",
                _one_tag(), reader.procedures_for)


def connected_equipment(reader) -> Tool:
    return Tool("get_connected_equipment",
                "Equipment and instruments directly connected in the process.",
                _one_tag(), reader.connected_equipment)


def work_orders(reader) -> Tool:
    return Tool("get_work_orders",
                "Recent work orders and the actions taken on an equipment tag.",
                _one_tag(), reader.work_orders_for)


def governing_clauses(reader) -> Tool:
    return Tool("get_governing_clauses",
                "Regulation and standard clauses that govern a piece of "
                "equipment - what it is legally held to, and at which revision.",
                _one_tag(),
                lambda tag: reader.governing_clauses(_id_for(tag)))


def documents_mentioning(reader) -> Tool:
    return Tool("get_documents_mentioning",
                "Documents and procedures that refer to this equipment, and "
                "would therefore have to be revised if it changed.",
                _one_tag(),
                lambda tag: reader.documents_mentioning(_id_for(tag)))

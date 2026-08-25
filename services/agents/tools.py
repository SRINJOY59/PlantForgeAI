"""What the graph can be asked, in the form an agent can call.

reader.py owns the Cypher; this owns the vocabulary. A tool is a capability of
the graph, not of a use-case: the failure investigation and a change impact
assessment both want to know what a pump is connected to, and neither should
own that question. Use-cases compose the list they need from here.
"""

import json
import os
import urllib.request

from plantmind_core.llm import Tool
from plantmind_core.telemetry import get_logger

log = get_logger("agents.tools")


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
                _one_tag(),
                reader.connected_equipment)


def shared_utilities(reader) -> Tool:
    return Tool("get_shared_utilities",
                "Equipment sharing a utility header with the given tag. Use this to find parallel reactors affected by a shared-coolant header breach.",
                _one_tag(),
                lambda tag: reader.shared_utilities(tag))


def downstream_units(reader) -> Tool:
    return Tool("get_downstream_units",
                "Downstream equipment fed by the given unit (e.g. CSTR feed into Column). Use this to trace process deviations forward.",
                _one_tag(),
                lambda tag: reader.downstream_units(tag))


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


def tep_live_status(get_status_fn) -> Tool:
    """Return a Tool that fetches live TEP simulator status.

    get_status_fn: async callable returning the /sim/tep/status dict.
    Used by both Q&A and RCA agents to answer questions like
    'What is the reactor pressure right now?'
    """
    return Tool(
        "get_tep_live_status",
        "Returns the current live readings for all TEP unit areas "
        "(REACTOR, CONDENSER, SEPARATOR, STRIPPER, COMPRESSOR, PRODUCT-SPLIT). "
        "Call this when the user asks about current plant conditions, "
        "e.g. 'What is the reactor temperature?' or 'Is there a high-pressure alarm?'. "
        "The result includes active_idvs (fault codes) and unit_areas with sub-tags.",
        {"type": "object", "properties": {}, "required": []},
        get_status_fn,
    )


def tep_idv_context() -> Tool:
    """Return a Tool that maps IDV fault numbers to descriptions.

    Useful for RCA to explain what fault has been injected.
    """
    IDV_TABLE = {
        1:  "A/C feed ratio step (stream 4) — common A-shortage fault",
        2:  "B composition step (stream 4) — inert buildup",
        3:  "D feed temperature step — upstream disturbance",
        4:  "Reactor coolant inlet temperature step — runaway risk",
        5:  "Condenser coolant inlet temperature step",
        6:  "A feed loss — starvation fault, critical",
        7:  "C header pressure loss — partial feed cutoff",
        8:  "A/B/C composition variation — random disturbance",
        9:  "D feed temperature variation — noise",
        10: "C feed temperature variation — noise",
        11: "Reactor coolant variation — noise",
        12: "Condenser coolant variation — noise",
        13: "Reaction kinetics drift — catalyst ageing",
        14: "Reactor coolant valve stuck — loss of cooling",
        15: "Condenser coolant valve stuck",
        16: "Heat exchanger partial fouling",
        17: "E feed disturbance",
        18: "D feed surge",
        19: "Kinetics runaway — emergency",
        20: "Heat exchanger severe fouling — emergency",
        21: "Stream 4 valve constant — reduced controllability",
    }

    def _live_faults() -> dict:
        """What the simulator says is wrong RIGHT NOW.

        Without this the tool was a dictionary and nothing more: it could
        describe IDV 6 if you already knew IDV 6 was active, and answered an
        empty call with {"active": []}. The agent has no other way to learn
        the active set, so every investigation concluded "no IDV fault is
        active" while the plant was running two of them - the single most
        useful fact about the upset, and the one the report denied.
        """
        url = os.environ.get("TEP_SIM_URL", "http://tep-sim:8012") + "/sim/status"
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                status = json.loads(r.read().decode())
        except Exception as e:
            log.warning("could not read live sim status for IDV context",
                        error=str(e)[:160])
            return {}
        return status.get("active_faults") or {}

    def describe_idvs(idv_list=None):
        faults = _live_faults()
        live = [int(i) for i in (faults.get("_active_idvs") or [])]

        # An explicit list still wins (explaining a historical alert), but an
        # empty call now means "tell me what is active", not "nothing is".
        if not idv_list:
            idv_list = live
        elif isinstance(idv_list, int):
            idv_list = [idv_list]

        # the raw fault parameters alongside the codes: "feed_a_bias: -50.0"
        # is the magnitude an engineer reasons about, not just the IDV number
        params = {k: v for k, v in faults.items() if not k.startswith("_")}

        if not idv_list:
            return {"active": [], "descriptions": [],
                    "live_fault_parameters": params,
                    "note": "The simulator reports no IDV fault injected. "
                            "Any deviation is process drift, controller "
                            "action or an unmodelled disturbance."}
        return {
            "active": idv_list,
            "currently_injected_in_simulator": live,
            "descriptions": [IDV_TABLE.get(i, f"IDV-{i}: unknown") for i in idv_list],
            "live_fault_parameters": params,
        }

    return Tool(
        "describe_tep_idv_faults",
        "The IDV faults injected in the TEP simulator RIGHT NOW, with "
        "human-readable descriptions and the raw fault parameters. Call this "
        "on ANY simulator alarm before concluding a cause - it is the only "
        "way to learn what was actually injected. Pass idv_list only to "
        "explain specific codes; omit it to get the live active set.",
        {
            "type": "object",
            "properties": {
                "idv_list": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "Optional. Specific IDV numbers (1-21) to "
                                   "explain. Omit to read the live active set.",
                }
            },
            "required": [],
        },
        lambda idv_list=None: describe_idvs(idv_list),
    )


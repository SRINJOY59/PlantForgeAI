"""Offline tests for the Permit-to-Work agent.

The full path — tools bound to the reader, trace -> WorkPermit, grounding —
runs without a network.  The ScriptedLLM controls exactly what the model
returns, so the tests assert the permit's structured fields and safety logic,
not the model's prose.
"""

import asyncio
from types import SimpleNamespace

from plantmind_core.schemas import PermitRequest

from agents.usecases.permit_to_work import PermitToWorkAgent
from agents.usecases.permit_to_work import permit_builder
from conftest import FakeAgentReader


# ── Test doubles ──────────────────────────────────────────────────────────────

def tool_call(name, args):
    return SimpleNamespace(id="c1", type="function",
                           function=SimpleNamespace(name=name, arguments=args))


def msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class ScriptedLLM:
    def __init__(self, *messages, stream_text="permit narrative"):
        self.queue = list(messages)
        self._stream_text = stream_text

    async def chat_with_tools(self, messages, tools, tier=None, max_tokens=2048):
        return self.queue.pop(0)

    async def complete(self, messages, tier=None, max_tokens=2048):
        return "final"

    async def stream(self, messages, tier=None, max_tokens=2048, temperature=0.0):
        for word in self._stream_text.split(" "):
            yield word + " "


# ── Fixtures ──────────────────────────────────────────────────────────────────

REQUEST = PermitRequest(
    tag="P-101A",
    work_description="Replace mechanical seal on centrifugal pump",
    requested_by="tech@plant.com",
)

HOT_WORK_REQUEST = PermitRequest(
    tag="V-201",
    work_description="Weld patch on vessel nozzle flange",
    requested_by="welder@plant.com",
)

CSE_REQUEST = PermitRequest(
    tag="T-301",
    work_description="Confined space entry to inspect tank internals",
    requested_by="inspector@plant.com",
)


def full_reader():
    r = FakeAgentReader()
    r.failures["equip:P-101A"] = [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3,
         "causes": ["cavitation", "seal wear"],
         "docs": ["sop-101.md"], "sources": ["document"],
         "corrected_by": [], "corrections": [], "correction_ids": []}
    ]
    r.clauses["equip:P-101A"] = [
        {"clause": "OISD-STD-119", "revision": "2019",
         "inspection_type": "Condition monitoring",
         "next_due": "2025-09-15", "doc_id": "ins-1"}
    ]
    r.connections["P-101A"] = [
        {"tag": "PI-102", "label": "Instrument"},
        {"tag": "XV-101", "label": "Instrument"},
    ]
    r.procedures["P-101A"] = [
        {"procedure": "SOP-PUMP-SEAL-001", "docs": ["sop-101.md"]}
    ]
    r.work_orders["P-101A"] = [
        {"wo_id": "WO-2025-055", "date": "2025-03-12",
         "description": "Seal inspection", "action_taken": "Replaced seal rings"}
    ]
    return r


# ── Permit type classification ────────────────────────────────────────────────

def test_cold_work_classified_correctly():
    assert permit_builder.classify_permit("replace mechanical seal") == "Cold Work"


def test_hot_work_classified_from_keyword():
    assert permit_builder.classify_permit("weld patch on nozzle") == "Hot Work"


def test_cse_classified_from_phrase():
    result = permit_builder.classify_permit("confined space entry to inspect tank")
    assert result == "Confined Space Entry"


def test_electrical_classified():
    assert permit_builder.classify_permit(
        "de-energise motor control panel for inspection") == "Electrical Isolation"


def test_generic_fallback():
    assert permit_builder.classify_permit("general housekeeping") == "General Maintenance"


# ── Hazard extraction from trace ──────────────────────────────────────────────

def test_hazards_extracted_from_seal_leak_failure():
    trace = [
        ("get_failure_history", {}, [
            {"tag": "P-101A", "mode": "SEAL-LEAK",
             "causes": ["cavitation"], "count": 3}
        ])
    ]
    hazards = permit_builder.hazards_from_trace(trace)
    assert any("seal" in h.lower() or "leak" in h.lower() or "cavitation" in h.lower()
               for h in hazards)


def test_no_hazards_from_empty_trace():
    assert permit_builder.hazards_from_trace([]) == []


# ── Structured fields harvested from tools ────────────────────────────────────

def test_isolation_points_come_from_connected_equipment_tool():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_connected_equipment", '{"tag": "P-101A"}')]),
        msg(content="Lock out PI-102 and XV-101 before starting work."),
    )
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm)
                         .draft_permit(REQUEST, graph_version=7))

    assert "PI-102" in result.isolation_points
    assert "XV-101" in result.isolation_points
    assert result.graph_version == 7


def test_governing_clauses_harvested_not_invented():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_governing_clauses", '{"tag": "P-101A"}')]),
        msg(content="Equipment is governed by OISD-STD-119."),
    )
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm).draft_permit(REQUEST))
    assert "OISD-STD-119" in result.governing_clauses


def test_procedures_harvested_from_fix_procedures_tool():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_fix_procedures", '{"tag": "P-101A"}')]),
        msg(content="Follow SOP-PUMP-SEAL-001."),
    )
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm).draft_permit(REQUEST))
    assert "SOP-PUMP-SEAL-001" in result.procedures_to_follow


# ── PPE defaults and extras ───────────────────────────────────────────────────

def test_default_ppe_always_present():
    llm = ScriptedLLM(msg(content="No tools needed."))
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm).draft_permit(REQUEST))
    ppe_text = " ".join(result.required_ppe).lower()
    assert "hard hat" in ppe_text
    assert "glove" in ppe_text


def test_hot_work_ppe_includes_fr_clothing():
    r = FakeAgentReader()
    llm = ScriptedLLM(msg(content="Weld nozzle."))
    result = asyncio.run(PermitToWorkAgent(r, llm=llm).draft_permit(HOT_WORK_REQUEST))
    assert result.permit_type == "Hot Work"
    ppe_text = " ".join(result.required_ppe).lower()
    assert "fire-retardant" in ppe_text or "fr" in ppe_text


def test_cse_ppe_includes_gas_monitor_and_harness():
    r = FakeAgentReader()
    llm = ScriptedLLM(msg(content="Enter tank."))
    result = asyncio.run(PermitToWorkAgent(r, llm=llm).draft_permit(CSE_REQUEST))
    assert result.permit_type == "Confined Space Entry"
    ppe_text = " ".join(result.required_ppe).lower()
    assert "gas monitor" in ppe_text or "monitor" in ppe_text
    assert "harness" in ppe_text


# ── Grounding ─────────────────────────────────────────────────────────────────

def test_invented_tag_marks_permit_unverified():
    llm = ScriptedLLM(
        msg(content="Also isolate X-999 before starting."),
    )
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm).draft_permit(REQUEST))
    assert result.verified is False
    assert "X-999" in result.unverified_claims
    assert "UNVERIFIED" in result.body


def test_permit_is_verified_when_all_tags_come_from_tools():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_connected_equipment", '{"tag": "P-101A"}')]),
        msg(content="Isolate PI-102 and XV-101 per the isolation list."),
    )
    result = asyncio.run(PermitToWorkAgent(full_reader(), llm=llm).draft_permit(REQUEST))
    assert result.verified is True


# ── Streaming interface ───────────────────────────────────────────────────────

def test_draft_permit_stream_emits_steps_tokens_then_done():
    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_connected_equipment", '{"tag": "P-101A"}')]),
        msg(tool_calls=[tool_call("get_governing_clauses", '{"tag": "P-101A"}')]),
        msg(content="ignored — stream regenerates final synthesis"),
        stream_text="Lock out PI-102 and XV-101.",
    )

    async def drive():
        steps, tokens, done = [], [], None
        async for kind, payload in PermitToWorkAgent(full_reader(), llm=llm) \
                .draft_permit_stream(REQUEST, graph_version=9):
            if kind == "step":
                steps.append(payload)
            elif kind == "token":
                tokens.append(payload)
            elif kind == "done":
                done = payload
        return steps, tokens, done

    steps, tokens, done = asyncio.run(drive())

    assert "get_connected_equipment" in steps
    assert "get_governing_clauses" in steps
    assert len(tokens) > 1
    assert "".join(tokens).strip() == "Lock out PI-102 and XV-101."
    assert done is not None
    assert done.graph_version == 9
    assert done.request.tag == "P-101A"

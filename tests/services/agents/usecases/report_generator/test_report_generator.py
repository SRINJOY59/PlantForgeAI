"""Offline test suite for the Report Generator agent.

Ensures that the LLM call, graph tools query, PDF rendering, plotting,
and MinIO storage work seamlessly in an offline/mock environment.
"""

import asyncio
from types import SimpleNamespace
import pytest

from plantmind_core.storage import ObjectStore
from agents.usecases.report_generator import ReportGeneratorAgent, pdf_renderer
from conftest import FakeAgentReader


def tool_call(name, args):
    return SimpleNamespace(id="c1", type="function",
                           function=SimpleNamespace(name=name, arguments=args))


def msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


class ScriptedLLM:
    def __init__(self, *messages):
        self.queue = list(messages)

    async def chat_with_tools(self, messages, tools, tier=None, max_tokens=2048):
        return self.queue.pop(0)

    async def complete(self, messages, tier=None, max_tokens=2048):
        return "final"


class FakeObjectStore:
    files = {}

    def put(self, key: str, data: bytes, content_type=None):
        self.files[key] = data

    @classmethod
    def from_settings(cls):
        return cls()


@pytest.fixture
def mock_storage(monkeypatch):
    FakeObjectStore.files.clear()
    monkeypatch.setattr("plantmind_core.storage.ObjectStore.from_settings", FakeObjectStore.from_settings)
    return FakeObjectStore.files


def test_pdf_renderer_produces_magic_pdf_header():
    md = """# Asset Report P-101A
## Failure History
- Mode: leak, Count: 2
- Mode: vibration, Count: 1

| Mode | Count |
|---|---|
| leak | 2 |
| vibration | 1 |
"""
    failure_data = [
        {"mode": "leak", "count": 2},
        {"mode": "vibration", "count": 1}
    ]
    pdf_bytes = pdf_renderer.render_report_pdf(md, failure_data)
    assert pdf_bytes.startswith(b"%PDF")
    assert len(pdf_bytes) > 1000


def test_pdf_renderer_with_empty_failure_data():
    md = "# Asset Report P-101A\nNo failures recorded."
    pdf_bytes = pdf_renderer.render_report_pdf(md, [])
    assert pdf_bytes.startswith(b"%PDF")


def test_agent_generates_report_and_stores_pdf(mock_storage):
    reader = FakeAgentReader()
    reader.failures["equip:P-101A"] = [
        {"tag": "P-101A", "mode": "SEAL-LEAK", "count": 3}
    ]

    llm = ScriptedLLM(
        msg(tool_calls=[tool_call("get_failure_history", '{"tag": "P-101A"}')]),
        msg(content="# Report P-101A\n\nSeal leak occurred 3 times.")
    )

    agent = ReportGeneratorAgent(reader, llm=llm)
    res = asyncio.run(agent.generate_report("P-101A", graph_version=5))

    assert res["tag"] == "P-101A"
    assert "# Report P-101A" in res["markdown"]
    assert "doc_id" in res
    assert res["graph_version"] == 5
    assert res["verified"] is True

    # Confirm it was uploaded to mock storage
    expected_key = f"raw/{res['doc_id']}/P-101A_report.pdf"
    assert expected_key in mock_storage
    assert mock_storage[expected_key].startswith(b"%PDF")

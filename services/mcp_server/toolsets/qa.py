"""Open-question answering over the plant graph.

The tool methods ARE the implementation - register() hands the bound methods to
FastMCP, which reads their signatures and docstrings as the tool schema the
client's model sees. That keeps the logic callable directly in tests, with a
fake backend, no protocol in the way.
"""


class QaToolset:
    def __init__(self, gateway):
        self._gateway = gateway

    def register(self, mcp) -> None:
        mcp.add_tool(self.ask_plant)

    def ask_plant(self, question: str) -> dict:
        """Ask the plant knowledge graph an open question (failures,
        procedures, inspections, process connections). Returns a grounded
        answer with citations to the plant's own documents; confidence
        reflects how well the answer traced to evidence."""
        answer = self._gateway.ask(question)
        return {
            "answer": answer.get("text"),
            "confidence": answer.get("confidence"),
            "citations": [
                {"document": c.get("filename") or c.get("doc_id"),
                 "page": c.get("page")}
                for c in answer.get("citations", [])],
            "corrections": answer.get("corrections", []),
        }

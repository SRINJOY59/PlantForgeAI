"""Management-of-Change assessment, exposed to MCP clients."""


class ChangeToolset:
    def __init__(self, gateway):
        self._gateway = gateway

    def register(self, mcp) -> None:
        mcp.add_tool(self.assess_change)

    def assess_change(self, tag: str, summary: str) -> dict:
        """Impact assessment for a PROPOSED change to a piece of equipment
        (Management of Change). Walks the graph for affected equipment,
        governing clauses and documents needing revision. Slow (~30s). Never
        approves or rejects - it gathers the evidence a human reviewer signs
        off on."""
        result = self._gateway.assess(tag.strip().upper(), summary)
        return {
            "body": result.get("body"),
            "affected_equipment": result.get("affected_equipment", []),
            "governing_clauses": result.get("governing_clauses", []),
            "documents_to_revise": result.get("documents_to_revise", []),
            "verified": result.get("verified"),
            "unverified_claims": result.get("unverified_claims", []),
        }

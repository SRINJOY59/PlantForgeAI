"""Direct structured lookups against the knowledge graph - the same queries the
in-app agents run, corrections included. Tags are normalised here (strip +
uppercase) so 'p-101a' from a chat client hits the same node as 'P-101A'."""


class GraphLookupToolset:
    def __init__(self, graph):
        self._graph = graph

    def register(self, mcp) -> None:
        for tool in (self.get_failure_history, self.get_connected_equipment,
                     self.get_governing_clauses, self.get_documents_mentioning,
                     self.get_fix_procedures, self.get_work_orders):
            mcp.add_tool(tool)

    @staticmethod
    def _tag(tag: str) -> str:
        return tag.strip().upper()

    def get_failure_history(self, tag: str) -> list:
        """Failure modes and occurrence counts for an equipment tag (e.g.
        P-101A). Where an engineer has corrected the record, 'corrections'
        carries what they said - a correction overrules the documents it was
        filed against."""
        return self._graph.failure_history(self._tag(tag))

    def get_connected_equipment(self, tag: str) -> list:
        """Equipment and instruments directly connected to a tag in the
        process - the physical neighbourhood a failure or a change can
        propagate into."""
        return self._graph.connected_equipment(self._tag(tag))

    def get_governing_clauses(self, tag: str) -> list:
        """The regulation/standard clauses an equipment tag is legally held
        to, with inspection type, last inspection and next-due date."""
        return self._graph.governing_clauses(self._tag(tag))

    def get_documents_mentioning(self, tag: str) -> list:
        """Documents, procedures and work orders that reference an equipment
        tag - the paper trail that would need revising if the equipment
        changed."""
        return self._graph.documents_mentioning(self._tag(tag))

    def get_fix_procedures(self, tag: str) -> list:
        """Named procedures on file that fix a piece of equipment."""
        return self._graph.fix_procedures(self._tag(tag))

    def get_work_orders(self, tag: str) -> list:
        """Recent work orders for an equipment tag: what broke, what was
        done, who did it, and the downtime."""
        return self._graph.work_orders(self._tag(tag))

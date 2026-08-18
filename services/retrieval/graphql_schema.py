"""Strawberry GraphQL schema for the PlantMind knowledge graph.

Exposes equipment, connections, failure modes, documents, regulations,
work orders, and procedures through a typed GraphQL API.  Every resolver
delegates to the existing Neo4j reads via GraphQLReader — no new Cypher
queries were written for this layer.

Mount with:
    from strawberry.fastapi import GraphQLRouter
    app.include_router(GraphQLRouter(schema), prefix="/graphql")
"""

from __future__ import annotations

from typing import Optional

import strawberry
from strawberry.scalars import JSON

# The reader is wired at startup by retrieval/main.py
_reader = None


def set_reader(reader):
    global _reader
    _reader = reader


def get_reader():
    if _reader is None:
        raise RuntimeError("GraphQL reader not initialised — call set_reader() at startup")
    return _reader


# ------------------------------------------------------------------- types

@strawberry.type
class FailureMode:
    mode: str
    count: int
    causes: list[str]
    docs: list[str]


@strawberry.type
class Document:
    id: strawberry.ID
    filename: Optional[str] = None
    label: Optional[str] = None


@strawberry.type
class RegulationClause:
    clause: str
    revision: Optional[str] = None
    inspection_type: Optional[str] = None
    next_due: Optional[str] = None
    last_inspection: Optional[str] = None
    doc_id: Optional[str] = None


@strawberry.type
class WorkOrder:
    wo_id: str
    date: Optional[str] = None
    description: Optional[str] = None
    action_taken: Optional[str] = None


@strawberry.type
class Procedure:
    procedure: str
    docs: list[str]


@strawberry.type
class Equipment:
    """A piece of plant equipment with all its graph relationships."""
    id: strawberry.ID
    tag: str
    label: str

    @strawberry.field
    def failures(self) -> list[FailureMode]:
        rows = get_reader().equipment_failures(self.tag)
        return [FailureMode(
            mode=r.get("mode", ""),
            count=r.get("count", 0),
            causes=r.get("causes") or [],
            docs=r.get("docs") or [],
        ) for r in rows]

    @strawberry.field
    def connections(self) -> list[GraphNode]:
        rows = get_reader().equipment_connections(self.tag)
        return [GraphNode(
            id=strawberry.ID(r.get("id", "")),
            label=r.get("label", "Entity"),
            surface=r.get("surface", ""),
        ) for r in rows]

    @strawberry.field
    def documents(self) -> list[Document]:
        rows = get_reader().equipment_documents(self.tag)
        return [Document(
            id=strawberry.ID(r.get("id", "")),
            filename=r.get("filename"),
            label=r.get("label"),
        ) for r in rows]

    @strawberry.field
    def regulations(self) -> list[RegulationClause]:
        rows = get_reader().equipment_regulations(self.tag)
        return [RegulationClause(
            clause=r.get("clause", ""),
            revision=r.get("revision"),
            inspection_type=r.get("inspection_type"),
            next_due=r.get("next_due"),
            last_inspection=r.get("last_inspection"),
            doc_id=r.get("doc_id"),
        ) for r in rows]

    @strawberry.field
    def work_orders(self, limit: int = 10) -> list[WorkOrder]:
        rows = get_reader().equipment_work_orders(self.tag, limit)
        return [WorkOrder(
            wo_id=r.get("wo_id", ""),
            date=r.get("date"),
            description=r.get("description"),
            action_taken=r.get("action_taken"),
        ) for r in rows]

    @strawberry.field
    def procedures(self) -> list[Procedure]:
        rows = get_reader().equipment_procedures(self.tag)
        return [Procedure(
            procedure=r.get("procedure", ""),
            docs=r.get("docs") or [],
        ) for r in rows]


@strawberry.type
class GraphNode:
    id: strawberry.ID
    label: str
    surface: str
    props: Optional[JSON] = None


@strawberry.type
class GraphEdge:
    src: strawberry.ID
    dst: strawberry.ID
    type: str


@strawberry.type
class PlantGraph:
    nodes: list[GraphNode]
    edges: list[GraphEdge]


@strawberry.type
class InspectionItem:
    equipment: str
    standard: str
    inspection_type: Optional[str] = None
    next_due: Optional[str] = None
    last_inspection: Optional[str] = None
    revision: Optional[str] = None
    doc_id: Optional[str] = None


# ---------------------------------------------------------------- query root

@strawberry.type
class Query:
    @strawberry.field(description="Full plant graph snapshot for the explorer view.")
    def plant_graph(self, limit: int = 400) -> PlantGraph:
        data = get_reader().plant_graph(limit)
        nodes = [GraphNode(
            id=strawberry.ID(n["id"]),
            label=n.get("label", "Entity"),
            surface=n.get("surface", ""),
            props=n.get("props"),
        ) for n in data.get("nodes", [])]
        edges = [GraphEdge(
            src=strawberry.ID(e["src"]),
            dst=strawberry.ID(e["dst"]),
            type=e["type"],
        ) for e in data.get("edges", [])]
        return PlantGraph(nodes=nodes, edges=edges)

    @strawberry.field(description="Look up one piece of equipment by its tag (e.g. 'P-101A', 'REACTOR').")
    def equipment(self, tag: str) -> Optional[Equipment]:
        rec = get_reader().equipment_by_tag(tag)
        if not rec:
            return None
        return Equipment(
            id=strawberry.ID(rec["id"]),
            tag=rec.get("surface", tag),
            label=rec.get("label", "Equipment"),
        )

    @strawberry.field(description="Search entities by name fragment.")
    def search_entities(self, phrase: str, limit: int = 10) -> list[GraphNode]:
        rows = get_reader().search_entities(phrase, limit)
        return [GraphNode(
            id=strawberry.ID(r["id"]),
            label=r.get("label", "Entity"),
            surface=r.get("surface", ""),
        ) for r in rows]

    @strawberry.field(description="All documents in the knowledge graph.")
    def documents(self) -> list[Document]:
        rows = get_reader().all_documents()
        return [Document(
            id=strawberry.ID(r.get("id", "")),
            filename=r.get("filename"),
        ) for r in rows]

    @strawberry.field(description="Statutory inspection schedule — every obligation with a due date.")
    def inspection_schedule(self) -> list[InspectionItem]:
        rows = get_reader().inspection_schedule()
        return [InspectionItem(
            equipment=r.get("equipment", ""),
            standard=r.get("standard", ""),
            inspection_type=r.get("inspection_type"),
            next_due=r.get("next_due"),
            last_inspection=r.get("last_inspection"),
            revision=r.get("revision"),
            doc_id=r.get("doc_id"),
        ) for r in rows]


schema = strawberry.Schema(query=Query)

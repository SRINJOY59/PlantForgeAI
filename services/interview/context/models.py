"""The shape of an employee's work context. Kept apart from the builder and
the graph reader so the domain (SessionMemory carries a WorkContext) can depend
on the data without dragging in Neo4j."""

from pydantic import BaseModel


class EquipmentContext(BaseModel):
    tag: str
    failures: list = []
    work_orders: list = []
    procedures: list = []
    connected: list = []


class WorkContext(BaseModel):
    profile: dict
    equipment: list[EquipmentContext] = []
    person_docs: list = []
    brief: str = ""

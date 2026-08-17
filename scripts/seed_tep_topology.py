"""One-time idempotent Neo4j seed script for TEP (Tennessee Eastman Process) topology.

Seeds all 10 equipment/line nodes, process flow CONNECTED_TO edges,
FEEDS edges, and stream labels. Uses MERGE to be safe to run repeatedly.
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

_repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo / "libs" / "core"))

from neo4j import GraphDatabase
from plantmind_core.config import get_settings

# Import topology from simulation package
sys.path.insert(0, str(_repo / "services"))
from simulation.tep.topology import TEP_NODES, TEP_CONNECTIONS


def main():
    s = get_settings()
    print(f"Connecting to Neo4j at {s.neo4j_uri}...")
    driver = GraphDatabase.driver(
        s.neo4j_uri,
        auth=(s.neo4j_user, s.neo4j_password),
    )

    with driver.session() as session:
        # 1. Create equipment/line nodes
        print("Seeding TEP equipment nodes...")
        for node in TEP_NODES:
            label = node["type"]
            query = f"""
            MERGE (e:Entity {{id: $id}})
            SET e :Equipment, e :{label},
                e.surface_form = $tag,
                e.unit = $unit,
                e.type = $type,
                e.plant = 'TEP'
            """
            session.run(query, id=node["id"], tag=node["tag"],
                        unit=node["unit"], type=node["type"])

        # 2. Seed process flow edges
        print("Seeding TEP process flow edges...")
        for src_tag, dst_tag, relation, stream_label in TEP_CONNECTIONS:
            query = f"""
            MATCH (a:Equipment {{surface_form: $src}})
            MATCH (b:Equipment {{surface_form: $dst}})
            MERGE (a)-[r:{relation}]->(b)
            SET r.stream = $stream,
                r.source = 'design',
                r.plant = 'TEP'
            """
            session.run(query, src=src_tag, dst=dst_tag, stream=stream_label)

        # 3. Seed Procedure / SOP knowledge nodes for TEP
        print("Seeding TEP SOPs...")
        sops = [
            {
                "id": "sop:TEP-STARTUP",
                "name": "TEP Plant Startup Procedure",
                "description": "Standard startup sequence for the Tennessee Eastman plant.",
                "applies_to": "TEP",
            },
            {
                "id": "sop:TEP-REACTOR-T-HIGH",
                "name": "High Reactor Temperature Response",
                "description": "Increase coolant flow via REACTOR-COOL valve. Check IDV-4 (coolant inlet T step).",
                "applies_to": "REACTOR",
            },
            {
                "id": "sop:TEP-REACTOR-P-HIGH",
                "name": "High Reactor Pressure Response",
                "description": "Open purge valve. Check inert B accumulation. Verify feed ratios.",
                "applies_to": "REACTOR",
            },
            {
                "id": "sop:TEP-SEP-LEVEL-LOW",
                "name": "Low Separator Level Response",
                "description": "Close separator liquid outlet valve. Check feed rate to reactor.",
                "applies_to": "SEPARATOR",
            },
            {
                "id": "sop:TEP-PRODUCT-PURITY",
                "name": "Low Product Purity Response",
                "description": "Check stripper steam. Verify G/H split valve. Review reactor compositions.",
                "applies_to": "PRODUCT-SPLIT",
            },
        ]
        for sop in sops:
            query = """
            MERGE (s:Procedure {id: $id})
            SET s.name = $name,
                s.description = $description,
                s.applies_to = $applies_to,
                s.plant = 'TEP'
            """
            session.run(query, **sop)
            # Link SOP to equipment
            query2 = """
            MATCH (s:Procedure {id: $sop_id})
            MATCH (e:Equipment {surface_form: $area})
            MERGE (e)-[r:GOVERNED_BY]->(s)
            """
            session.run(query2, sop_id=sop["id"], area=sop["applies_to"])

    driver.close()
    print("TEP topology seed complete.")


if __name__ == "__main__":
    main()

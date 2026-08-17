"""One-time idempotent Neo4j seed script for CSTR & Column demo train topology.

Seeds equipment nodes, CONNECTED_TO process flow edges, SHARES_HEADER coolant edges,
FEEDS cross-unit edges, and Procedures/SOPs with GOVERNED_BY links.
Uses MERGE to ensure it is safe to run repeatedly.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path

# Bootstrap path to resolve plantmind_core imports
_repo = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo / "libs" / "core"))

from neo4j import GraphDatabase
from plantmind_core.config import get_settings


def main():
    s = get_settings()
    print(f"Connecting to Neo4j at {s.neo4j_uri}...")
    
    driver = GraphDatabase.driver(
        s.neo4j_uri,
        auth=(s.neo4j_user, s.neo4j_password)
    )

    with driver.session() as session:
        # 1. Create Equipment/Line Nodes
        nodes = [
            {"id": "equip:FEED", "tag": "FEED", "type": "Line", "unit": "DemoTrain1"},
            {"id": "equip:CSTR-101", "tag": "CSTR-101", "type": "CSTR", "unit": "DemoTrain1"},
            {"id": "equip:CSTR-102A", "tag": "CSTR-102A", "type": "CSTR", "unit": "DemoTrain1"},
            {"id": "equip:CSTR-102B", "tag": "CSTR-102B", "type": "CSTR", "unit": "DemoTrain1"},
            {"id": "equip:CSTR-104", "tag": "CSTR-104", "type": "CSTR", "unit": "DemoTrain1"},
            {"id": "equip:COLUMN-1", "tag": "COLUMN-1", "type": "DistillationColumn", "unit": "DemoTrain1"},
        ]

        print("Seeding nodes...")
        for node in nodes:
            label = node["type"]
            # We add BOTH the specific label (CSTR, DistillationColumn, Line) and the generic 'Equipment' and 'Entity' labels
            query = f"""
            MERGE (e:Entity {{id: $id}})
            SET e :Equipment, e :{label},
                e.surface_form = $tag,
                e.unit = $unit,
                e.type = $type
            """
            session.run(query, id=node["id"], tag=node["tag"], unit=node["unit"], type=node["type"])

        # 2. Seed CONNECTED_TO process flow edges
        connected_to = [
            ("FEED", "CSTR-101"),
            ("CSTR-101", "CSTR-102A"),
            ("CSTR-101", "CSTR-102B"),
            ("CSTR-102A", "CSTR-104"),
            ("CSTR-102B", "CSTR-104"),
        ]
        print("Seeding CONNECTED_TO edges...")
        for src, dst in connected_to:
            query = """
            MATCH (a:Equipment {surface_form: $src})
            MATCH (b:Equipment {surface_form: $dst})
            MERGE (a)-[r:CONNECTED_TO]->(b)
            SET r.source = "design"
            """
            session.run(query, src=src, dst=dst)

        # 3. Seed SHARES_HEADER utility edges
        shares_header = [
            ("CSTR-102A", "CSTR-102B"),
        ]
        print("Seeding SHARES_HEADER edges...")
        for a, b in shares_header:
            query = """
            MATCH (x:Equipment {surface_form: $a})
            MATCH (y:Equipment {surface_form: $b})
            MERGE (x)-[r1:SHARES_HEADER]->(y)
            MERGE (y)-[r2:SHARES_HEADER]->(x)
            """
            session.run(query, a=a, b=b)

        # 4. Seed FEEDS cross-unit process flow edge
        print("Seeding FEEDS edges...")
        query = """
        MATCH (a:Equipment {surface_form: "CSTR-104"})
        MATCH (b:Equipment {surface_form: "COLUMN-1"})
        MERGE (a)-[r:FEEDS]->(b)
        SET r.source = "design"
        """
        session.run(query)

        # 5. Seed SOP/Procedure Nodes and GOVERNED_BY links
        sops = [
            {
                "id": "doc:SOP-COOLANT-LOSS",
                "surface_form": "SOP-COOLANT-LOSS",
                "filename": "SOP-COOLANT-LOSS.pdf",
                "name": "Coolant Loss Response - Parallel CSTR",
                "steps": [
                    "Check coolant header valve positions on CSTR-102A and CSTR-102B.",
                    "Verify temperature rise rates. If dT/dt exceeds 2.0 K/s, raise a critical alarm.",
                    "If coolant loss is detected on CSTR-102A, verify if sibling reactor CSTR-102B shares the utility header.",
                    "Increase cooling water bypass flow rates to maintain temperature control.",
                    "If temperature continues to rise above 355 K, prepare to shut down feed flow."
                ],
                "governs": ["CSTR-102A", "CSTR-102B"]
            },
            {
                "id": "doc:SOP-FLOODING-RESPONSE",
                "surface_form": "SOP-FLOODING-RESPONSE",
                "filename": "SOP-FLOODING-RESPONSE.pdf",
                "name": "Distillation Column Flooding Response",
                "steps": [
                    "Monitor column flooding index and pressure drop across COLUMN-1 trays.",
                    "If flooding index exceeds 1.20, check reboiler duty (COLUMN-1.REBOILER.Duty) and reflux flow.",
                    "Verify upstream CSTR-104 outlet temperature and conversion. A thermal runaway in the CSTR train will increase unreacted feed concentration to COLUMN-1, triggering reboiler overload.",
                    "Reduce reboiler steam duty and boilup rate (V) to lower liquid entrainment.",
                    "Reduce CSTR train output to lower COLUMN-1 feed flow rate."
                ],
                "governs": ["COLUMN-1"]
            }
        ]

        print("Seeding SOPs...")
        for sop in sops:
            # Merge Procedure/Document node
            query_sop = """
            MERGE (p:Entity {id: $id})
            SET p :Procedure, p :Document,
                p.surface_form = $surface_form,
                p.filename = $filename,
                p.name = $name,
                p.steps = $steps
            """
            session.run(
                query_sop,
                id=sop["id"],
                surface_form=sop["surface_form"],
                filename=sop["filename"],
                name=sop["name"],
                steps=sop["steps"]
            )

            # Link governed equipment
            for target in sop["governs"]:
                query_link = """
                MATCH (e:Equipment {surface_form: $target})
                MATCH (p:Procedure {surface_form: $sop_sf})
                MERGE (e)-[g:GOVERNED_BY]->(p)
                SET g.revision = "Rev 2", g.date = "2026-01-01"
                MERGE (e)-[f:FIXED_BY]->(p)
                SET f.doc_id = p.id
                """
                session.run(query_link, target=target, sop_sf=sop["surface_form"])

    driver.close()
    print("Topology and SOP seeding complete.")


if __name__ == "__main__":
    main()

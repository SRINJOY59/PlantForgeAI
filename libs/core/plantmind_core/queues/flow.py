"""The pipeline topology, declared in one place. Services contain no
routing: task adapters look up "what comes next" here, and build_kg prints
this same declaration as the authoritative picture of the flow.

    upload -> ingest -> extraction_for[kind] -> after_extraction -> writer
"""

from enum import Enum

from plantmind_core.queues.routes import Routes


class DocKind(str, Enum):
    TABLE = "table"      # structured rows: work orders, inspection records
    PNID = "pnid"        # engineering drawings
    TEXT = "text"        # SOPs, incident reports, short prose
    MANUAL = "manual"    # long structured documents (OEM manuals, handbooks)
    EMAIL = "email"
    IMAGE = "image"      # standalone images: charts, nameplates, scans


class Flow:
    ingest = Routes.classify

    extraction_for = {
        DocKind.TABLE: Routes.parse_workorder,
        DocKind.PNID: Routes.extract_pnid,
        DocKind.TEXT: Routes.extract_text,
        DocKind.MANUAL: Routes.extract_manual,
        DocKind.EMAIL: Routes.extract_email,
        DocKind.IMAGE: Routes.extract_image,
    }

    after_extraction = Routes.resolve

    # after resolution the subgraph leaves celery: it goes onto the redis
    # write buffer, which the graph writer drains on its beat (Routes.flush)

    @classmethod
    def describe(cls) -> str:
        lines = [f"  upload -> {cls.ingest.queue}"]
        for kind, route in cls.extraction_for.items():
            lines.append(f"  {cls.ingest.queue} [{kind.value}] -> {route.queue}")
        lines.append(f"  extraction -> {cls.after_extraction.queue}")
        lines.append(f"  {cls.after_extraction.queue} -> write_buffer " f"-> neo4j (via {Routes.flush.queue})")
        return "\n".join(lines)

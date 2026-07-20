"""The Report Generator agent logic.

Combines tool-calling LLM reasoning to produce a report, then renders a PDF
and uploads it to MinIO for user download.
"""

import asyncio
import hashlib

from plantmind_core.storage import ObjectStore
from plantmind_core.telemetry import get_logger

from agents import tools
from agents.usecases.base import GraphAgent
from agents.usecases.report_generator import pdf_renderer, prompts

log = get_logger("agents.usecases.report_generator")


class ReportGeneratorAgent(GraphAgent):
    """Agent that runs graph tools to gather info, compiles a markdown report,
    and renders a beautiful PDF report with tables and failure charts.
    """
    system = prompts.SYSTEM

    def tools(self) -> list:
        r = self._reader
        return [
            tools.connected_equipment(r),
            tools.failure_history(r),
            tools.governing_clauses(r),
            tools.documents_mentioning(r),
            tools.fix_procedures(r),
            tools.work_orders(r),
            tools.sibling_history(r)
        ]

    async def generate_report(self, tag: str, graph_version: int = 0) -> dict:
        node_id = f"equip:{tag}"
        
        # 1. Fetch raw data from Neo4j for plotting
        # Run it off the main event loop to keep the loop free
        failure_data = await asyncio.to_thread(self._reader.equipment_failures, node_id)
        
        # 2. Ask the agent to reason and draft the report
        given = {tag}
        reasoned = await self.reason(prompts.task(tag), given)
        
        markdown_content = reasoned.answer
        if not reasoned.grounding.verified:
            markdown_content += (
                "\n\n[UNVERIFIED - the following tags were not found in the "
                "assessment evidence and may be incorrect: "
                + ", ".join(reasoned.grounding.ungrounded_tags) + "]"
            )
            
        # 3. Render the PDF with embedded Matplotlib chart and tables
        pdf_bytes = await asyncio.to_thread(
            pdf_renderer.render_report_pdf, markdown_content, failure_data
        )
        
        # 4. Upload to MinIO under raw/<doc_id>/<tag>_report.pdf
        content_hash = hashlib.sha256(pdf_bytes).hexdigest()
        doc_id = content_hash[:16]
        
        store = ObjectStore.from_settings()
        object_key = f"raw/{doc_id}/{tag}_report.pdf"
        
        # MinIO put is synchronous; run it off the main loop
        await asyncio.to_thread(
            store.put, object_key, pdf_bytes, "application/pdf"
        )
        
        log.info("report pdf generated and stored in MinIO",
                 tag=tag, doc_id=doc_id, path=object_key,
                 verified=reasoned.grounding.verified)
                 
        return {
            "tag": tag,
            "markdown": markdown_content,
            "doc_id": doc_id,
            "verified": reasoned.grounding.verified,
            "unverified_claims": reasoned.grounding.ungrounded_tags,
            "graph_version": graph_version
        }

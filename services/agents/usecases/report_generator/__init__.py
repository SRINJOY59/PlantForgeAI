"""Report Generator use-case package."""

# re-exported beside the agent because rendering is half of what this use-case
# does: the agent writes the markdown and the renderer turns it into the PDF
# that actually reaches a person. Callers reaching for one usually want both,
# and it is the package - not agent.py - that they import.
from plantmind_core.reporting import pdf_renderer

from agents.usecases.report_generator.agent import ReportGeneratorAgent

__all__ = ["ReportGeneratorAgent", "pdf_renderer"]

"""Reports generation route - proxied to the agents service.

Provides an API endpoint for users with engineering roles to generate
asset-specific PDF and Markdown reports.
"""

import httpx
from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from gateway.deps import get_agents_http, require_role
from gateway.ratelimit import rate_limit

router = APIRouter()
# Report generation requires engineer role and is metered (billed LLM + plot + PDF generation)
metered = [require_role("engineer"), Depends(rate_limit("reports"))]


class ReportRequest(BaseModel):
    tag: str


@router.post("/reports/generate", dependencies=metered)
async def generate_report(request: ReportRequest,
                          http: httpx.AsyncClient = Depends(get_agents_http)):
    resp = await http.post("/report/generate", json=request.model_dump())
    return Response(content=resp.content, status_code=resp.status_code,
                    media_type="application/json")

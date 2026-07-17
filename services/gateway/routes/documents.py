"""Upload into the pipeline, take corrections from engineers, and serve
original documents back for citation clicks."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from gateway.auth import current_user
from gateway.deps import get_service

router = APIRouter()

# octet-stream makes a browser download rather than render, which leaves the
# citation viewer blank. Text-ish sources are served as text/plain so they
# display inline; only genuinely unknown types fall back to a download.
MEDIA_TYPES = {
    "pdf": "application/pdf",
    "svg": "image/svg+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "html": "text/html",
    "json": "application/json",
    "md": "text/plain",
    "txt": "text/plain",
    "csv": "text/plain",
    "tsv": "text/plain",
    "eml": "text/plain",
    "log": "text/plain",
}


def media_type_for(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    return MEDIA_TYPES.get(ext, "application/octet-stream")


class CorrectionRequest(BaseModel):
    question: str
    answer: str
    correction: str = Field(min_length=1, max_length=4000)
    cited_docs: list[str] = Field(default_factory=list, max_length=20)


@router.post("/ingest")
async def ingest(file: UploadFile, svc=Depends(get_service)):
    data = await file.read()
    return svc.ingest(file.filename, data)


@router.post("/corrections")
def correct(request: CorrectionRequest, svc=Depends(get_service),
            user: dict = Depends(current_user)):
    """An engineer overturning something we said.

    The author comes off the verified token, never off the request body: a
    correction carries more weight in the graph than the document it
    contradicts, so who signed it has to be something we established rather
    than something the client asserted.
    """
    return svc.correct(question=request.question, answer=request.answer,
                       correction=request.correction,
                       author=user.get("email") or user.get("sub", "unknown"),
                       cited_docs=request.cited_docs)


@router.get("/documents/{doc_id}")
def document(doc_id: str, svc=Depends(get_service)):
    found = svc.document(doc_id)
    if not found:
        raise HTTPException(404, f"no document for {doc_id}")
    filename, data = found
    return Response(content=data, media_type=media_type_for(filename),
                    headers={"Content-Disposition":
                             f'inline; filename="{filename}"'})

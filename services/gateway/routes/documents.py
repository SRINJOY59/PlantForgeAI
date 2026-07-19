"""Upload into the pipeline, take corrections from engineers, and serve
original documents back for citation clicks."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from gateway.auth import current_user
from gateway.deps import get_service, require_role

router = APIRouter()

# The upload trust boundary. Anything past here gets parsed by pypdfium2, PIL,
# openpyxl and friends, so the gate belongs out here, before a byte reaches a
# parser. The allowlist mirrors what the classifier can actually route - keep
# it a superset of ingestion/classify.py so a valid file is never rejected here
# only to be understood downstream.
MAX_UPLOAD_BYTES = 25 * 1024 * 1024      # 25 MB
ALLOWED_EXTENSIONS = {
    "pdf", "md", "txt", "docx", "doc", "html",
    "csv", "tsv", "xlsx", "xls", "xlsm",
    "eml", "msg",
    "svg", "png", "jpg", "jpeg", "webp", "bmp", "tif", "tiff",
}


def _ext(filename: str) -> str:
    return filename.rsplit(".", 1)[-1].lower() if "." in (filename or "") else ""


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


@router.post("/ingest", dependencies=[require_role("engineer")])
async def ingest(file: UploadFile, svc=Depends(get_service)):
    ext = _ext(file.filename)
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            415, f"'{file.filename or 'file'}' is not an accepted type. "
                 f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}.")

    # read one byte past the limit and no further: an oversized upload is
    # rejected without ever holding more than the cap in memory
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            413, f"File exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit.")
    if not data:
        raise HTTPException(400, "Empty file.")

    # svc.ingest does a synchronous MinIO put (up to the 25 MB cap) plus a
    # Celery send; off the loop so a large upload doesn't stall other requests
    return await asyncio.to_thread(svc.ingest, file.filename, data)


@router.post("/corrections", dependencies=[require_role("engineer")])
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
    # nosniff on the sensitive endpoint explicitly, not just via middleware: a
    # document is the one response whose bytes we did not write, so the browser
    # must be told to honour the declared type and never sniff an upload served
    # as text/plain back into executable HTML
    return Response(content=data, media_type=media_type_for(filename),
                    headers={"Content-Disposition":
                             f'inline; filename="{filename}"',
                             "X-Content-Type-Options": "nosniff"})

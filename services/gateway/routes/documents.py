"""Upload into the pipeline, and serve original documents back for citation
clicks."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

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


@router.post("/ingest")
async def ingest(file: UploadFile, svc=Depends(get_service)):
    data = await file.read()
    return svc.ingest(file.filename, data)


@router.get("/documents/{doc_id}")
def document(doc_id: str, svc=Depends(get_service)):
    found = svc.document(doc_id)
    if not found:
        raise HTTPException(404, f"no document for {doc_id}")
    filename, data = found
    return Response(content=data, media_type=media_type_for(filename),
                    headers={"Content-Disposition":
                             f'inline; filename="{filename}"'})

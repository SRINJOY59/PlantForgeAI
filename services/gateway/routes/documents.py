"""Upload into the pipeline, and serve original documents back for citation
clicks."""

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import Response

from gateway.deps import get_service

router = APIRouter()


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
    return Response(content=data, media_type="application/octet-stream",
                    headers={"Content-Disposition":
                             f'inline; filename="{filename}"'})

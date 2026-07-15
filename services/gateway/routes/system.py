"""Operational endpoints: pipeline metrics and health."""

from fastapi import APIRouter, Depends

from gateway.deps import get_service

router = APIRouter()


@router.get("/metrics")
def metrics(svc=Depends(get_service)):
    return svc.metrics()


@router.get("/health")
def health():
    return {"status": "ok"}

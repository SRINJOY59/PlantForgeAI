"""Operational endpoints: pipeline metrics and health."""

from fastapi import APIRouter, Depends

from gateway.auth import current_user
from gateway.deps import get_service

router = APIRouter()


# this router is mounted without the blanket auth dependency so /health stays
# reachable for container healthchecks - /metrics protects itself
@router.get("/metrics")
def metrics(svc=Depends(get_service), user=Depends(current_user)):
    return svc.metrics()


@router.get("/health")
def health():
    return {"status": "ok"}

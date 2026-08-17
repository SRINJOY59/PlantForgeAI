"""Simulation routes package composing envelopes, proxy, ws, and idv endpoints.
"""

from fastapi import APIRouter

from gateway.routes.simulation.envelopes import router as envelopes_router
from gateway.routes.simulation.idv import router as idv_router
from gateway.routes.simulation.proxy import router as proxy_router
from gateway.routes.simulation.ws import router as ws_router

router = APIRouter()

router.include_router(envelopes_router)
router.include_router(proxy_router)
router.include_router(idv_router)
router.include_router(ws_router)

__all__ = ["router"]

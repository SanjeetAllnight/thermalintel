"""V1 API Router package."""

from fastapi import APIRouter

from .health import router as health_router
from .hotspots import router as hotspots_router
from .incidents import router as incidents_router
from .alerts import router as alerts_router
from .summary import router as summary_router
from .refresh import router as refresh_router
from .scheduler import router as scheduler_router

v1_router = APIRouter(prefix="/api/v1")

v1_router.include_router(health_router)
v1_router.include_router(hotspots_router)
v1_router.include_router(incidents_router)
v1_router.include_router(alerts_router)
v1_router.include_router(summary_router)
v1_router.include_router(refresh_router)
v1_router.include_router(scheduler_router)

__all__ = ["v1_router"]

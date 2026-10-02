"""V1 Refresh mutation router for ThermalIntel API."""

from typing import Optional
from fastapi import APIRouter, Depends, status

from services.api.database import seed_if_empty
from services.api.security import verify_admin_key, verify_refresh_rate_limit
from services.api.scheduler.orchestrator import get_refresh_orchestrator
from services.api.routers.errors import APIErrorResponse
from services.api.schemas import RefreshRequest, RefreshResponse

router = APIRouter(tags=["V1 - Orchestration"])


@router.post(
    "/refresh",
    response_model=RefreshResponse,
    dependencies=[Depends(verify_admin_key), Depends(verify_refresh_rate_limit)],
    summary="Trigger telemetry synchronization or sample catalog reindex",
    responses={
        401: {"model": APIErrorResponse, "description": "Missing required administrative API key"},
        403: {"model": APIErrorResponse, "description": "Invalid administrative API key"},
        409: {"model": APIErrorResponse, "description": "Concurrent refresh operation conflict"},
        429: {"model": APIErrorResponse, "description": "Rate limit exceeded"},
        500: {"model": APIErrorResponse, "description": "Server misconfiguration or internal error"},
    },
)
async def trigger_refresh(req: Optional[RefreshRequest] = None):
    """Trigger data synchronization from NASA FIRMS or reload sample dataset.
    
    Protected mutation endpoint:
    - Protected by ADMIN_API_KEY with constant-time verification (fails closed in production)
    - Protected against repeated abuse by in-process rate limiting
    - Protected against duplicate runs by single-flight execution sharing
    - Preserves ProviderRun audit telemetry and error containment
    """
    seed_if_empty()
    force = req.force_sample if req else False
    orchestrator = get_refresh_orchestrator()
    return await orchestrator.execute_refresh(
        force_sample=force,
        trigger="manual",
        wait_if_in_flight=True,
    )

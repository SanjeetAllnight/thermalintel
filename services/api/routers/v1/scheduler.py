"""V1 Scheduler diagnostics router for ThermalIntel API."""

from typing import Any, Dict
from fastapi import APIRouter

from services.api.scheduler.scheduler import get_scheduler

router = APIRouter(tags=["V1 - Orchestration"])


@router.get("/scheduler/status", summary="Diagnostic status of the background ingestion scheduler")
def get_scheduler_status() -> Dict[str, Any]:
    """Retrieve operational telemetry, status, and execution counters of the background scheduler."""
    scheduler = get_scheduler()
    return scheduler.get_status()

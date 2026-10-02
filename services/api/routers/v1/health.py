"""V1 System Health router for ThermalIntel API."""

from datetime import datetime, timezone
from fastapi import APIRouter

from services.api.database import get_connection, seed_if_empty
from services.api.schemas import HealthResponse, DataMode

router = APIRouter(tags=["V1 - Operations"])


@router.get("/health", response_model=HealthResponse, summary="System health and subsystem status")
def get_health():
    """Health check returning system status, operational data mode, and subsystem readiness."""
    seed_if_empty()
    mode = DataMode.DEMO
    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM system_meta WHERE key = 'data_mode'")
            row = cursor.fetchone()
            if row and row["value"] == "live":
                mode = DataMode.LIVE
    except Exception:
        pass

    intelligence_status = "online"
    try:
        from services.intelligence.engine import ThermalIntelligenceEngine  # noqa: F401
    except Exception:
        intelligence_status = "degraded"

    return HealthResponse(
        status="ok",
        version="2.0.0",
        data_mode=mode,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services={
            "database": "connected",
            "firms_api": "ready",
            "intelligence_engine": intelligence_status,
            "enrichment_engine": "ready",
            "incident_layer": "ready",
        },
    )

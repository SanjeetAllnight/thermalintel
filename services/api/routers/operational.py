"""Operational health, readiness, and metrics endpoints for ThermalIntel V2 API."""

import os
import time
import logging
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from fastapi import APIRouter, Header, Query, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field, ConfigDict

from services.api.database import get_connection

logger = logging.getLogger(__name__)

START_TIME = time.time()

router = APIRouter(tags=["Operational"])

# Hook for Phase 4 or observability layer to register an authoritative metrics collector
_external_metrics_collector: Optional[Callable[[], Dict[str, Any]]] = None


def register_metrics_collector(collector: Callable[[], Dict[str, Any]]) -> None:
    """Register an external observability metrics collector (e.g. from Phase 4)."""
    global _external_metrics_collector
    _external_metrics_collector = collector


# ── Response Models ───────────────────────────────────────────────────────────

class LivenessResponse(BaseModel):
    status: str = Field("ok", description="Liveness indicator")
    service: str = Field("ThermalIntel API", description="Service identifier")
    timestamp: str = Field(..., description="UTC ISO timestamp")
    uptime_seconds: float = Field(..., description="Process uptime in seconds")


class ReadinessChecks(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    database: str = Field(..., description="Database connectivity status: ok or error")
    schema_status: str = Field(..., alias="schema", description="Canonical schema presence: ok or error")


class ReadinessResponse(BaseModel):
    status: str = Field(..., description="Readiness indicator: ready or not_ready")
    timestamp: str = Field(..., description="UTC ISO timestamp")
    checks: ReadinessChecks = Field(..., description="Component readiness evaluations")


# ── Operational Endpoints ─────────────────────────────────────────────────────

@router.get("/healthz", response_model=LivenessResponse, summary="Cheap process liveness check")
def healthz():
    """Very cheap process liveness probe.
    
    Zero external dependencies, no provider network calls, no database mutations.
    """
    return LivenessResponse(
        status="ok",
        service="ThermalIntel API",
        timestamp=datetime.now(timezone.utc).isoformat(),
        uptime_seconds=round(time.time() - START_TIME, 2),
    )


@router.get("/readyz", response_model=ReadinessResponse, summary="Operational readiness check")
def readyz():
    """Readiness probe evaluating required operational dependencies.
    
    Checks database connectivity and schema readiness without triggering ingestion.
    Provider outages will not report the process as unready or crash it.
    """
    db_status = "ok"
    schema_status = "ok"

    try:
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
            
            # Check for baseline table
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='hotspots'")
            if not cursor.fetchone():
                schema_status = "uninitialized"
    except Exception as e:
        logger.warning("Readiness probe encountered database error: %s", e)
        db_status = "error"
        schema_status = "error"

    is_ready = (db_status == "ok" and schema_status == "ok")
    status_code = status.HTTP_200_OK if is_ready else status.HTTP_503_SERVICE_UNAVAILABLE

    payload = {
        "status": "ready" if is_ready else "not_ready",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": {
            "database": db_status,
            "schema": schema_status,
        },
    }
    return JSONResponse(status_code=status_code, content=payload)


@router.get("/metrics", summary="Operational and telemetry metrics")
def metrics(
    accept: Optional[str] = Header(None),
    format: Optional[str] = Query(None, description="Output format: 'json' or 'prometheus'"),
):
    """Expose service operational metrics.
    
    Integrates with repository observability collector if registered, or provides
    safe in-process metrics. Supports Prometheus exposition text format and JSON.
    """
    # 1. Collect core telemetry
    uptime = round(time.time() - START_TIME, 2)
    hotspots_count = 0
    incidents_count = 0
    alerts_count = 0

    try:
        with get_connection() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) as cnt FROM hotspots")
            row = c.fetchone()
            if row:
                hotspots_count = row["cnt"]
            
            # Check incidents if table exists
            c.execute("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table' AND name='incidents'")
            if c.fetchone()["cnt"] > 0:
                c.execute("SELECT COUNT(*) as cnt FROM incidents")
                incidents_count = c.fetchone()["cnt"]

            # Check alerts if table exists
            c.execute("SELECT COUNT(*) as cnt FROM sqlite_master WHERE type='table' AND name='alerts'")
            if c.fetchone()["cnt"] > 0:
                c.execute("SELECT COUNT(*) as cnt FROM alerts")
                alerts_count = c.fetchone()["cnt"]
    except Exception:
        pass

    # Check scheduler state if available
    from services.api.config import get_api_config
    scheduler_enabled = get_api_config().scheduler.enabled

    data: Dict[str, Any] = {
        "service": "thermalintel",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "uptime_seconds": uptime,
        "database_connected": True,
        "counts": {
            "hotspots": hotspots_count,
            "incidents": incidents_count,
            "alerts": alerts_count,
        },
        "scheduler": {
            "enabled": scheduler_enabled,
        },
    }

    # If an external Phase 4 observability collector is registered, incorporate it
    if _external_metrics_collector is not None:
        try:
            extra = _external_metrics_collector()
            if isinstance(extra, dict):
                data["observability"] = extra
        except Exception as e:
            logger.warning("External metrics collector raised error: %s", e)

    # 2. Format response based on header / query
    prefers_prometheus = (format == "prometheus") or (accept and "text/plain" in accept)

    if prefers_prometheus:
        lines = [
            "# HELP thermalintel_uptime_seconds Process uptime in seconds",
            "# TYPE thermalintel_uptime_seconds gauge",
            f"thermalintel_uptime_seconds {uptime}",
            "# HELP thermalintel_hotspots_total Count of persisted hotspots",
            "# TYPE thermalintel_hotspots_total gauge",
            f"thermalintel_hotspots_total {hotspots_count}",
            "# HELP thermalintel_incidents_total Count of persisted incidents",
            "# TYPE thermalintel_incidents_total gauge",
            f"thermalintel_incidents_total {incidents_count}",
            "# HELP thermalintel_alerts_total Count of persisted alerts",
            "# TYPE thermalintel_alerts_total gauge",
            f"thermalintel_alerts_total {alerts_count}",
            "# HELP thermalintel_scheduler_enabled Whether background scheduler is configured enabled",
            "# TYPE thermalintel_scheduler_enabled gauge",
            f"thermalintel_scheduler_enabled {1 if scheduler_enabled else 0}",
        ]
        return PlainTextResponse("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")

    return JSONResponse(content=data)

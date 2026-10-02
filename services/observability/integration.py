"""Integration helpers for wiring observability into FastAPI applications."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, FastAPI, Response, status
from fastapi.responses import JSONResponse, PlainTextResponse

from services.observability.health.service import get_health_service
from services.observability.logging.config import configure_logging, get_logger
from services.observability.logging.events import LogEvent
from services.observability.metrics.exporter import export_json, export_prometheus
from services.observability.middleware import ObservabilityMiddleware

logger = get_logger("thermalintel.observability")


async def prometheus_metrics_endpoint() -> Response:
    """Prometheus exposition format endpoint handler (text/plain; version=0.0.4)."""
    content = export_prometheus()
    return PlainTextResponse(content=content, media_type="text/plain; version=0.0.4")


async def json_metrics_endpoint() -> JSONResponse:
    """JSON snapshot metrics endpoint handler."""
    data = export_json()
    return JSONResponse(content=data)


async def readiness_probe_endpoint() -> JSONResponse:
    """Readiness probe endpoint handler."""
    service = get_health_service()
    report = await service.check_readiness()
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE if report.status == "unhealthy" else status.HTTP_200_OK
    return JSONResponse(content=report.to_dict(), status_code=http_status)


async def liveness_probe_endpoint() -> JSONResponse:
    """Liveness probe endpoint handler."""
    service = get_health_service()
    report = await service.check_liveness()
    http_status = status.HTTP_503_SERVICE_UNAVAILABLE if report.status == "unhealthy" else status.HTTP_200_OK
    return JSONResponse(content=report.to_dict(), status_code=http_status)


def create_observability_router() -> APIRouter:
    """Create an APIRouter providing /metrics and health probes.

    Can be included in FastAPI applications by the integration agent:
    app.include_router(create_observability_router())
    """
    router = APIRouter(tags=["Observability & Health"])
    router.add_api_route("/metrics", prometheus_metrics_endpoint, methods=["GET"], summary="Prometheus Operational Metrics")
    router.add_api_route("/metrics/json", json_metrics_endpoint, methods=["GET"], summary="JSON Metrics Snapshot")
    router.add_api_route("/health/ready", readiness_probe_endpoint, methods=["GET"], summary="Readiness Probe")
    router.add_api_route("/health/live", liveness_probe_endpoint, methods=["GET"], summary="Liveness Probe")
    return router


def setup_observability(
    app: Optional[FastAPI] = None,
    log_format: Optional[str] = None,
    log_level: Optional[str] = None,
    include_routes: bool = False,
) -> None:
    """Bootstrap structured logging, metrics, and middleware on a FastAPI application."""
    configure_logging(log_format=log_format, log_level=log_level)

    logger.log_event(
        LogEvent.APPLICATION_START,
        "ThermalIntel Observability subsystem initialized",
        severity="INFO",
    )

    if app is not None:
        # Add ASGI middleware for request tracking
        app.add_middleware(ObservabilityMiddleware)

        if include_routes:
            app.include_router(create_observability_router())

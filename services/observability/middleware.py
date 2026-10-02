"""ASGI / FastAPI Observability Middleware.

Provides automatic request correlation, duration timing, structured access logging,
and operational HTTP metric tracking with controlled cardinality.
"""

from __future__ import annotations

import re
import time
from typing import Callable
import uuid

from starlette.datastructures import Headers
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from services.observability.logging.config import get_logger
from services.observability.logging.context import correlation_context
from services.observability.logging.events import LogEvent
from services.observability.metrics.operational import get_operational_metrics

logger = get_logger("thermalintel.http")

# Path normalization regexes to prevent cardinality explosion in metric labels
PATH_PATTERNS = [
    # Alerts endpoints: /api/alerts/{id}/acknowledge, /api/alerts/{id}
    (re.compile(r"^/api/alerts/[^/]+/acknowledge/?$"), "/api/alerts/{id}/acknowledge"),
    (re.compile(r"^/api/alerts/[^/]+/?$"), "/api/alerts/{id}"),
    # Incidents endpoints: /api/incidents/{id}/timeline, /api/incidents/{id}/observations, /api/incidents/{id}
    (re.compile(r"^/api/incidents/[^/]+/timeline/?$"), "/api/incidents/{id}/timeline"),
    (re.compile(r"^/api/incidents/[^/]+/observations/?$"), "/api/incidents/{id}/observations"),
    (re.compile(r"^/api/incidents/[^/]+/?$"), "/api/incidents/{id}"),
    # Hotspots endpoints: /api/hotspots/{id}
    (re.compile(r"^/api/hotspots/[^/]+/?$"), "/api/hotspots/{id}"),
]


def normalize_path(path: str) -> str:
    """Normalize parameterized URL paths to prevent Prometheus cardinality explosion."""
    for pattern, replacement in PATH_PATTERNS:
        if pattern.match(path):
            return replacement
    # Collapse trailing slash
    clean = path.rstrip("/")
    return clean if clean else "/"


class ObservabilityMiddleware(BaseHTTPMiddleware):
    """Starlette middleware providing request correlation, logging, and metrics."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Prefer request ID already set by RequestCorrelationMiddleware (req- prefix).
        request_id = (
            getattr(request.state, "request_id", None)
            or request.headers.get("x-request-id")
            or request.headers.get("x-correlation-id")
            or f"req_{uuid.uuid4().hex[:12]}"
        )
        correlation_id = request.headers.get("x-correlation-id") or request_id

        # Normalize endpoint for bounded metrics cardinality
        raw_path = request.url.path
        endpoint = normalize_path(raw_path)
        method = request.method

        metrics = get_operational_metrics()
        metrics.http_active_requests.inc(method=method)

        start_time = time.perf_counter()

        with correlation_context(request_id=request_id, correlation_id=correlation_id):
            logger.log_event(
                LogEvent.HTTP_REQUEST_STARTED,
                f"{method} {raw_path}",
                severity="DEBUG",
                request_id=request_id,
                details={"method": method, "endpoint": endpoint, "path": raw_path},
            )

            status_code = 500
            error_type = None

            try:
                response = await call_next(request)
                status_code = response.status_code
                # Only set X-Request-ID if inner middleware hasn't already set it
                # (RequestCorrelationMiddleware owns this header when present)
                if "X-Request-ID" not in response.headers:
                    response.headers["X-Request-ID"] = request_id
                return response
            except Exception as exc:
                error_type = exc.__class__.__name__
                metrics.http_request_failures_total.inc(
                    method=method,
                    endpoint=endpoint,
                    error_type=error_type,
                )
                logger.log_event(
                    LogEvent.HTTP_REQUEST_FAILED,
                    f"{method} {raw_path} failed with {error_type}: {exc}",
                    severity="ERROR",
                    status="failure",
                    error_category=error_type,
                    error_message=str(exc),
                    request_id=request_id,
                    exc_info=True,
                )
                raise
            finally:
                duration_s = time.perf_counter() - start_time
                duration_ms = duration_s * 1000.0

                metrics.http_active_requests.dec(method=method)

                # Record HTTP request metrics
                status_str = str(status_code)
                status_class = f"{status_code // 100}xx"
                metrics.http_requests_total.inc(
                    method=method,
                    status_code=status_str,
                    endpoint=endpoint,
                )
                metrics.http_requests_by_status_class.inc(status_class=status_class)
                metrics.http_request_duration_seconds.observe(
                    duration_s,
                    method=method,
                    endpoint=endpoint,
                )

                if status_code >= 500 and not error_type:
                    metrics.http_request_failures_total.inc(
                        method=method,
                        endpoint=endpoint,
                        error_type="HTTP5xxError",
                    )

                severity = "ERROR" if status_code >= 500 else ("WARNING" if status_code >= 400 else "INFO")
                status = "failure" if status_code >= 500 else "success"

                logger.log_event(
                    LogEvent.HTTP_REQUEST_COMPLETED,
                    f"{method} {raw_path} -> {status_code} ({duration_ms:.1f}ms)",
                    severity=severity,
                    status=status,
                    duration_ms=round(duration_ms, 2),
                    request_id=request_id,
                    details={
                        "method": method,
                        "endpoint": endpoint,
                        "status_code": status_code,
                        "status_class": status_class,
                    },
                )

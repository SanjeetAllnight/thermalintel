"""Request and Correlation ID handling for ThermalIntel API."""

import re
import logging
from contextvars import ContextVar
from typing import Optional
from uuid import uuid4
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Request ID regex: alphanumeric, underscores, hyphens, 1 to 64 chars
REQUEST_ID_REGEX = re.compile(r"^[a-zA-Z0-9_\-]{1,64}$")

_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_current_request_id() -> Optional[str]:
    """Retrieve the current request/correlation ID from contextvars."""
    return _request_id_ctx.get()


def set_current_request_id(request_id: Optional[str]) -> None:
    """Explicitly assign the current request/correlation ID in contextvars."""
    _request_id_ctx.set(request_id)


def sanitize_or_generate_request_id(incoming: Optional[str] = None) -> str:
    """Validate incoming request ID or safely mint a fresh UUID-based identifier."""
    if incoming:
        cleaned = incoming.strip()
        if REQUEST_ID_REGEX.match(cleaned):
            return cleaned
    return f"req-{uuid4().hex}"


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Ensure every HTTP request has an audited request and correlation ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming_id = request.headers.get("X-Request-ID") or request.headers.get("X-Correlation-ID")
        req_id = sanitize_or_generate_request_id(incoming_id)
        
        # Store in context variable for downstream logger and error formatters
        token = _request_id_ctx.set(req_id)
        # Store in request state for direct access
        request.state.request_id = req_id

        try:
            response: Response = await call_next(request)
        except Exception:
            # Re-raise after ensuring context is reset in finally block
            raise
        finally:
            _request_id_ctx.reset(token)

        response.headers["X-Request-ID"] = req_id
        response.headers["X-Correlation-ID"] = req_id
        return response

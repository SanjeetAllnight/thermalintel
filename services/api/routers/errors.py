"""Structured API Errors and standard exception handling for ThermalIntel V2 API."""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from services.api.security import get_current_request_id, sanitize_or_generate_request_id

logger = logging.getLogger(__name__)


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── OpenAPI Error Models ──────────────────────────────────────────────────────

class ErrorDetail(BaseModel):
    """Structured machine-readable error details."""
    code: str = Field(..., description="Stable error code/category (e.g. not_found, invalid_request, rate_limited)")
    message: str = Field(..., description="Human-readable explanation of the error")
    request_id: Optional[str] = Field(None, description="Audited request/correlation identifier")
    details: Dict[str, Any] = Field(default_factory=dict, description="Supplementary non-sensitive error context")
    timestamp: str = Field(default_factory=_now_utc_iso, description="UTC timestamp of the error event")


class APIErrorResponse(BaseModel):
    """Standardized top-level API error envelope."""
    detail: str = Field(..., description="Backward-compatible detail string for standard HTTP clients")
    error: ErrorDetail = Field(..., description="Structured error payload")


# ── Custom Exceptions ─────────────────────────────────────────────────────────

class APIException(HTTPException):
    """Base exception for explicit structured API errors."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ):
        super().__init__(status_code=status_code, detail=message, headers=headers)
        self.code = code
        self.message = message
        self.details = details or {}


class InvalidRequestError(APIException):
    def __init__(self, message: str = "Invalid request parameters", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_request",
            message=message,
            details=details,
        )


class AuthenticationError(APIException):
    def __init__(self, message: str = "Authentication required or invalid credentials provided", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_401_UNAUTHORIZED,
            code="authentication_failure",
            message=message,
            details=details,
        )


class AuthorizationError(APIException):
    def __init__(self, message: str = "Insufficient permissions to perform this operation", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            code="authorization_failure",
            message=message,
            details=details,
        )


class NotFoundError(APIException):
    def __init__(self, message: str = "Requested resource not found", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message=message,
            details=details,
        )


class ConflictError(APIException):
    def __init__(self, message: str = "Resource conflict or concurrent operation in progress", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            code="conflict",
            message=message,
            details=details,
        )


class RateLimitedError(APIException):
    def __init__(self, message: str = "Too many requests. Please retry later.", retry_after: int = 60, details: Optional[Dict[str, Any]] = None):
        d = details or {}
        d["retry_after_seconds"] = retry_after
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            code="rate_limited",
            message=message,
            details=d,
            headers={"Retry-After": str(retry_after)},
        )


class ProviderUnavailableError(APIException):
    def __init__(self, message: str = "Upstream telemetry provider temporarily unavailable", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="provider_unavailable",
            message=message,
            details=details,
        )


class UpstreamTimeoutError(APIException):
    def __init__(self, message: str = "Upstream provider timed out while processing request", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            code="upstream_timeout",
            message=message,
            details=details,
        )


class InternalFailureError(APIException):
    def __init__(self, message: str = "An internal server error occurred", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_failure",
            message=message,
            details=details,
        )


# ── Response Formatting & Secret Sanitization ─────────────────────────────────

def _sanitize_message(message: str) -> str:
    """Strip potential leaked API keys or credentials from error strings."""
    if not isinstance(message, str):
        return str(message)
    # Simple defense in depth against accidental token echoing
    for sensitive_keyword in ["ADMIN_API_KEY", "FIRMS_MAP_KEY", "Bearer", "secret"]:
        if sensitive_keyword in message and "=" in message:
            return "Sensitive parameter error (details redacted for security)"
    return message


def _status_to_code(status_code: int) -> str:
    mapping = {
        400: "invalid_request",
        401: "authentication_failure",
        403: "authorization_failure",
        404: "not_found",
        409: "conflict",
        422: "invalid_request",
        429: "rate_limited",
        502: "provider_unavailable",
        503: "provider_unavailable",
        504: "upstream_timeout",
        500: "internal_failure",
    }
    return mapping.get(status_code, "internal_failure" if status_code >= 500 else "api_error")


def build_error_response(
    status_code: int,
    code: str,
    message: str,
    request_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """Construct structured JSONResponse with correlation headers."""
    clean_msg = _sanitize_message(message)
    req_id = request_id or get_current_request_id() or sanitize_or_generate_request_id()

    payload = {
        "detail": clean_msg,  # Preserved for backward compatibility
        "error": {
            "code": code,
            "message": clean_msg,
            "request_id": req_id,
            "details": details or {},
            "timestamp": _now_utc_iso(),
        },
    }

    resp_headers = dict(headers or {})
    resp_headers["X-Request-ID"] = req_id
    resp_headers["X-Correlation-ID"] = req_id

    return JSONResponse(status_code=status_code, content=payload, headers=resp_headers)


# ── Exception Handlers ────────────────────────────────────────────────────────

def register_error_handlers(app: FastAPI) -> None:
    """Register structured error handlers on the FastAPI application."""

    @app.exception_handler(APIException)
    async def handle_api_exception(request: Request, exc: APIException):
        req_id = getattr(request.state, "request_id", None) or get_current_request_id()
        return build_error_response(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            request_id=req_id,
            details=exc.details,
            headers=exc.headers,
        )

    @app.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException):
        req_id = getattr(request.state, "request_id", None) or get_current_request_id()
        code = _status_to_code(exc.status_code)
        return build_error_response(
            status_code=exc.status_code,
            code=code,
            message=str(exc.detail),
            request_id=req_id,
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError):
        req_id = getattr(request.state, "request_id", None) or get_current_request_id()
        # Sanitize error detail list
        sanitized_errors = []
        for err in exc.errors():
            sanitized_errors.append({
                "loc": [str(x) for x in err.get("loc", [])],
                "msg": err.get("msg", "Validation error"),
                "type": err.get("type", "value_error"),
            })
        return build_error_response(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            code="invalid_request",
            message="Invalid request parameters or payload",
            request_id=req_id,
            details={"validation_errors": sanitized_errors},
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception):
        req_id = getattr(request.state, "request_id", None) or get_current_request_id()
        logger.error(f"Unhandled exception on request {req_id}: {exc}", exc_info=True)
        return build_error_response(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            code="internal_failure",
            message="An internal server error occurred.",
            request_id=req_id,
        )

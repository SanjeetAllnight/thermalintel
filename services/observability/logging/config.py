"""Logging configuration and StructuredLogger wrapper for ThermalIntel.
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any, Mapping, Optional, Union

from services.observability.logging.events import LogEvent
from services.observability.logging.formatters import JSONFormatter, TextFormatter
from services.observability.logging.sanitizers import SecretSanitizingFilter


class StructuredLogger(logging.LoggerAdapter):
    """Adapter providing ergonomic methods for emitting structured events."""

    def __init__(self, logger: logging.Logger, extra: Optional[Mapping[str, Any]] = None) -> None:
        super().__init__(logger, dict(extra or {}))

    def log_event(
        self,
        event: Union[LogEvent, str],
        message: str,
        severity: str = "INFO",
        *,
        status: Optional[str] = None,
        duration_ms: Optional[float] = None,
        error_category: Optional[str] = None,
        error_message: Optional[str] = None,
        request_id: Optional[str] = None,
        provider_run_id: Optional[str] = None,
        incident_id: Optional[str] = None,
        alert_id: Optional[str] = None,
        observation_id: Optional[str] = None,
        operation_id: Optional[str] = None,
        exc_info: Any = None,
        **extra_fields: Any,
    ) -> None:
        """Emit a structured event with explicit metadata."""
        level = getattr(logging, severity.upper(), logging.INFO)
        extra = {
            "event": str(event),
            "status": status,
            "duration_ms": duration_ms,
            "error_category": error_category,
            "error_message": error_message,
            "request_id": request_id,
            "provider_run_id": provider_run_id,
            "incident_id": incident_id,
            "alert_id": alert_id,
            "observation_id": observation_id,
            "operation_id": operation_id,
            "extra_fields": extra_fields if extra_fields else None,
        }
        # Filter None values to keep record clean
        filtered_extra = {k: v for k, v in extra.items() if v is not None}
        self.logger.log(level, message, exc_info=exc_info, extra=filtered_extra)

    def event_info(self, event: Union[LogEvent, str], message: str, **kwargs: Any) -> None:
        self.log_event(event, message, severity="INFO", **kwargs)

    def event_warn(self, event: Union[LogEvent, str], message: str, **kwargs: Any) -> None:
        self.log_event(event, message, severity="WARNING", **kwargs)

    def event_error(self, event: Union[LogEvent, str], message: str, **kwargs: Any) -> None:
        self.log_event(event, message, severity="ERROR", **kwargs)

    def event_debug(self, event: Union[LogEvent, str], message: str, **kwargs: Any) -> None:
        self.log_event(event, message, severity="DEBUG", **kwargs)


def configure_logging(
    log_format: Optional[str] = None,
    log_level: Optional[str] = None,
    service_name: Optional[str] = None,
    stream: Optional[Any] = None,
) -> None:
    """Configure root and application logging with structured formatters and sanitizers.

    Default format is 'json' if running in production or docker, otherwise 'text'.
    Can be explicitly controlled via LOG_FORMAT=json|text.
    """
    fmt = log_format or os.getenv("LOG_FORMAT")
    if not fmt:
        # Default to json in production or container environments, text otherwise
        env = os.getenv("ENVIRONMENT", "").lower()
        is_container = os.path.exists("/.dockerenv") or os.getenv("CONTAINER") == "true"
        fmt = "json" if (env == "production" or is_container) else "text"

    lvl = log_level or os.getenv("LOG_LEVEL", "INFO").upper()
    numeric_level = getattr(logging, lvl, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Remove existing handlers to avoid duplicate log lines
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    # Create handler
    output_stream = stream or sys.stdout
    handler = logging.StreamHandler(output_stream)
    handler.setLevel(numeric_level)

    # Attach secret sanitizing filter
    handler.addFilter(SecretSanitizingFilter())

    # Attach appropriate formatter
    if fmt.lower() == "json":
        handler.setFormatter(JSONFormatter(service_name=service_name))
    else:
        handler.setFormatter(TextFormatter(service_name=service_name))

    root_logger.addHandler(handler)

    # Keep noisy third-party loggers at WARNING unless debug is explicitly set
    if numeric_level > logging.DEBUG:
        logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> StructuredLogger:
    """Retrieve a StructuredLogger wrapping the standard python logger."""
    return StructuredLogger(logging.getLogger(name))

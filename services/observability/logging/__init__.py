"""Structured logging package for ThermalIntel."""

from services.observability.logging.config import (
    StructuredLogger,
    configure_logging,
    get_logger,
)
from services.observability.logging.context import (
    clear_correlation_context,
    correlation_context,
    generate_id,
    get_correlation_context,
    get_correlation_value,
    get_current_alert_id,
    get_current_incident_id,
    get_current_provider_run_id,
    get_current_request_id,
    set_correlation_field,
)
from services.observability.logging.events import LogEvent
from services.observability.logging.formatters import JSONFormatter, TextFormatter
from services.observability.logging.sanitizers import (
    REDACTED_PLACEHOLDER,
    SecretSanitizingFilter,
    sanitize_data,
    sanitize_string,
)

__all__ = [
    "configure_logging",
    "get_logger",
    "StructuredLogger",
    "LogEvent",
    "JSONFormatter",
    "TextFormatter",
    "SecretSanitizingFilter",
    "sanitize_data",
    "sanitize_string",
    "REDACTED_PLACEHOLDER",
    "correlation_context",
    "get_correlation_context",
    "get_correlation_value",
    "get_current_request_id",
    "get_current_provider_run_id",
    "get_current_incident_id",
    "get_current_alert_id",
    "set_correlation_field",
    "clear_correlation_context",
    "generate_id",
]

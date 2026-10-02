"""Correlation context propagation using Python contextvars.

Tracks request_id, provider_run_id, incident_id, alert_id, and operation_id
across asynchronous tasks and call stacks without polluting domain models.
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any, Callable, Generator, Mapping, Optional
import uuid

# Global ContextVar holding active correlation attributes
_correlation_ctx: contextvars.ContextVar[dict[str, Any]] = contextvars.ContextVar(
    "thermalintel_correlation_ctx",
    default={},
)

STANDARD_CORRELATION_KEYS = {
    "request_id",
    "correlation_id",
    "provider_run_id",
    "incident_id",
    "alert_id",
    "observation_id",
    "operation_id",
}


def get_correlation_context() -> dict[str, Any]:
    """Return a copy of the current correlation context dictionary."""
    return dict(_correlation_ctx.get())


def get_correlation_value(key: str, default: Optional[Any] = None) -> Optional[Any]:
    """Retrieve a single correlation value from the active context."""
    return _correlation_ctx.get().get(key, default)


def get_current_request_id() -> Optional[str]:
    """Return the current request_id if set."""
    return get_correlation_value("request_id")


def get_current_provider_run_id() -> Optional[str]:
    """Return the current provider_run_id if set."""
    return get_correlation_value("provider_run_id")


def get_current_incident_id() -> Optional[str]:
    """Return the current incident_id if set."""
    return get_correlation_value("incident_id")


def get_current_alert_id() -> Optional[str]:
    """Return the current alert_id if set."""
    return get_correlation_value("alert_id")


def generate_id(prefix: str = "") -> str:
    """Generate a random short UUID identifier, optionally prefixed."""
    token = uuid.uuid4().hex[:16]
    return f"{prefix}{token}" if prefix else token


@contextmanager
def correlation_context(
    *,
    request_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    provider_run_id: Optional[str] = None,
    incident_id: Optional[str] = None,
    alert_id: Optional[str] = None,
    observation_id: Optional[str] = None,
    operation_id: Optional[str] = None,
    **custom_fields: Any,
) -> Generator[dict[str, Any], None, None]:
    """Context manager to push correlation fields into contextvars for the duration of a block.

    Restores previous context upon exit.
    """
    current = dict(_correlation_ctx.get())

    # Build new context overlay, filtering out None values
    updates: dict[str, Any] = {}
    if request_id is not None:
        updates["request_id"] = request_id
    if correlation_id is not None:
        updates["correlation_id"] = correlation_id
    elif request_id is not None and "correlation_id" not in current:
        # Request ID can serve as default correlation ID if none specified
        updates["correlation_id"] = request_id

    if provider_run_id is not None:
        updates["provider_run_id"] = provider_run_id
    if incident_id is not None:
        updates["incident_id"] = incident_id
    if alert_id is not None:
        updates["alert_id"] = alert_id
    if observation_id is not None:
        updates["observation_id"] = observation_id
    if operation_id is not None:
        updates["operation_id"] = operation_id

    for k, v in custom_fields.items():
        if v is not None:
            updates[k] = v

    new_ctx = {**current, **updates}
    token = _correlation_ctx.set(new_ctx)
    try:
        yield new_ctx
    finally:
        _correlation_ctx.reset(token)


def set_correlation_field(key: str, value: Any) -> None:
    """Set a field in the current context (persists until scope exit or reset)."""
    current = dict(_correlation_ctx.get())
    current[key] = value
    _correlation_ctx.set(current)


def clear_correlation_context() -> None:
    """Clear all correlation context for the current task."""
    _correlation_ctx.set({})

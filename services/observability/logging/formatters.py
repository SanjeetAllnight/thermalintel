"""Structured log formatters for machine-readable JSON and local dev output.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
import traceback
from typing import Any, Optional

from services.observability.logging.context import get_correlation_context
from services.observability.logging.sanitizers import sanitize_data, sanitize_string


def get_iso_utc_timestamp() -> str:
    """Return the current UTC time in ISO-8601 format with explicit Z suffix."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class JSONFormatter(logging.Formatter):
    """Machine-readable JSON formatter conforming to the ThermalIntel V2 observability spec."""

    def __init__(
        self,
        service_name: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.service_name = service_name or os.getenv("SERVICE_NAME", "thermalintel-backend")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")

    def format(self, record: logging.LogRecord) -> str:
        # Pull correlation context from contextvars
        context = get_correlation_context()

        # Event name: prefer explicitly passed event, or record.event, or fallback
        event_name = getattr(record, "event", None)
        if not event_name:
            if hasattr(record, "msg") and isinstance(record.msg, str) and "_" in record.msg and " " not in record.msg:
                # e.g. logger.info("application_ready")
                event_name = record.msg
            else:
                event_name = "log_entry"

        # Timestamp in UTC ISO-8601
        dt = datetime.fromtimestamp(record.created, timezone.utc)
        iso_timestamp = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

        # Sanitize message
        raw_msg = record.getMessage()
        clean_msg = sanitize_string(raw_msg)

        # Assemble canonical structured record
        payload: dict[str, Any] = {
            "timestamp": iso_timestamp,
            "severity": record.levelname,
            "logger": record.name,
            "service": self.service_name,
            "environment": self.environment,
            "event": str(event_name),
            "message": clean_msg,
        }

        # Correlation fields (overlay record attributes over contextvars)
        for key in (
            "request_id",
            "correlation_id",
            "provider_run_id",
            "incident_id",
            "alert_id",
            "observation_id",
            "operation_id",
        ):
            val = getattr(record, key, None) or context.get(key)
            if val is not None:
                payload[key] = str(val)

        # Operational metrics fields if present
        for key in ("duration_ms", "status", "error_category", "error_message"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val

        # Handle exception information if present
        if record.exc_info:
            ex_type, ex_val, ex_tb = record.exc_info
            if "error_category" not in payload and ex_type is not None:
                payload["error_category"] = ex_type.__name__
            if "error_message" not in payload and ex_val is not None:
                payload["error_message"] = sanitize_string(str(ex_val))
            payload["exception"] = {
                "type": ex_type.__name__ if ex_type else "Exception",
                "message": sanitize_string(str(ex_val)),
                "stacktrace": sanitize_string("".join(traceback.format_exception(*record.exc_info))),
            }

        # Any extra dictionary supplied via extra={"extra_fields": {...}} or extra={"details": {...}}
        extra_fields = getattr(record, "extra_fields", None) or getattr(record, "details", None)
        if isinstance(extra_fields, dict):
            payload["details"] = sanitize_data(extra_fields)

        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-friendly text formatter for local development console output."""

    def __init__(
        self,
        service_name: Optional[str] = None,
        environment: Optional[str] = None,
    ) -> None:
        super().__init__()
        self.service_name = service_name or os.getenv("SERVICE_NAME", "thermalintel-backend")
        self.environment = environment or os.getenv("ENVIRONMENT", "development")

    def format(self, record: logging.LogRecord) -> str:
        dt = datetime.fromtimestamp(record.created, timezone.utc)
        iso_timestamp = dt.strftime("%Y-%m-%d %H:%M:%S")

        context = get_correlation_context()
        event_name = getattr(record, "event", None) or "event"
        msg = sanitize_string(record.getMessage())

        # Collect relevant correlation badges
        badges = []
        req_id = getattr(record, "request_id", None) or context.get("request_id")
        if req_id:
            badges.append(f"req={req_id[:8]}")
        run_id = getattr(record, "provider_run_id", None) or context.get("provider_run_id")
        if run_id:
            badges.append(f"run={run_id}")
        inc_id = getattr(record, "incident_id", None) or context.get("incident_id")
        if inc_id:
            badges.append(f"inc={inc_id}")

        badge_str = f" [{','.join(badges)}]" if badges else ""
        duration = getattr(record, "duration_ms", None)
        dur_str = f" ({duration:.1f}ms)" if duration is not None else ""

        line = f"[{iso_timestamp}] {record.levelname:<7} [{record.name}] {event_name}: {msg}{dur_str}{badge_str}"

        if record.exc_info:
            line += "\n" + sanitize_string("".join(traceback.format_exception(*record.exc_info)))

        return line

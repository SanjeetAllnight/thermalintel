"""Tests for correlation context propagation."""

import json
import logging

from services.observability.logging.context import (
    clear_correlation_context,
    correlation_context,
    get_correlation_context,
    get_current_alert_id,
    get_current_incident_id,
    get_current_provider_run_id,
    get_current_request_id,
)
from services.observability.logging.formatters import JSONFormatter


def test_correlation_context_scope():
    clear_correlation_context()
    assert get_current_request_id() is None

    with correlation_context(request_id="req_123", provider_run_id="run_456"):
        assert get_current_request_id() == "req_123"
        assert get_current_provider_run_id() == "run_456"
        assert get_correlation_context()["correlation_id"] == "req_123"

        # Nested scope
        with correlation_context(incident_id="INC-001", alert_id="ALT-002"):
            assert get_current_request_id() == "req_123"
            assert get_current_incident_id() == "INC-001"
            assert get_current_alert_id() == "ALT-002"

        # Restored after inner scope
        assert get_current_incident_id() is None
        assert get_current_request_id() == "req_123"

    # Restored after outer scope
    assert get_current_request_id() is None


def test_json_formatter_captures_active_correlation():
    formatter = JSONFormatter()

    with correlation_context(request_id="req_abc999", incident_id="INC-2026-X"):
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="Incident triage initiated",
            args=(),
            exc_info=None,
        )
        record.event = "incident_triage"
        output = formatter.format(record)
        data = json.loads(output)

        assert data["request_id"] == "req_abc999"
        assert data["incident_id"] == "INC-2026-X"

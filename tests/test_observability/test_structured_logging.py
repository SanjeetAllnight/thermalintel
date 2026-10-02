"""Tests for structured logging and JSON formatting."""

import json
import logging
from unittest.mock import MagicMock

from services.observability.logging.config import StructuredLogger, configure_logging, get_logger
from services.observability.logging.context import correlation_context
from services.observability.logging.events import LogEvent
from services.observability.logging.formatters import JSONFormatter, TextFormatter


def test_json_formatter_standard_fields():
    formatter = JSONFormatter(service_name="test-service", environment="test-env")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Sample log message",
        args=(),
        exc_info=None,
    )
    record.event = LogEvent.APPLICATION_START
    output = formatter.format(record)
    data = json.loads(output)

    assert data["service"] == "test-service"
    assert data["environment"] == "test-env"
    assert data["logger"] == "test.logger"
    assert data["severity"] == "INFO"
    assert data["event"] == "application_start"
    assert data["message"] == "Sample log message"
    assert "timestamp" in data
    assert data["timestamp"].endswith("Z")


def test_json_formatter_with_operational_fields():
    formatter = JSONFormatter(service_name="test-service", environment="test-env")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=25,
        msg="Operation failed",
        args=(),
        exc_info=None,
    )
    record.event = LogEvent.PROVIDER_RUN_FAILED
    record.duration_ms = 142.5
    record.status = "failure"
    record.error_category = "TimeoutError"
    record.error_message = "Remote provider timed out"

    output = formatter.format(record)
    data = json.loads(output)

    assert data["event"] == "provider_run_failed"
    assert data["duration_ms"] == 142.5
    assert data["status"] == "failure"
    assert data["error_category"] == "TimeoutError"
    assert data["error_message"] == "Remote provider timed out"


def test_structured_logger_log_event():
    mock_logger = MagicMock(spec=logging.Logger)
    s_logger = StructuredLogger(mock_logger)

    s_logger.log_event(
        LogEvent.INCIDENT_CREATED,
        "New high-risk incident created",
        severity="WARNING",
        incident_id="INC-20261002-0001",
        status="success",
        risk_score=94.5,
    )

    mock_logger.log.assert_called_once()
    args, kwargs = mock_logger.log.call_args
    assert args[0] == logging.WARNING
    assert args[1] == "New high-risk incident created"
    assert kwargs["extra"]["event"] == "incident_created"
    assert kwargs["extra"]["incident_id"] == "INC-20261002-0001"
    assert kwargs["extra"]["status"] == "success"
    assert kwargs["extra"]["extra_fields"] == {"risk_score": 94.5}


def test_text_formatter_output():
    formatter = TextFormatter(service_name="test-service")
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message",
        args=(),
        exc_info=None,
    )
    record.event = "test_event"
    record.duration_ms = 45.2
    line = formatter.format(record)

    assert "[test.logger]" in line
    assert "test_event: Test message" in line
    assert "45.2ms" in line

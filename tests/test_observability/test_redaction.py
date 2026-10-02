"""Tests for secret redaction and log sanitization."""

import logging

from services.observability.logging.sanitizers import (
    REDACTED_PLACEHOLDER,
    SecretSanitizingFilter,
    sanitize_data,
    sanitize_string,
)


def test_sanitize_string_bearer_token():
    text = "Authorization: Bearer secret_token_value_12345678"
    clean = sanitize_string(text)
    assert REDACTED_PLACEHOLDER in clean
    assert "secret_token_value_12345678" not in clean


def test_sanitize_string_firms_hex_key():
    hex_key = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
    text = f"Fetching from https://firms.nasa.gov/api/area/csv/{hex_key}/VIIRS_SNPP_NRT"
    clean = sanitize_string(text)
    assert hex_key not in clean
    assert REDACTED_PLACEHOLDER in clean


def test_sanitize_string_key_value_params():
    text = "Connecting with map_key=secret_map_key_999 and admin_api_key=super_admin_pass"
    clean = sanitize_string(text)
    assert "secret_map_key_999" not in clean
    assert "super_admin_pass" not in clean
    assert f"map_key={REDACTED_PLACEHOLDER}" in clean
    assert f"admin_api_key={REDACTED_PLACEHOLDER}" in clean


def test_sanitize_data_dictionary():
    raw_dict = {
        "provider": "VIIRS",
        "api_key": "my-secret-api-key",
        "FIRMS_MAP_KEY": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
        "config": {
            "admin_api_key": "admin_token",
            "safe_param": 100,
        },
        "headers": ["Authorization: Bearer mytoken12345"],
    }

    clean = sanitize_data(raw_dict)

    assert clean["provider"] == "VIIRS"
    assert clean["api_key"] == REDACTED_PLACEHOLDER
    assert clean["FIRMS_MAP_KEY"] == REDACTED_PLACEHOLDER
    assert clean["config"]["admin_api_key"] == REDACTED_PLACEHOLDER
    assert clean["config"]["safe_param"] == 100
    assert "mytoken12345" not in clean["headers"][0]


def test_secret_sanitizing_filter():
    s_filter = SecretSanitizingFilter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="API Key is %s",
        args=("secret_xyz123456",),
        exc_info=None,
    )
    s_filter.filter(record)
    assert "secret_xyz123456" not in record.args[0]

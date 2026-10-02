"""Log sanitization and secret redaction for ThermalIntel.

Protects against accidental leakage of credentials, API keys, Bearer tokens,
passwords, and sensitive headers in log outputs.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Mapping, MutableMapping, Sequence

REDACTED_PLACEHOLDER = "[REDACTED]"

# Field name patterns that represent secrets
SENSITIVE_FIELD_REGEX = re.compile(
    r"(?i)(api[_-]?key|map[_-]?key|token|secret|password|passwd|auth|authorization|credential|cookie|private[_-]?key)",
)

# In-string value patterns (Bearer tokens, FIRMS 32-hex keys, key=val patterns)
IN_STRING_PATTERNS = [
    # Bearer tokens
    (re.compile(r"(?i)\b(bearer\s+)([A-Za-z0-9_\-\.]{8,})\b"), r"\1" + REDACTED_PLACEHOLDER),
    # Common auth/key query params or key-value pairs (e.g. MAP_KEY=xxx or api_key=xxx)
    (
        re.compile(
            r"(?i)\b(map_key|api_key|token|secret|password|admin_api_key)=([A-Za-z0-9_\-]{6,})\b"
        ),
        r"\1=" + REDACTED_PLACEHOLDER,
    ),
    # 32-character hex string (typical NASA FIRMS key format)
    (re.compile(r"\b[0-9a-fA-F]{32}\b"), REDACTED_PLACEHOLDER),
    # Prefixed secrets / tokens (e.g. secret_xyz123, token_abc456)
    (
        re.compile(r"(?i)\b(secret|token|api_key|password)[_-][A-Za-z0-9_\-]{4,}\b"),
        REDACTED_PLACEHOLDER,
    ),
]


def sanitize_string(text: str) -> str:
    """Sanitize sensitive patterns from an arbitrary string."""
    if not text:
        return text
    result = text
    for pattern, replacement in IN_STRING_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


def sanitize_data(data: Any, depth: int = 0, max_depth: int = 10) -> Any:
    """Recursively sanitize dictionaries, sequences, and strings."""
    if depth > max_depth:
        return str(data)

    if isinstance(data, str):
        return sanitize_string(data)

    if isinstance(data, Mapping):
        clean_dict: dict[str, Any] = {}
        for key, value in data.items():
            str_key = str(key)
            if SENSITIVE_FIELD_REGEX.search(str_key):
                clean_dict[str_key] = REDACTED_PLACEHOLDER
            else:
                clean_dict[str_key] = sanitize_data(value, depth=depth + 1, max_depth=max_depth)
        return clean_dict

    if isinstance(data, (list, tuple, set)):
        clean_seq = [sanitize_data(item, depth=depth + 1, max_depth=max_depth) for item in data]
        if isinstance(data, tuple):
            return tuple(clean_seq)
        if isinstance(data, set):
            return set(clean_seq)
        return clean_seq

    return data


class SecretSanitizingFilter(logging.Filter):
    """Logging filter that sanitizes log records before formatting/emission."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Sanitize main message
        if isinstance(record.msg, str):
            record.msg = sanitize_string(record.msg)
        elif record.msg is not None:
            record.msg = sanitize_data(record.msg)

        # Sanitize arguments if provided
        if record.args:
            if isinstance(record.args, dict):
                record.args = sanitize_data(record.args)
            elif isinstance(record.args, (list, tuple)):
                record.args = tuple(sanitize_data(arg) for arg in record.args)

        # Sanitize known extra attributes attached to record
        for attr in ("extra_fields", "details", "payload", "error_details"):
            if hasattr(record, attr):
                setattr(record, attr, sanitize_data(getattr(record, attr)))

        return True

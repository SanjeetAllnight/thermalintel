"""Security and hardening package for ThermalIntel API.

Preserves full backward compatibility with the previous security module interface:
- get_cors_origins
- get_admin_api_key
- verify_admin_key
- DEFAULT_DEV_ORIGINS
"""

from .cors import get_cors_origins
from .auth import get_admin_api_key, verify_admin_key, is_production_sensitive
from .rate_limit import InProcessRateLimiter, get_refresh_rate_limiter, verify_refresh_rate_limit
from .request_id import (
    RequestCorrelationMiddleware,
    get_current_request_id,
    set_current_request_id,
    sanitize_or_generate_request_id,
)
from services.api.config import DEFAULT_DEV_ORIGINS

__all__ = [
    "get_cors_origins",
    "get_admin_api_key",
    "verify_admin_key",
    "is_production_sensitive",
    "InProcessRateLimiter",
    "get_refresh_rate_limiter",
    "verify_refresh_rate_limit",
    "RequestCorrelationMiddleware",
    "get_current_request_id",
    "set_current_request_id",
    "sanitize_or_generate_request_id",
    "DEFAULT_DEV_ORIGINS",
]

"""Security configuration and lightweight guards for ThermalIntel API.

Provides:
- Configuration-driven, explicit CORS origin resolution (wildcards strictly disallowed).
- Lightweight API key verification for mutating endpoints (POST /api/refresh).
"""

import os
import hmac
import logging
from typing import List, Optional
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)

# Default development origins for Next.js / Vite local frontends
DEFAULT_DEV_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]


def get_cors_origins() -> List[str]:
    """Parse and validate CORS allowed origins from environment configuration.
    
    Loads a comma-separated list from CORS_ALLOWED_ORIGINS.
    Wildcard '*' is strictly filtered out and rejected to prevent insecure wildcard configurations.
    Defaults to standard local development origins if no explicit configuration is provided.
    
    Returns:
        List[str]: Clean list of authorized origin strings.
    """
    raw = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_DEV_ORIGINS)

    parsed: List[str] = []
    for item in raw.split(","):
        origin = item.strip()
        if not origin:
            continue
        if origin == "*":
            logger.warning(
                "Security warning: Wildcard '*' in CORS_ALLOWED_ORIGINS was ignored. "
                "Specify explicit origins for security."
            )
            continue
        if origin not in parsed:
            parsed.append(origin)

    return parsed if parsed else list(DEFAULT_DEV_ORIGINS)


def get_admin_api_key() -> Optional[str]:
    """Retrieve the configured administrative API key from environment."""
    key = os.getenv("ADMIN_API_KEY", "").strip()
    return key if key else None


def verify_admin_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """Validate administrative API key for mutating endpoints.
    
    Behavior:
    - If ADMIN_API_KEY is not configured (empty or unset), open access is maintained
      to preserve local development, demo workflows, and existing tests.
    - If ADMIN_API_KEY is configured in the environment, the caller must supply
      a matching 'X-API-Key' header.
    - Uses constant-time comparison to prevent timing side-channel attacks.
    - Secret values are never logged or exposed in HTTP responses.
    
    Raises:
        HTTPException(401): If ADMIN_API_KEY is configured but X-API-Key header is absent.
        HTTPException(403): If ADMIN_API_KEY is configured but X-API-Key header is invalid.
    """
    expected_key = get_admin_api_key()
    if not expected_key:
        # Local development / unconfigured mode: permissive to avoid breaking local workflows
        return

    if not x_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required 'X-API-Key' header for administrative operation.",
        )

    # Constant-time comparison
    if not hmac.compare_digest(x_api_key.encode("utf-8"), expected_key.encode("utf-8")):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid 'X-API-Key' provided.",
        )

"""Authentication and authorization guards for ThermalIntel API."""

import os
import hmac
import logging
from typing import Optional
from fastapi import Header, HTTPException, status

logger = logging.getLogger(__name__)


def get_admin_api_key() -> Optional[str]:
    """Retrieve the configured administrative API key from environment."""
    key = os.getenv("ADMIN_API_KEY", "").strip()
    return key if key else None


def is_production_sensitive() -> bool:
    """Check if the service is running in a production or fail-closed configuration."""
    env = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).strip().lower()
    fail_closed = os.getenv("FAIL_CLOSED_ON_MISSING_KEY", "").strip().lower() in ("true", "1", "yes")
    return env in ("production", "prod") or fail_closed


def verify_admin_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> None:
    """Validate administrative API key for mutating endpoints.
    
    Behavior:
    - If in a production-sensitive configuration and ADMIN_API_KEY is missing,
      fail closed with a 500 error to prevent unauthenticated administrative operations.
    - If ADMIN_API_KEY is not configured and not in production, open access is maintained
      to preserve local development, demo workflows, and baseline tests.
    - If ADMIN_API_KEY is configured in the environment, the caller must supply
      a matching 'X-API-Key' header.
    - Uses constant-time comparison to prevent timing side-channel attacks.
    - Secret values are never logged or exposed in HTTP responses.
    
    Raises:
        HTTPException(500): If running in production but ADMIN_API_KEY is unconfigured (fail closed).
        HTTPException(401): If ADMIN_API_KEY is configured but X-API-Key header is absent.
        HTTPException(403): If ADMIN_API_KEY is configured but X-API-Key header is invalid.
    """
    expected_key = get_admin_api_key()

    if not expected_key:
        if is_production_sensitive():
            logger.error("Security violation: ADMIN_API_KEY is unconfigured in production environment.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Administrative key configuration error: ADMIN_API_KEY must be set in production.",
            )
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

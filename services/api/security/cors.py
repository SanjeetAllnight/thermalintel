"""CORS origins resolution and validation."""

import os
import logging
from typing import List
from services.api.config import get_api_config, DEFAULT_DEV_ORIGINS

logger = logging.getLogger(__name__)


def get_cors_origins() -> List[str]:
    """Parse and validate CORS allowed origins from environment configuration.
    
    Loads a comma-separated list from CORS_ALLOWED_ORIGINS.
    Wildcard '*' is strictly filtered out and rejected to prevent insecure configurations.
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

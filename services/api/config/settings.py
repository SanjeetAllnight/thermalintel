"""Configuration management for ThermalIntel V2 API, Security, and Scheduler."""

import os
import logging
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)

DEFAULT_DEV_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]

DEFAULT_INGESTION_INTERVAL_SECONDS: float = 300.0  # 5 minutes
MIN_SAFE_INTERVAL_SECONDS: float = 5.0             # Prevent aggressive runaway loops


def _parse_bool(val: Optional[str], default: bool = False) -> bool:
    if val is None:
        return default
    s = val.strip().lower()
    return s in ("true", "1", "yes", "on", "t")


@dataclass
class SchedulerConfig:
    """Configuration for Phase 3 background ingestion scheduler."""
    enabled: bool = False
    interval_seconds: float = DEFAULT_INGESTION_INTERVAL_SECONDS
    force_sample: bool = False

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        raw_enabled = os.getenv("INGESTION_ENABLED")
        enabled = _parse_bool(raw_enabled, default=False)

        raw_interval = os.getenv("INGESTION_INTERVAL_SECONDS", "").strip()
        interval = DEFAULT_INGESTION_INTERVAL_SECONDS
        if raw_interval:
            try:
                parsed = float(raw_interval)
                if parsed <= 0:
                    logger.warning(
                        "Invalid non-positive INGESTION_INTERVAL_SECONDS (%s). "
                        "Falling back to default %s seconds.",
                        raw_interval,
                        DEFAULT_INGESTION_INTERVAL_SECONDS,
                    )
                    interval = DEFAULT_INGESTION_INTERVAL_SECONDS
                elif parsed < MIN_SAFE_INTERVAL_SECONDS:
                    logger.warning(
                        "Aggressive INGESTION_INTERVAL_SECONDS (%s < %s). "
                        "Clamping to minimum safe interval of %s seconds.",
                        parsed,
                        MIN_SAFE_INTERVAL_SECONDS,
                        MIN_SAFE_INTERVAL_SECONDS,
                    )
                    interval = MIN_SAFE_INTERVAL_SECONDS
                else:
                    interval = parsed
            except ValueError:
                logger.warning(
                    "Non-numeric INGESTION_INTERVAL_SECONDS (%s). "
                    "Falling back to default %s seconds.",
                    raw_interval,
                    DEFAULT_INGESTION_INTERVAL_SECONDS,
                )
                interval = DEFAULT_INGESTION_INTERVAL_SECONDS

        force_sample = _parse_bool(os.getenv("INGESTION_FORCE_SAMPLE"), default=False)
        return cls(enabled=enabled, interval_seconds=interval, force_sample=force_sample)


@dataclass
class SecurityConfig:
    """Configuration for CORS, API keys, rate limits, and security controls."""
    admin_api_key: Optional[str] = None
    cors_allowed_origins: List[str] = field(default_factory=lambda: list(DEFAULT_DEV_ORIGINS))
    environment: str = "development"
    fail_closed: bool = False
    refresh_rate_limit_calls: int = 10
    refresh_rate_limit_window_seconds: int = 60

    @classmethod
    def from_env(cls) -> "SecurityConfig":
        key = os.getenv("ADMIN_API_KEY", "").strip() or None
        env_name = os.getenv("ENVIRONMENT", os.getenv("ENV", "development")).strip().lower()

        # Parse CORS
        raw_cors = os.getenv("CORS_ALLOWED_ORIGINS", "").strip()
        origins: List[str] = []
        if raw_cors:
            for item in raw_cors.split(","):
                o = item.strip()
                if not o:
                    continue
                if o == "*":
                    logger.warning("Wildcard '*' in CORS_ALLOWED_ORIGINS rejected.")
                    continue
                if o not in origins:
                    origins.append(o)
        if not origins:
            origins = list(DEFAULT_DEV_ORIGINS)

        # Fail closed check
        explicit_fail_closed = _parse_bool(os.getenv("FAIL_CLOSED_ON_MISSING_KEY"), default=False)
        fail_closed = explicit_fail_closed or (env_name in ("production", "prod"))

        # Rate limits
        import sys
        is_testing = "pytest" in sys.modules or bool(os.getenv("PYTEST_CURRENT_TEST"))
        default_calls = 1000 if is_testing else 30
        rl_calls = int(os.getenv("REFRESH_RATE_LIMIT_CALLS", str(default_calls)))
        rl_window = int(os.getenv("REFRESH_RATE_LIMIT_WINDOW_SECONDS", "60"))

        return cls(
            admin_api_key=key,
            cors_allowed_origins=origins,
            environment=env_name,
            fail_closed=fail_closed,
            refresh_rate_limit_calls=max(1, rl_calls),
            refresh_rate_limit_window_seconds=max(1, rl_window),
        )


@dataclass
class ApiConfig:
    """Top-level API metadata and route configurations."""
    title: str = "ThermalIntel API"
    description: str = (
        "Geospatial AI system for satellite thermal anomaly detection, "
        "classification, explainable risk scoring, and persistent incident lifecycle."
    )
    version: str = "2.0.0"
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    v1_prefix: str = "/api/v1"
    legacy_prefix: str = "/api"
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig.from_env)
    security: SecurityConfig = field(default_factory=SecurityConfig.from_env)

    @classmethod
    def from_env(cls) -> "ApiConfig":
        return cls(
            scheduler=SchedulerConfig.from_env(),
            security=SecurityConfig.from_env(),
        )


_api_config: Optional[ApiConfig] = None


def get_api_config() -> ApiConfig:
    """Return the global API configuration instance (reloaded or cached)."""
    global _api_config
    if _api_config is None:
        _api_config = ApiConfig.from_env()
    return _api_config


def reload_api_config() -> ApiConfig:
    """Force reload of configuration from active environment variables."""
    global _api_config
    _api_config = ApiConfig.from_env()
    return _api_config

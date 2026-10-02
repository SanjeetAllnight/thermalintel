"""Health and readiness checks for ThermalIntel subsystems."""

from __future__ import annotations

import os
import sqlite3
import time
from typing import Any, Optional


class HealthCheckResult:
    """Outcome of a single subsystem health check."""

    def __init__(
        self,
        name: str,
        status: str,  # "healthy", "degraded", "unhealthy"
        latency_ms: float,
        details: Optional[dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        self.name = name
        self.status = status
        self.latency_ms = round(latency_ms, 2)
        self.details = details or {}
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "status": self.status,
            "latency_ms": self.latency_ms,
            "details": self.details,
        }
        if self.error:
            res["error"] = self.error
        return res


class DatabaseHealthCheck:
    """Verifies SQLite database connectivity, schema readiness, and integrity."""

    name = "database"

    def __init__(self, db_path: Optional[str] = None) -> None:
        self.db_path = db_path or os.getenv("DATABASE_PATH", "thermalintel.db")

    async def check(self) -> HealthCheckResult:
        start = time.perf_counter()
        if not os.path.exists(self.db_path):
            latency = (time.perf_counter() - start) * 1000.0
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                latency_ms=latency,
                error=f"Database file does not exist at {self.db_path}",
            )

        try:
            conn = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5.0)
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()

            # Check for core table existence
            cursor.execute(
                "SELECT count(*) FROM sqlite_master WHERE type='table' AND name IN ('hotspots', 'incidents', 'alerts_v2')"
            )
            table_count = cursor.fetchone()[0]
            conn.close()

            latency = (time.perf_counter() - start) * 1000.0
            if table_count >= 1:
                return HealthCheckResult(
                    name=self.name,
                    status="healthy",
                    latency_ms=latency,
                    details={"path": self.db_path, "tables_detected": table_count},
                )
            else:
                return HealthCheckResult(
                    name=self.name,
                    status="degraded",
                    latency_ms=latency,
                    details={"path": self.db_path, "tables_detected": table_count},
                    error="Database file exists but tables appear uninitialized",
                )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000.0
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                latency_ms=latency,
                error=str(exc),
            )


class StorageHealthCheck:
    """Verifies that cache directory and storage volume are writable and accessible."""

    name = "storage"

    def __init__(self, cache_dir: Optional[str] = None) -> None:
        self.cache_dir = cache_dir or os.getenv("CACHE_DIR", "data/cache")

    async def check(self) -> HealthCheckResult:
        start = time.perf_counter()
        try:
            os.makedirs(self.cache_dir, exist_ok=True)
            test_file = os.path.join(self.cache_dir, ".health_check_tmp")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)

            latency = (time.perf_counter() - start) * 1000.0
            return HealthCheckResult(
                name=self.name,
                status="healthy",
                latency_ms=latency,
                details={"cache_dir": self.cache_dir, "writable": True},
            )
        except Exception as exc:
            latency = (time.perf_counter() - start) * 1000.0
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                latency_ms=latency,
                error=str(exc),
            )


class ModeHealthCheck:
    """Verifies operational mode ('live' vs 'demo') configuration."""

    name = "data_mode"

    async def check(self) -> HealthCheckResult:
        start = time.perf_counter()
        mode = os.getenv("DATA_MODE", "demo").lower()
        has_firms_key = bool(os.getenv("FIRMS_MAP_KEY"))

        status = "healthy"
        error = None
        if mode == "live" and not has_firms_key:
            status = "degraded"
            error = "DATA_MODE is 'live' but FIRMS_MAP_KEY is empty; system will use fallback"

        latency = (time.perf_counter() - start) * 1000.0
        return HealthCheckResult(
            name=self.name,
            status=status,
            latency_ms=latency,
            details={
                "data_mode": mode,
                "firms_configured": has_firms_key,
                "environment": os.getenv("ENVIRONMENT", "development"),
            },
            error=error,
        )

"""Health and readiness aggregation service and CLI runner."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import sys
from typing import Any, Optional

from services.observability.health.checks import (
    DatabaseHealthCheck,
    HealthCheckResult,
    ModeHealthCheck,
    StorageHealthCheck,
)


class HealthReport:
    """Aggregated health report."""

    def __init__(
        self,
        status: str,  # "healthy", "degraded", "unhealthy"
        checks: dict[str, HealthCheckResult],
        version: str = "0.2.0",
        environment: Optional[str] = None,
    ) -> None:
        self.status = status
        self.timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        self.version = version
        self.environment = environment or os.getenv("ENVIRONMENT", "development")
        self.checks = checks

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "timestamp": self.timestamp,
            "version": self.version,
            "environment": self.environment,
            "checks": {name: res.to_dict() for name, res in self.checks.items()},
        }


class HealthService:
    """Service orchestrating liveness and readiness probe checks."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        cache_dir: Optional[str] = None,
    ) -> None:
        self.db_check = DatabaseHealthCheck(db_path=db_path)
        self.storage_check = StorageHealthCheck(cache_dir=cache_dir)
        self.mode_check = ModeHealthCheck()

    async def check_liveness(self) -> HealthReport:
        """Liveness probe: verifies process responsiveness."""
        # Process is alive if this runs
        mode_res = await self.mode_check.check()
        return HealthReport(
            status="healthy",
            checks={"process": HealthCheckResult("process", "healthy", 0.1), "mode": mode_res},
        )

    async def check_readiness(self) -> HealthReport:
        """Readiness probe: verifies dependencies (DB, filesystem) before serving traffic."""
        tasks = [
            self.db_check.check(),
            self.storage_check.check(),
            self.mode_check.check(),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        checks_map: dict[str, HealthCheckResult] = {}
        has_unhealthy = False
        has_degraded = False

        for res in results:
            if isinstance(res, Exception):
                has_unhealthy = True
                checks_map["internal_error"] = HealthCheckResult(
                    name="internal_error",
                    status="unhealthy",
                    latency_ms=0.0,
                    error=str(res),
                )
            elif isinstance(res, HealthCheckResult):
                checks_map[res.name] = res
                if res.status == "unhealthy":
                    has_unhealthy = True
                elif res.status == "degraded":
                    has_degraded = True

        overall_status = "unhealthy" if has_unhealthy else ("degraded" if has_degraded else "healthy")
        return HealthReport(status=overall_status, checks=checks_map)


_DEFAULT_HEALTH_SERVICE: Optional[HealthService] = None


def get_health_service() -> HealthService:
    global _DEFAULT_HEALTH_SERVICE
    if _DEFAULT_HEALTH_SERVICE is None:
        _DEFAULT_HEALTH_SERVICE = HealthService()
    return _DEFAULT_HEALTH_SERVICE


async def _cli_main() -> int:
    parser = argparse.ArgumentParser(description="ThermalIntel health & readiness probe runner.")
    parser.add_argument(
        "--type",
        choices=["readiness", "liveness"],
        default="readiness",
        help="Probe type to evaluate (default: readiness)",
    )
    args = parser.parse_args()

    service = get_health_service()
    if args.type == "liveness":
        report = await service.check_liveness()
    else:
        report = await service.check_readiness()

    output = report.to_dict()
    print(json.dumps(output, indent=2))

    # Exit code: 0 for healthy or degraded (still serving traffic), 1 for unhealthy
    return 1 if report.status == "unhealthy" else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_cli_main()))

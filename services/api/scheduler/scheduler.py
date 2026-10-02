"""Phase 3 Ingestion Scheduler for ThermalIntel V2.

Lightweight, robust, in-process background scheduler for automated telemetry
synchronization with:
- Strict environment-driven activation (disabled by default)
- Safe startup and shutdown lifecycles
- Duplicate loop prevention
- Canonical single-flight execution sharing with manual refresh
- Resilience against provider failures and unexpected exceptions
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from services.api.config import (
    SchedulerConfig,
    get_api_config,
    DEFAULT_INGESTION_INTERVAL_SECONDS,
    MIN_SAFE_INTERVAL_SECONDS,
)
from services.api.scheduler.orchestrator import RefreshOrchestrator, get_refresh_orchestrator

logger = logging.getLogger(__name__)


class IngestionScheduler:
    """In-process background loop triggering scheduled telemetry synchronization."""

    def __init__(
        self,
        config: Optional[SchedulerConfig] = None,
        orchestrator: Optional[RefreshOrchestrator] = None,
    ):
        self._config = config or get_api_config().scheduler
        self._orchestrator = orchestrator or get_refresh_orchestrator()
        self._task: Optional[asyncio.Task] = None
        self._stop_event: Optional[asyncio.Event] = None
        self._is_running: bool = False
        self._last_run_utc: Optional[str] = None
        self._last_status: Optional[str] = None
        self._last_error: Optional[str] = None
        self._run_count: int = 0
        self._success_count: int = 0
        self._failure_count: int = 0

    @property
    def config(self) -> SchedulerConfig:
        return self._config

    @property
    def is_running(self) -> bool:
        return self._is_running and self._task is not None and not self._task.done()

    @property
    def interval_seconds(self) -> float:
        return self._config.interval_seconds

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status snapshot of the background scheduler."""
        return {
            "enabled": self._config.enabled,
            "running": self.is_running,
            "interval_seconds": self.interval_seconds,
            "force_sample": self._config.force_sample,
            "last_run_utc": self._last_run_utc,
            "last_status": self._last_status,
            "last_error": self._last_error,
            "run_count": self._run_count,
            "success_count": self._success_count,
            "failure_count": self._failure_count,
        }

    async def start(self) -> bool:
        """Start the background scheduler task if enabled.
        
        Returns:
            True if started, False if disabled or already running.
        """
        if not self._config.enabled:
            logger.info("Ingestion scheduler is disabled (INGESTION_ENABLED=false). Skipping startup.")
            return False

        if self.is_running:
            logger.warning("Ingestion scheduler is already running. Duplicate startup ignored.")
            return False

        # Validate interval before launching
        if self._config.interval_seconds <= 0:
            logger.warning(
                "Invalid interval %s. Setting to default %s seconds.",
                self._config.interval_seconds,
                DEFAULT_INGESTION_INTERVAL_SECONDS,
            )
            self._config.interval_seconds = DEFAULT_INGESTION_INTERVAL_SECONDS

        logger.info(
            "Starting IngestionScheduler with interval=%.1fs (force_sample=%s)",
            self._config.interval_seconds,
            self._config.force_sample,
        )

        self._stop_event = asyncio.Event()
        self._is_running = True
        self._task = asyncio.create_task(self._scheduler_loop())
        return True

    async def stop(self, timeout: float = 5.0) -> None:
        """Gracefully stop the background scheduler task."""
        if not self.is_running or self._stop_event is None:
            self._is_running = False
            return

        logger.info("Stopping IngestionScheduler...")
        self._stop_event.set()
        self._is_running = False

        if self._task and not self._task.done():
            try:
                await asyncio.wait_for(self._task, timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("IngestionScheduler did not stop within %.1fs timeout. Cancelling task.", timeout)
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except Exception as e:
                logger.error("Error during IngestionScheduler shutdown: %s", e)

        self._task = None
        self._stop_event = None
        logger.info("IngestionScheduler stopped successfully.")

    async def _scheduler_loop(self) -> None:
        """Continuous background execution loop."""
        logger.info("IngestionScheduler background loop entered.")

        while self._stop_event and not self._stop_event.is_set():
            # Wait for the configured interval or stop signal
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
                # If stop event fired, exit loop immediately
                break
            except asyncio.TimeoutError:
                # Interval elapsed; trigger a run
                pass

            if self._stop_event and self._stop_event.is_set():
                break

            await self._execute_scheduled_run()

        logger.info("IngestionScheduler background loop exited cleanly.")

    async def _execute_scheduled_run(self) -> None:
        """Execute a single scheduled ingestion run with full exception containment."""
        self._run_count += 1
        self._last_run_utc = datetime.now(timezone.utc).isoformat()
        logger.info("IngestionScheduler triggering scheduled run #%d...", self._run_count)

        try:
            # Use canonical single-flight orchestrator
            response = await self._orchestrator.execute_refresh(
                force_sample=self._config.force_sample,
                trigger="scheduler",
                wait_if_in_flight=True,
            )
            self._last_status = response.status
            self._last_error = None
            self._success_count += 1
            logger.info(
                "IngestionScheduler run #%d completed: status=%s, ingested=%d",
                self._run_count,
                response.status,
                response.ingested_count,
            )
        except Exception as exc:
            self._failure_count += 1
            self._last_status = "error"
            self._last_error = str(exc)
            logger.error(
                "IngestionScheduler run #%d encountered error (scheduler remains active): %s",
                self._run_count,
                exc,
                exc_info=True,
            )


# Global scheduler singleton
_global_scheduler: Optional[IngestionScheduler] = None


def get_scheduler() -> IngestionScheduler:
    """Return the global IngestionScheduler instance."""
    global _global_scheduler
    if _global_scheduler is None:
        _global_scheduler = IngestionScheduler()
    return _global_scheduler

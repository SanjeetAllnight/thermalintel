"""Canonical Refresh Orchestration and Single-Flight Execution Engine.

Ensures that concurrent manual refresh requests and scheduled background refresh
runs share a single synchronized execution path without duplicate ingestion runs,
race conditions, or unhandled process crashes.
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from services.api.data.service import HotspotDataService
from services.api.schemas import RefreshResponse, DataMode
from services.api.routers.errors import (
    ConflictError,
    ProviderUnavailableError,
    InternalFailureError,
)

logger = logging.getLogger(__name__)


class RefreshOrchestrator:
    """Coordinates and serializes ingestion refresh runs across manual and scheduled callers."""

    def __init__(self, data_service: Optional[HotspotDataService] = None):
        self._data_service = data_service or HotspotDataService()
        self._lock = asyncio.Lock()
        self._current_run: Optional[asyncio.Future] = None
        self._last_run_timestamp: Optional[str] = None
        self._last_result: Optional[RefreshResponse] = None
        self._total_runs: int = 0
        self._total_failures: int = 0

    @property
    def is_running(self) -> bool:
        """Whether a refresh execution is actively in-flight."""
        return self._current_run is not None and not self._current_run.done()

    @property
    def stats(self) -> Dict[str, Any]:
        """Telemetry snapshot of orchestrator execution history."""
        return {
            "is_running": self.is_running,
            "last_run_timestamp": self._last_run_timestamp,
            "total_runs": self._total_runs,
            "total_failures": self._total_failures,
        }

    async def execute_refresh(
        self,
        force_sample: bool = False,
        trigger: str = "manual",
        wait_if_in_flight: bool = True,
    ) -> RefreshResponse:
        """Execute a canonical refresh run with single-flight deduplication.
        
        Args:
            force_sample: If True, forces reloading of deterministic demo sample.
            trigger: Identifier of caller ('manual', 'scheduler', 'test').
            wait_if_in_flight: If True, shares and waits for the active execution.
                              If False, raises ConflictError (HTTP 409).
        
        Returns:
            RefreshResponse from the single executed run.
        """
        async with self._lock:
            if self._current_run is not None and not self._current_run.done():
                logger.info(
                    "Refresh requested (trigger=%s) while an execution is already in-flight. Single-flight sharing.",
                    trigger,
                )
                if not wait_if_in_flight:
                    raise ConflictError(
                        message="A data synchronization run is already actively in progress.",
                        details={"trigger": trigger, "status": "in_progress"},
                    )
                in_flight = self._current_run
            else:
                loop = asyncio.get_running_loop()
                in_flight = loop.create_future()
                self._current_run = in_flight
                # Launch task
                asyncio.create_task(self._do_execute(in_flight, force_sample, trigger))

        # Await the shared future
        try:
            result = await in_flight
            return result
        except Exception as e:
            logger.error("Refresh execution failed for caller (trigger=%s): %s", trigger, e)
            raise

    async def _do_execute(
        self,
        future: asyncio.Future,
        force_sample: bool,
        trigger: str,
    ) -> None:
        """Worker task running the synchronous data_service.sync inside a threadpool worker."""
        start_time = time.time()
        self._total_runs += 1
        logger.info("Starting canonical refresh execution (trigger=%s, force_sample=%s)...", trigger, force_sample)

        try:
            # Execute in thread to avoid blocking FastAPI event loop
            response: RefreshResponse = await asyncio.to_thread(
                self._data_service.sync,
                force_sample=force_sample,
            )
            self._last_run_timestamp = datetime.now(timezone.utc).isoformat()
            self._last_result = response

            if not future.done():
                future.set_result(response)
            logger.info(
                "Completed canonical refresh execution (trigger=%s, status=%s, count=%d in %.3fs)",
                trigger,
                response.status,
                response.ingested_count,
                round(time.time() - start_time, 3),
            )
        except Exception as exc:
            self._total_failures += 1
            logger.error("Exception during refresh sync execution: %s", exc, exc_info=True)
            # Create a safe fallback response so the service never crashes
            fallback_response = RefreshResponse(
                status="fallback_sample",
                message=f"Orchestrated sync encountered error; fallback active: {exc}",
                ingested_count=0,
                data_mode=DataMode.DEMO,
                timestamp=datetime.now(timezone.utc).isoformat(),
                execution_time_seconds=round(time.time() - start_time, 3),
            )
            self._last_result = fallback_response
            if not future.done():
                future.set_result(fallback_response)
        finally:
            async with self._lock:
                if self._current_run is future:
                    self._current_run = None


# Singleton instance
_refresh_orchestrator: Optional[RefreshOrchestrator] = None


def get_refresh_orchestrator() -> RefreshOrchestrator:
    """Return the global RefreshOrchestrator singleton."""
    global _refresh_orchestrator
    if _refresh_orchestrator is None:
        _refresh_orchestrator = RefreshOrchestrator()
    return _refresh_orchestrator

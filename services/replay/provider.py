"""Scenario Provider implementation for ThermalIntel V2 Replay.

Acts as an interchangeable input source for the ThermalIntel data pipeline,
yielding satellite observations and simulating provider degradation/recovery
in virtual simulated time (as_of_utc).

Implements Requirement 6:
'The architecture should make it possible to run:
 LIVE PROVIDER or SCENARIO PROVIDER through the same processing pipeline.'
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional, Union, Dict, Any, TYPE_CHECKING

if TYPE_CHECKING:
    from scenarios.schema import Scenario, ScenarioObservation, ProviderControlEvent
from services.replay.clock import Clock, SimulatedClock
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.provider import ProviderRun
from services.api.schemas.v2.common import ProviderStatus, now_utc_iso
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.v2.converters import hotspot_from_v2

logger = logging.getLogger(__name__)


def scenario_obs_to_v2_observation(
    so: ScenarioObservation,
    ingestion_time_utc: Optional[str] = None
) -> Observation:
    """Convert a ScenarioObservation into a validated canonical V2 Observation."""
    return Observation(
        observation_id=so.observation_id,
        provider=so.provider,
        product=so.product,
        satellite=so.satellite,
        instrument=so.instrument,
        latitude=so.latitude,
        longitude=so.longitude,
        acquisition_time_utc=so.acquisition_time_utc,
        ingestion_time_utc=ingestion_time_utc or now_utc_iso(),
        brightness=so.brightness,
        bright_t31=so.bright_t31,
        frp=so.frp,
        scan=so.scan,
        track=so.track,
        daynight=so.daynight,
        detection_confidence=so.detection_confidence,
        source_attributes={
            **so.source_attributes,
            "scenario_label_type": so.label_type.value,
            "expected_source": so.expected_source,
            "nearest_place": so.nearest_place,
        },
        schema_version="2.0",
    )


class ScenarioProvider:
    """Data provider executing over declarative scenario definitions.
    
    Provides observations at or before virtual simulated time, and tracks
    controlled provider state transitions (degradation, failure, recovery).
    """

    def __init__(self, scenario: Scenario, clock: Optional[Clock] = None):
        self.scenario = scenario
        self.clock = clock or SimulatedClock(scenario.start_time_utc)
        self._consumed_obs_ids: set[str] = set()
        self._provider_status: ProviderStatus = ProviderStatus.SUCCESS
        self._last_error_type: Optional[str] = None
        self._last_error_message: Optional[str] = None
        self._provider_runs: List[ProviderRun] = []
        self._run_counter: int = 0

    @property
    def status(self) -> ProviderStatus:
        """Current operational status of this provider."""
        return self._provider_status

    @property
    def is_degraded(self) -> bool:
        """True if provider is degraded or failed."""
        return self._provider_status in (ProviderStatus.PARTIAL, ProviderStatus.FAILED)

    def evaluate_provider_status(self, as_of: Optional[datetime] = None) -> ProviderStatus:
        """Update provider health based on scheduled ProviderControlEvents up to as_of."""
        target_dt = as_of or self.clock.now_utc()
        target_iso = target_dt.isoformat()

        # Find the latest control event <= target_dt
        events = self.scenario.provider_events_up_to(target_dt)
        if events:
            latest = events[-1]
            status_map = {
                "success": ProviderStatus.SUCCESS,
                "degraded": ProviderStatus.PARTIAL,
                "failed": ProviderStatus.FAILED,
                "partial": ProviderStatus.PARTIAL,
            }
            new_status = status_map.get(latest.status.lower(), ProviderStatus.SUCCESS)
            if new_status != self._provider_status:
                logger.info(
                    "Provider %s transitioned from %s to %s at %s",
                    latest.provider,
                    self._provider_status,
                    new_status,
                    target_iso,
                )
            self._provider_status = new_status
            self._last_error_type = latest.error_type
            self._last_error_message = latest.error_message
        else:
            self._provider_status = ProviderStatus.SUCCESS
            self._last_error_type = None
            self._last_error_message = None

        return self._provider_status

    def fetch_observations(
        self,
        as_of: Optional[Union[datetime, str]] = None,
        consume: bool = True,
    ) -> List[Observation]:
        """Fetch observations available up to the given as_of timestamp.
        
        If consume=True, marks returned observations as consumed so subsequent
        calls only return newly arrived observations.
        """
        if as_of is None:
            target_dt = self.clock.now_utc()
        elif isinstance(as_of, str):
            target_dt = datetime.fromisoformat(as_of.replace("Z", "+00:00"))
            if target_dt.tzinfo is None:
                target_dt = target_dt.replace(tzinfo=timezone.utc)
        else:
            target_dt = as_of

        # Evaluate provider degradation state
        current_status = self.evaluate_provider_status(target_dt)
        target_iso = target_dt.isoformat()

        # Collect eligible observations
        eligible_obs = self.scenario.observations_up_to(target_iso)
        if consume:
            eligible_obs = [o for o in eligible_obs if o.observation_id not in self._consumed_obs_ids]
            for o in eligible_obs:
                self._consumed_obs_ids.add(o.observation_id)

        # Ingestion time represents physical DB write time (as_of is acquisition/simulated time)
        ingestion_time = now_utc_iso()
        results: List[Observation] = []

        if current_status == ProviderStatus.FAILED:
            # If provider failed, raw fetch returns empty or degraded cached copy
            logger.warning("Provider fetch failed at %s: %s", target_iso, self._last_error_message)
        else:
            for so in eligible_obs:
                obs_v2 = scenario_obs_to_v2_observation(so, ingestion_time_utc=ingestion_time)
                results.append(obs_v2)

        # Record provider run telemetry (Rule: No secrets in request_metadata)
        self._run_counter += 1
        run_record = ProviderRun(
            run_id=f"RUN-SCENARIO-{self.scenario.id}-{self._run_counter:04d}",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            started_at_utc=target_iso,
            finished_at_utc=target_iso,
            status=current_status,
            rows_received=len(results),
            duration_ms=45,
            error_type=self._last_error_type,
            error_message=self._last_error_message,
            request_metadata={
                "scenario_id": self.scenario.id,
                "as_of_utc": target_iso,
                "mode": self.scenario.mode.value,
            },
        )
        self._provider_runs.append(run_record)

        return results

    def fetch_hotspots(
        self,
        as_of: Optional[Union[datetime, str]] = None,
        consume: bool = True,
    ) -> List[Hotspot]:
        """Fetch observations projected as backward-compatible Hotspot models for the pipeline."""
        observations = self.fetch_observations(as_of=as_of, consume=consume)
        hotspots: List[Hotspot] = []
        for obs in observations:
            nearest_place = obs.source_attributes.get("nearest_place")
            h = hotspot_from_v2(obs, nearest_place=nearest_place)
            hotspots.append(h)
        return hotspots

    def get_provider_runs(self) -> List[ProviderRun]:
        """Return audit history of provider execution runs."""
        return list(self._provider_runs)

    def reset(self) -> None:
        """Reset provider consumption state and status."""
        self._consumed_obs_ids.clear()
        self._provider_status = ProviderStatus.SUCCESS
        self._last_error_type = None
        self._last_error_message = None
        self._provider_runs.clear()
        self._run_counter = 0

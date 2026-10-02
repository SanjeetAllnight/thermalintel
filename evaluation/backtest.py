"""Historical backtest interface and engine for ThermalIntel V2.

Provides clean abstractions and extensible fixtures to replay historical satellite
records through the ThermalIntel processing pipeline and compare output incidents
against known historical ground truth events.

Implements Requirement 12:
'Design a clean interface for future historical replay.
 It should eventually support:
 standard-processing satellite data
 → replay
 → compare against known events
 Do not require downloading external historical datasets during this task.
 Provide fixtures/interfaces sufficient for future integration.'
"""

import math
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Tuple, TYPE_CHECKING
from pydantic import BaseModel, Field

from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident
from services.replay.clock import SimulatedClock
from services.api.incidents.aggregator import haversine_distance_km

if TYPE_CHECKING:
    from services.replay.pipeline import ReplayPipeline


class KnownEvent(BaseModel):
    """Ground truth historical thermal event for backtest validation."""
    event_id: str = Field(..., description="Unique event identifier (e.g. 'HIST-CALIFORNIA-2025-001')")
    name: str = Field(..., description="Human-readable event name (e.g. 'Camp Fire Complex')")
    event_type: str = Field(..., description="Physical event category (e.g. 'wildfire', 'industrial_flare')")
    start_time_utc: str = Field(..., description="Known initiation timestamp in UTC")
    end_time_utc: str = Field(..., description="Known containment or extinguishment timestamp in UTC")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    radius_km: float = Field(default=5.0, gt=0.0, description="Approximate geographic radius of event perimeter")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BacktestResult(BaseModel):
    """Structured report documenting historical backtest performance."""
    dataset_name: str
    total_observations_replayed: int
    total_known_events: int
    detected_known_events: int
    detection_rate: float
    synthesized_incidents_count: int
    matched_pairs: List[Dict[str, Any]] = Field(default_factory=list)
    unmatched_incidents: List[str] = Field(default_factory=list)


class BacktestSource(ABC):
    """Abstract interface supplying historical satellite data and verified ground truth events."""

    @abstractmethod
    def get_dataset_metadata(self) -> Dict[str, Any]:
        """Return dataset description, sensor sources, and temporal boundaries."""
        pass

    @abstractmethod
    def get_observations(self) -> List[Observation]:
        """Return chronological stream of historical satellite observations."""
        pass

    @abstractmethod
    def get_known_events(self) -> List[KnownEvent]:
        """Return collection of verified ground truth events during the backtest period."""
        pass


class FixtureBacktestSource(BacktestSource):
    """In-memory fixture backtest source for deterministic local testing."""

    def __init__(
        self,
        dataset_name: str,
        observations: List[Observation],
        known_events: List[KnownEvent],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.dataset_name = dataset_name
        self._observations = sorted(observations, key=lambda o: o.acquisition_time_utc)
        self._known_events = known_events
        self._metadata = metadata or {"type": "local_fixture", "version": "1.0.0"}

    def get_dataset_metadata(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "observation_count": len(self._observations),
            "known_event_count": len(self._known_events),
            **self._metadata,
        }

    def get_observations(self) -> List[Observation]:
        return list(self._observations)

    def get_known_events(self) -> List[KnownEvent]:
        return list(self._known_events)


class BacktestEngine:
    """Executes backtests by driving pipeline replay and matching synthesized incidents against known events."""

    def __init__(self, pipeline: Optional[Any] = None):
        if pipeline is None:
            from services.replay.pipeline import ReplayPipeline
            self.pipeline = ReplayPipeline()
        else:
            self.pipeline = pipeline

    def run_backtest(self, source: BacktestSource) -> BacktestResult:
        """Execute historical replay and evaluate ground truth event discovery."""
        observations = source.get_observations()
        known_events = source.get_known_events()
        metadata = source.get_dataset_metadata()
        dataset_name = metadata.get("dataset_name", "historical_dataset")

        self.pipeline.reset()

        if observations:
            start_time = observations[0].acquisition_time_utc
            clock = SimulatedClock(start_time)
            self.pipeline.clock = clock

            # Process observations in chronological batches
            for obs in observations:
                clock.set_time(obs.acquisition_time_utc)
                self.pipeline.process_observations([obs], as_of_utc=obs.acquisition_time_utc)

        synthesized_incidents = self.pipeline.incidents

        # Evaluate spatiotemporal overlap against known events
        matched_pairs: List[Dict[str, Any]] = []
        matched_incident_ids: set[str] = set()
        matched_known_ids: set[str] = set()

        for known in known_events:
            for inc in synthesized_incidents:
                dist_km = haversine_distance_km(
                    known.latitude, known.longitude, inc.centroid_latitude, inc.centroid_longitude
                )
                # Check spatial tolerance
                if dist_km <= (known.radius_km + 5.0):
                    # Check temporal overlap
                    if (
                        inc.first_seen_utc <= known.end_time_utc
                        and inc.last_seen_utc >= known.start_time_utc
                    ):
                        matched_pairs.append({
                            "known_event_id": known.event_id,
                            "known_event_name": known.name,
                            "incident_id": inc.incident_id,
                            "distance_km": round(dist_km, 2),
                            "incident_peak_frp": inc.peak_frp,
                            "incident_severity": inc.current_severity.value,
                            "incident_classification": inc.current_classification.value,
                        })
                        matched_incident_ids.add(inc.incident_id)
                        matched_known_ids.add(known.event_id)
                        break

        total_known = len(known_events)
        detected_count = len(matched_known_ids)
        detection_rate = round(detected_count / total_known, 4) if total_known > 0 else 1.0

        unmatched = [
            inc.incident_id for inc in synthesized_incidents if inc.incident_id not in matched_incident_ids
        ]

        return BacktestResult(
            dataset_name=dataset_name,
            total_observations_replayed=len(observations),
            total_known_events=total_known,
            detected_known_events=detected_count,
            detection_rate=detection_rate,
            synthesized_incidents_count=len(synthesized_incidents),
            matched_pairs=matched_pairs,
            unmatched_incidents=unmatched,
        )

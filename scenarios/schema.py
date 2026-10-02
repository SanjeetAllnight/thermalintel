"""Scenario pack schema definitions for ThermalIntel V2.

Defines the declarative data model for replay scenarios, including simulated
observations, contextual injections, provider failure events, and expected domain states.
"""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime, timezone

from evaluation.labels import LabelType
from services.api.schemas.v2.common import now_utc_iso


class ScenarioMode(str, Enum):
    """Execution mode for the scenario."""
    SYNTHETIC = "synthetic"
    DEMO = "demo"
    HISTORICAL = "historical"


class ScenarioObservation(BaseModel):
    """Simulated observation record within a scenario."""
    observation_id: str = Field(..., description="Unique deterministic identifier")
    acquisition_time_utc: str = Field(..., description="ISO 8601 UTC sensor acquisition timestamp")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    brightness: float = Field(..., gt=0.0, description="Thermal band temperature in Kelvin")
    frp: float = Field(..., ge=0.0, description="Fire Radiative Power in MW")
    bright_t31: Optional[float] = Field(None, gt=0.0)
    scan: Optional[float] = Field(0.375, ge=0.0)
    track: Optional[float] = Field(0.375, ge=0.0)
    daynight: str = Field("N", pattern="^[DN]$")
    detection_confidence: str = Field("nominal", description="Provider detection rating (low, nominal, high)")
    satellite: Optional[str] = "Suomi-NPP"
    instrument: Optional[str] = "VIIRS"
    provider: str = "NASA_FIRMS"
    product: str = "VIIRS_SNPP_NRT"
    nearest_place: Optional[str] = None
    source_attributes: Dict[str, Any] = Field(default_factory=dict)
    
    # Context telemetry (optional overrides for weather, geospatial, history)
    context: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Pre-packaged contextual enrichment dictionary"
    )

    # Evaluation annotations
    expected_source: Optional[str] = Field(
        None,
        description="Expected thermal source category (e.g. 'industrial', 'wildfire')"
    )
    label_type: LabelType = Field(
        default=LabelType.SYNTHETIC_EXPECTATION,
        description="Provenance of label annotations"
    )

    @field_validator("daynight")
    @classmethod
    def validate_daynight(cls, v: str) -> str:
        upper = v.upper()
        if upper not in ("D", "N"):
            raise ValueError("daynight must be 'D' or 'N'")
        return upper


class ScenarioExpectedStates(BaseModel):
    """Expected outcome invariants for golden scenario testing."""
    min_incidents: Optional[int] = None
    max_incidents: Optional[int] = None
    expected_incident_ids: Optional[List[str]] = None
    expected_dominant_source: Optional[str] = None
    expected_escalation: Optional[bool] = None
    min_alerts: Optional[int] = None
    expected_alert_count: Optional[int] = None
    final_severity: Optional[str] = None
    expected_lifecycle_events: Optional[List[str]] = Field(
        default=None,
        description="Expected event types (e.g. ['created', 'escalated', 'closed'])"
    )


class ScenarioMetadata(BaseModel):
    """Scenario authoring metadata."""
    version: str = "1.0.0"
    author: Optional[str] = "ThermalIntel Team"
    tags: List[str] = Field(default_factory=list)
    seed: Optional[int] = 42
    created_at_utc: str = Field(default_factory=now_utc_iso)


class ProviderControlEvent(BaseModel):
    """Controlled provider degradation or recovery event."""
    timestamp_utc: str = Field(..., description="Timestamp when provider status changes")
    provider: str = Field("NASA_FIRMS", description="Provider name")
    status: str = Field(..., description="'success', 'degraded', 'failed'")
    error_message: Optional[str] = None
    error_type: Optional[str] = None
    latency_ms: Optional[int] = 120


class Scenario(BaseModel):
    """Declarative scenario pack model."""
    id: str = Field(..., description="Stable scenario identifier (e.g. 'SCN-001-INDUSTRIAL-SPIKE')")
    name: str = Field(..., description="Human-readable scenario title")
    description: str = Field(..., description="Detailed narrative and purpose of the scenario")
    mode: ScenarioMode = Field(default=ScenarioMode.SYNTHETIC)
    start_time_utc: str = Field(..., description="Starting simulation timestamp in ISO 8601 UTC")
    metadata: ScenarioMetadata = Field(default_factory=ScenarioMetadata)
    observations: List[ScenarioObservation] = Field(default_factory=list)
    provider_events: List[ProviderControlEvent] = Field(default_factory=list)
    expected_states: Optional[ScenarioExpectedStates] = None

    def sorted_observations(self) -> List[ScenarioObservation]:
        """Return all observations sorted chronologically by acquisition timestamp."""
        return sorted(self.observations, key=lambda o: o.acquisition_time_utc)

    def sorted_provider_events(self) -> List[ProviderControlEvent]:
        """Return all provider control events sorted chronologically."""
        return sorted(self.provider_events, key=lambda e: e.timestamp_utc)

    def get_timeline_timestamps(self) -> List[str]:
        """Return unique sorted timeline timestamps combining start time, observations, and provider events."""
        ts_set = {self.start_time_utc}
        for o in self.observations:
            ts_set.add(o.acquisition_time_utc)
        for e in self.provider_events:
            ts_set.add(e.timestamp_utc)
        return sorted(list(ts_set), key=lambda s: datetime.fromisoformat(s.replace("Z", "+00:00")))

    def observations_up_to(self, cutoff_utc: Union[str, datetime]) -> List[ScenarioObservation]:
        """Return observations acquired at or before the given cutoff timestamp."""
        cutoff_dt = (
            datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
            if isinstance(cutoff_utc, str)
            else cutoff_utc
        )
        if cutoff_dt.tzinfo is None:
            cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)

        results = []
        for o in self.sorted_observations():
            odt = datetime.fromisoformat(o.acquisition_time_utc.replace("Z", "+00:00"))
            if odt.tzinfo is None:
                odt = odt.replace(tzinfo=timezone.utc)
            if odt <= cutoff_dt:
                results.append(o)
        return results

    def provider_events_up_to(self, cutoff_utc: Union[str, datetime]) -> List[ProviderControlEvent]:
        """Return provider events occurring at or before the given cutoff timestamp."""
        cutoff_dt = (
            datetime.fromisoformat(cutoff_utc.replace("Z", "+00:00"))
            if isinstance(cutoff_utc, str)
            else cutoff_utc
        )
        if cutoff_dt.tzinfo is None:
            cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)

        results = []
        for e in self.sorted_provider_events():
            edt = datetime.fromisoformat(e.timestamp_utc.replace("Z", "+00:00"))
            if edt.tzinfo is None:
                edt = edt.replace(tzinfo=timezone.utc)
            if edt <= cutoff_dt:
                results.append(e)
        return results


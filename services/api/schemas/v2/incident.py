"""Canonical Incident and IncidentObservation Contracts for ThermalIntel V2.

Represents persistent real-world thermal events synthesized from one or more
satellite observations over time. Incident identity remains stable across updates.
"""

from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field
from .common import IncidentStatus, SourceType, RiskLevel, Coordinates, now_utc_iso


class Incident(BaseModel):
    """Canonical persistent real-world incident model.
    
    Identity Rule: Incident ID is permanent and immutable upon creation.
    It does NOT change when observations are added, when the centroid shifts,
    or when a new primary observation is designated.
    """
    incident_id: str = Field(..., description="Stable unique incident identifier (e.g. 'INC-20261001-0001')")
    status: IncidentStatus = Field(default=IncidentStatus.ACTIVE, description="Current operational state")
    
    # Temporal bounds
    first_seen_utc: str = Field(..., description="Earliest detection acquisition timestamp in UTC")
    last_seen_utc: str = Field(..., description="Most recent detection acquisition timestamp in UTC")
    
    # Geographic bounds
    centroid_latitude: float = Field(..., ge=-90.0, le=90.0, description="Weighted or geometric centroid latitude (WGS84)")
    centroid_longitude: float = Field(..., ge=-180.0, le=180.0, description="Weighted or geometric centroid longitude (WGS84)")
    geometry_geojson: Optional[Dict[str, Any]] = Field(
        None,
        description="GeoJSON geometry (Point, MultiPoint, or Polygon) representing the spatial footprint"
    )
    nearest_place: Optional[str] = Field(None, description="Human-readable nearby geographic locality or landmark")
    
    # Quantitative radiometrics & scale
    peak_frp: float = Field(..., ge=0.0, description="Highest Fire Radiative Power (MW) observed across all associated detections")
    average_frp: float = Field(..., ge=0.0, description="Average Fire Radiative Power (MW) across detections")
    observation_count: int = Field(default=1, ge=1, description="Total number of satellite observations correlated to this incident")
    
    # Current intelligence state (derived from latest correlated assessment)
    current_risk_score: float = Field(..., ge=0.0, le=100.0, description="Current composite risk score (0-100)")
    current_severity: RiskLevel = Field(..., description="Current categorical severity rating")
    current_classification: SourceType = Field(default=SourceType.UNKNOWN, description="Dominant classified thermal source")
    current_assessment_id: Optional[str] = Field(
        None,
        description="Reference identifier to the active Assessment record"
    )
    
    # Audit timestamps
    created_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp of incident creation")
    updated_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp of last state update")


class IncidentObservation(BaseModel):
    """Associative relationship link between an Incident and a remote Observation.
    
    Supports 1:N and N:M associations (e.g. during split, merge, or re-clustering).
    """
    id: Optional[int] = Field(None, description="Database row identifier if persisted")
    incident_id: str = Field(..., description="Foreign key to the associated Incident")
    observation_id: str = Field(..., description="Foreign key to the associated Observation")
    joined_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when association was established")
    association_method: str = Field(
        default="dbscan_spatiotemporal",
        description="Method or algorithm used to associate (e.g. 'dbscan_spatiotemporal', 'manual', 'proximity_threshold')"
    )
    association_reason: Optional[str] = Field(
        None,
        description="Detailed contextual reason or distance score justifying association"
    )

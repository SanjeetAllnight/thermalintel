"""Incident domain models and state tracking for ThermalIntel Phase 4.

Extends the frozen schema ecosystem with operational incident definitions
and aggregation data structures.
"""

from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.hotspot import Hotspot


class IncidentStatus(str, Enum):
    """Operational state of an incident."""
    ACTIVE = "active"
    MONITORING = "monitoring"
    RESOLVED = "resolved"
    UNKNOWN = "unknown"


class AggregatedIncident(BaseModel):
    """Operational incident aggregating multiple proximate thermal detections.
    
    Represents a unified real-world thermal event synthesized from one or more
    satellite hotspot detections.
    """
    incident_id: str = Field(..., description="Deterministic incident identifier (e.g. INC-VIIRS-SNPP-20261001-001)")
    primary_hotspot_id: str = Field(..., description="Hotspot ID of the primary/representative detection")
    cluster_id: Optional[str] = Field(None, description="Spatial cluster ID if assigned")
    hotspot_ids: List[str] = Field(default_factory=list, description="All associated detection IDs in this incident")
    detection_count: int = Field(default=1, ge=1, description="Number of aggregated hotspot observations")
    
    # Spatial & Temporal bounds
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Centroid or primary latitude")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Centroid or primary longitude")
    nearest_place: Optional[str] = Field(None, description="Descriptive geographic locality")
    first_seen: str = Field(..., description="Earliest detection ISO timestamp or acq date/time")
    last_seen: str = Field(..., description="Latest detection ISO timestamp or acq date/time")
    
    # Intelligence & Risk metrics (conservatively inherited from peak observation)
    source_type: SourceType = Field(default=SourceType.UNKNOWN, description="Dominant classified thermal source")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Highest composite risk score among observations")
    risk_level: RiskLevel = Field(..., description="Categorical severity rating")
    peak_frp: float = Field(..., ge=0.0, description="Maximum Fire Radiative Power (MW) recorded")
    average_frp: float = Field(..., ge=0.0, description="Average Fire Radiative Power across detections")
    is_anomaly: bool = Field(default=False, description="True if any detection was statistically anomalous")
    
    # Operational workflow
    status: IncidentStatus = Field(default=IncidentStatus.ACTIVE, description="Current operational status")
    primary_hotspot: Optional[Hotspot] = Field(None, description="Full primary hotspot object")

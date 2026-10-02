"""ThermalIntel V2 Common Contracts, Enumerations, and Provenance Models.

Freezes canonical enumerations, timestamp standards, and provenance structures
shared across all V2 domain models.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class SourceType(str, Enum):
    """Categorical classification of thermal anomaly source."""
    WILDFIRE = "wildfire"
    INDUSTRIAL = "industrial"
    AGRICULTURAL = "agricultural"
    URBAN = "urban"
    VOLCANIC = "volcanic"
    PRESCRIBED_BURN = "prescribed_burn"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Operational risk/severity category."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertSeverity(str, Enum):
    """Operational priority of alert notifications."""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertState(str, Enum):
    """Lifecycle state of an operational alert."""
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"
    SUPPRESSED = "suppressed"


class IncidentStatus(str, Enum):
    """Operational state of a tracked incident."""
    ACTIVE = "active"
    MONITORING = "monitoring"
    CONTAINED = "contained"
    RESOLVED = "resolved"
    CLOSED = "closed"


class IncidentEventType(str, Enum):
    """Append-only incident timeline event types."""
    CREATED = "created"
    OBSERVATION_ADDED = "observation_added"
    ESCALATED = "escalated"
    DEESCALATED = "deescalated"
    MERGED = "merged"
    SPLIT = "split"
    ACKNOWLEDGED = "acknowledged"
    CLOSED = "closed"
    REOPENED = "reopened"


class FreshnessState(str, Enum):
    """Data freshness status for enrichment context."""
    FRESH = "fresh"
    CACHED = "cached"
    STALE = "stale"
    UNAVAILABLE = "unavailable"


class ProviderStatus(str, Enum):
    """Execution status of an external provider fetch run."""
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class EnrichmentType(str, Enum):
    """Category of contextual enrichment."""
    GEOSPATIAL = "geospatial"
    WEATHER = "weather"
    HISTORICAL = "historical"
    TERRAIN = "terrain"
    OTHER = "other"


def now_utc_iso() -> str:
    """Return current wall-clock time as a standardized ISO 8601 UTC string."""
    return datetime.now(timezone.utc).isoformat()


class Coordinates(BaseModel):
    """Geographic coordinate in WGS84 with optional elevation."""
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (WGS84)")
    elevation_meters: Optional[float] = Field(None, description="Elevation above sea level in meters")


class RiskFactor(BaseModel):
    """Individual explainable factor contributing to composite risk score."""
    factor: str = Field(..., description="Short canonical title of the risk factor")
    weight: float = Field(..., ge=0.0, le=1.0, description="Relative contribution weight (0 to 1)")
    impact: RiskLevel = Field(..., description="Categorical impact level")
    description: str = Field(..., description="Explainable rationale of why this factor increases or decreases risk")


class Provenance(BaseModel):
    """Canonical provenance metadata tracking the origin, lineage, and freshness of any datum.
    
    Ensures every datum answers: 'Where did this value come from, when was it observed,
    and when was it acquired by ThermalIntel?'
    """
    provider: str = Field(..., description="Name of external service or sensor provider (e.g. 'NASA_FIRMS', 'OpenStreetMap', 'Open-Meteo')")
    product: str = Field(..., description="Specific dataset or API product name (e.g. 'VIIRS_SNPP_NRT', 'Overpass_API', 'Forecast_10m')")
    observed_at_utc: str = Field(..., description="ISO 8601 UTC timestamp when the physical phenomenon was acquired/observed")
    fetched_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when ThermalIntel fetched the data")
    freshness_state: FreshnessState = Field(default=FreshnessState.FRESH, description="Freshness status of this datum")
    ttl_seconds: Optional[int] = Field(None, ge=0, description="Optional cache time-to-live in seconds")
    reference: Optional[str] = Field(None, description="External URL, query hash, or storage reference")


class ConfidenceBreakdown(BaseModel):
    """Explicit decomposition of confidence metrics to prevent conflation.
    
    Guarantees strict separation between:
    1. Provider Detection Confidence: instrument-level sensor signal reliability (e.g. VIIRS low/nominal/high).
    2. Classification Confidence: ML model posterior probability for predicted source type.
    3. Data Quality / Completeness: proportion of required context successfully fetched.
    """
    detection_confidence: str = Field(..., description="Provider-native signal confidence (e.g. 'low', 'nominal', 'high', '85%'). NOT AI confidence.")
    classification_confidence: Optional[float] = Field(None, ge=0.0, le=1.0, description="ML classifier posterior probability for predicted source (0 to 1)")
    data_completeness_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Completeness of input features and enrichment context (0 to 1)")

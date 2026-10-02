"""Canonical Provider Run Contract for ThermalIntel V2.

Provides execution telemetry and lineage tracking for every external data acquisition
run (e.g. NASA FIRMS API, Overpass queries, Open-Meteo fetches).
CRITICAL: NEVER stores API keys, authentication headers, or secrets.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from .common import ProviderStatus, now_utc_iso


class ProviderRun(BaseModel):
    """Execution telemetry record for an external provider ingestion job.
    
    Security Guarantee: All request parameters must be sanitized prior to storage.
    API keys, credentials, and tokens are strictly excluded.
    """
    run_id: str = Field(..., description="Unique provider execution identifier (e.g. 'RUN-FIRMS-20261001-085000')")
    provider: str = Field(..., description="Name of external service (e.g. 'NASA_FIRMS', 'OpenStreetMap', 'Open-Meteo')")
    product: str = Field(..., description="Product or query endpoint (e.g. 'VIIRS_SNPP_NRT_CSV', 'Overpass_OSM_Features')")
    
    # Execution timeline
    started_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when network fetch commenced")
    finished_at_utc: Optional[str] = Field(None, description="ISO 8601 UTC timestamp when fetch cycle completed")
    status: ProviderStatus = Field(default=ProviderStatus.RUNNING, description="Execution outcome state")
    
    # Quantitative throughput
    rows_received: int = Field(default=0, ge=0, description="Count of raw records/features parsed from payload")
    duration_ms: Optional[int] = Field(None, ge=0, description="Total execution duration in milliseconds")
    
    # Error classification (if failed or partial)
    error_type: Optional[str] = Field(None, description="Categorical error classifier (e.g. 'Timeout', 'RateLimit', 'Http502', 'ParseError')")
    error_message: Optional[str] = Field(None, description="Sanitized error description with credentials redacted")
    
    # Sanitized request metadata safe for storage
    request_metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Safe query bounds, bbox coordinates, or date filters (Strictly no API keys)"
    )
    payload_id: Optional[str] = Field(
        None,
        description="Foreign reference to stored raw response payload if captured"
    )

    @field_validator("request_metadata")
    @classmethod
    def prevent_secrets_in_metadata(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Defensive validator ensuring no credential keys are stored in metadata."""
        prohibited_substrings = ("key", "secret", "token", "auth", "password")
        for key in v.keys():
            lower_k = key.lower()
            if any(sub in lower_k for sub in prohibited_substrings):
                raise ValueError(f"Prohibited credential key '{key}' found in request_metadata")
        return v

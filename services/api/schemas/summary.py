"""Summary, Source Breakdown, and Data Refresh schemas."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .common import DataMode, RiskLevel, SourceType
from .hotspot import Hotspot


class SourceBreakdown(BaseModel):
    """Categorical source distribution metrics."""
    source_type: SourceType = Field(..., description="Classified source key")
    display_name: str = Field(..., description="Human-friendly label (e.g. 'Wildfire / Forest Fire')")
    count: int = Field(..., ge=0, description="Total active hotspots identified under this source")
    percentage: float = Field(..., ge=0.0, le=100.0, description="Percentage share of total active hotspots")
    average_frp: float = Field(..., ge=0.0, description="Mean Fire Radiative Power (MW) for this category")
    average_risk: float = Field(..., ge=0.0, le=100.0, description="Mean risk score (0-100) for this category")
    primary_driver: str = Field(..., description="Short explanation of primary risk or signature mechanism")


class SourcesResponse(BaseModel):
    """Payload for GET /api/sources."""
    sources: List[SourceBreakdown] = Field(..., description="Distribution of thermal anomalies by source")
    total_evaluated: int = Field(..., ge=0, description="Total active hotspots evaluated")
    dominant_source: SourceType = Field(..., description="Most frequent thermal source category")
    data_mode: DataMode = Field(..., description="Active data mode (live or demo)")
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp")


class SummaryResponse(BaseModel):
    """Payload for GET /api/summary dashboard KPIs and high-level analytics."""
    total_active_hotspots: int = Field(..., ge=0, description="Total active hotspots in system")
    critical_risk_count: int = Field(..., ge=0, description="Hotspots with risk score >= 75 (Critical)")
    high_risk_count: int = Field(..., ge=0, description="Hotspots with risk score 50-74 (High)")
    medium_risk_count: int = Field(..., ge=0, description="Hotspots with risk score 25-49 (Medium)")
    low_risk_count: int = Field(..., ge=0, description="Hotspots with risk score 0-24 (Low)")
    active_alerts_count: int = Field(..., ge=0, description="Number of currently unacknowledged alerts")
    average_frp: float = Field(..., ge=0.0, description="Average Fire Radiative Power in MW")
    max_frp: float = Field(..., ge=0.0, description="Peak Fire Radiative Power recorded in active set")
    average_risk_score: float = Field(..., ge=0.0, le=100.0, description="Mean risk score across all active hotspots")
    data_mode: DataMode = Field(..., description="Current data mode: live or demo")
    last_sync_time: str = Field(..., description="ISO 8601 UTC timestamp of last ingestion/sync")
    dominant_source: SourceType = Field(..., description="Most common thermal source category")
    source_counts: Dict[str, int] = Field(..., description="Map of source type to active hotspot count")
    recent_critical_hotspots: List[Hotspot] = Field(
        default_factory=list,
        description="Top high/critical risk hotspots requiring immediate attention"
    )


class RefreshRequest(BaseModel):
    """Optional payload for POST /api/refresh."""
    force_sample: bool = Field(default=False, description="Force fallback to bundled sample dataset even if FIRMS key exists")
    bbox: Optional[List[float]] = Field(
        default=None,
        description="Bounding box [min_lat, min_lon, max_lat, max_lon] to filter ingestion"
    )
    days: Optional[int] = Field(default=1, ge=1, le=7, description="Number of historical days to pull (1-7)")


class RefreshResponse(BaseModel):
    """Payload returned by POST /api/refresh."""
    status: str = Field(..., description="Sync execution result: success, fallback_sample, or error")
    message: str = Field(..., description="Human-readable outcome description")
    ingested_count: int = Field(..., ge=0, description="Number of thermal anomaly records ingested and processed")
    data_mode: DataMode = Field(..., description="Data mode resulting from sync (live or demo)")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp when sync completed")
    execution_time_seconds: float = Field(..., ge=0.0, description="Duration of ingestion and enrichment cycle in seconds")

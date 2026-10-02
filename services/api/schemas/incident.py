"""Enriched Incident Detail schemas for deep-dive hotspot analysis."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .common import DataMode, RiskLevel
from .hotspot import Hotspot
from .intelligence import IntelligenceResult


class GeospatialContext(BaseModel):
    """OpenStreetMap / Overpass and GIS topographic enrichment."""
    land_cover: str = Field(..., description="Land cover classification (e.g. dense_forest, scrubland, industrial_site)")
    nearest_infrastructure: Optional[str] = Field(None, description="Closest critical infrastructure name & type")
    distance_to_infrastructure_meters: Optional[float] = Field(None, description="Distance in meters to nearest infrastructure")
    nearest_settlement: Optional[str] = Field(None, description="Closest town, city, or residential area")
    distance_to_settlement_meters: Optional[float] = Field(None, description="Distance in meters to nearest settlement")
    is_protected_area: bool = Field(default=False, description="Whether location intersects a national park or reserve")
    protected_area_name: Optional[str] = Field(None, description="Name of the protected conservation area if applicable")
    elevation_meters: Optional[float] = Field(None, description="Elevation above sea level in meters")
    slope_degrees: Optional[float] = Field(None, description="Terrain slope angle (affects fire spread velocity)")
    fuel_load_estimate: Optional[str] = Field(default="moderate", description="Vegetation fuel dryness/density estimate")


class WeatherContext(BaseModel):
    """Open-Meteo weather parameters at the hotspot coordinates."""
    temperature_celsius: Optional[float] = Field(None, description="Ambient air temperature in °C (None if unavailable)")
    relative_humidity_percent: Optional[float] = Field(None, ge=0.0, le=100.0, description="Relative humidity percentage (None if unavailable)")
    wind_speed_kmh: Optional[float] = Field(None, ge=0.0, description="Wind speed at 10m in km/h (None if unavailable)")
    wind_gust_kmh: Optional[float] = Field(None, description="Wind gust speed in km/h")
    wind_direction_degrees: Optional[float] = Field(None, ge=0.0, le=360.0, description="Wind direction in degrees (None if unavailable)")
    wind_direction_cardinal: Optional[str] = Field(None, description="Cardinal wind direction (e.g. NW, SE, or None)")
    precipitation_mm: Optional[float] = Field(default=0.0, ge=0.0, description="Recent precipitation in mm (last 24 hours)")
    fire_weather_index: Optional[float] = Field(None, ge=0.0, le=100.0, description="Normalized fire danger proxy index")
    forecast_summary: str = Field(..., description="Short weather forecast description")


class HistoricalContext(BaseModel):
    """Historical thermal anomaly recurrence analysis."""
    prior_detections_30d: int = Field(default=0, ge=0, description="Thermal detections within 1km over past 30 days")
    prior_detections_90d: int = Field(default=0, ge=0, description="Thermal detections within 1km over past 90 days")
    is_recurrent_site: bool = Field(default=False, description="Flagged if area shows repeated thermal activity")
    recurrent_pattern: Optional[str] = Field(
        default="none",
        description="Pattern classification: known_industrial_stack, agricultural_clearing, persistent_burn, none"
    )
    first_detected_date: Optional[str] = Field(None, description="Earliest detection date recorded in system (YYYY-MM-DD)")
    detection_frequency_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized recurrence index (0 to 1)")


class TimelineEvent(BaseModel):
    """Historical progression or satellite pass timeline item for an incident."""
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    event_type: str = Field(..., description="Type of event: satellite_pass, weather_shift, alert_triggered, verification")
    summary: str = Field(..., description="Short title of the timeline event")
    details: Optional[Dict[str, Any]] = Field(default=None, description="Structured key-value context")


class IncidentDetail(BaseModel):
    """Comprehensive incident payload returned by GET /api/hotspots/{id}."""
    hotspot: Hotspot = Field(..., description="Base normalized hotspot data")
    geospatial: GeospatialContext = Field(..., description="Enriched GIS context from OpenStreetMap")
    weather: WeatherContext = Field(..., description="Enriched local weather from Open-Meteo")
    historical: HistoricalContext = Field(..., description="Enriched historical persistence analysis")
    intelligence: IntelligenceResult = Field(..., description="AI classification, risk score breakdown, and factors")
    timeline: List[TimelineEvent] = Field(default_factory=list, description="Chronological timeline of detections/events")
    data_mode: DataMode = Field(..., description="Live FIRMS data or fallback demo dataset")

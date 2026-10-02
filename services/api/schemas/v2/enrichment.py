"""Canonical Enrichment Contracts for ThermalIntel V2.

Defines contextual data structures with independent provenance per source.
Explicitly distinguishes available vs unavailable data without fabricating values.
"""

from typing import Optional, Dict, Any, List, Generic, TypeVar
from pydantic import BaseModel, Field
from .common import Provenance, FreshnessState, EnrichmentType, now_utc_iso

T = TypeVar("T")


class EnrichmentDatum(BaseModel, Generic[T]):
    """Generic atomic contextual datum with explicit provenance and availability status.
    
    Prevents value fabrication: if an external service is unavailable or times out,
    'status' is 'unavailable' and 'value' is None.
    """
    value: Optional[T] = Field(None, description="Actual measured or enriched value; None if unavailable")
    status: str = Field(default="available", description="Status: 'available', 'unavailable', 'degraded', 'error'")
    provenance: Provenance = Field(..., description="Complete audit lineage of where and when this datum was fetched")
    error_message: Optional[str] = Field(None, description="Descriptive error if status is 'unavailable' or 'error'")

    @property
    def is_available(self) -> bool:
        return self.status == "available" and self.value is not None


class GeospatialEnrichment(BaseModel):
    """Enrichment context derived from OpenStreetMap / GIS layers."""
    land_cover: EnrichmentDatum[str] = Field(..., description="Land cover classification (e.g. 'dense_forest', 'shrubland')")
    nearest_settlement: EnrichmentDatum[str] = Field(..., description="Closest town, city, or residential community")
    distance_to_settlement_meters: EnrichmentDatum[float] = Field(..., description="Distance in meters to nearest settlement")
    nearest_infrastructure: EnrichmentDatum[str] = Field(..., description="Closest critical infrastructure name and type")
    distance_to_infrastructure_meters: EnrichmentDatum[float] = Field(..., description="Distance in meters to critical asset")
    is_protected_area: EnrichmentDatum[bool] = Field(..., description="Whether coordinates intersect a national park / reserve")
    protected_area_name: Optional[EnrichmentDatum[str]] = Field(None, description="Name of conservation area if applicable")


class WeatherEnrichment(BaseModel):
    """Enrichment context derived from numerical weather prediction APIs (e.g. Open-Meteo)."""
    temperature_celsius: EnrichmentDatum[float] = Field(..., description="Ambient air temperature at 2m in °C")
    relative_humidity_percent: EnrichmentDatum[float] = Field(..., description="Relative humidity percentage (0-100%)")
    wind_speed_kmh: EnrichmentDatum[float] = Field(..., description="Wind speed at 10m in km/h")
    wind_gust_kmh: Optional[EnrichmentDatum[float]] = Field(None, description="Peak wind gust speed in km/h")
    wind_direction_degrees: EnrichmentDatum[float] = Field(..., description="Wind direction in degrees (0-360°)")
    wind_direction_cardinal: EnrichmentDatum[str] = Field(..., description="Cardinal wind heading (e.g. 'NW', 'SE')")
    precipitation_mm_24h: EnrichmentDatum[float] = Field(..., description="Accumulated rainfall over past 24 hours in mm")
    fire_weather_index: Optional[EnrichmentDatum[float]] = Field(None, description="Normalized Canadian Fire Weather Index (FWI)")


class HistoricalEnrichment(BaseModel):
    """Enrichment context derived from historical satellite detection records."""
    prior_detections_30d: EnrichmentDatum[int] = Field(..., description="Detections within 1km radius over past 30 days")
    prior_detections_90d: EnrichmentDatum[int] = Field(..., description="Detections within 1km radius over past 90 days")
    is_recurrent_site: EnrichmentDatum[bool] = Field(..., description="True if site exhibits recurring thermal anomalies")
    recurrent_pattern: EnrichmentDatum[str] = Field(..., description="Pattern: 'industrial_flare', 'agricultural_clearing', 'persistent_wildfire', 'none'")
    recurrence_score: EnrichmentDatum[float] = Field(..., description="Normalized historical recurrence index (0 to 1)")


class TerrainEnrichment(BaseModel):
    """Enrichment context derived from Digital Elevation Models (DEM) and fuel models."""
    elevation_meters: EnrichmentDatum[float] = Field(..., description="Elevation above sea level in meters")
    slope_degrees: EnrichmentDatum[float] = Field(..., description="Terrain slope in degrees (fire spread accelerant)")
    aspect_degrees: Optional[EnrichmentDatum[float]] = Field(None, description="Terrain sun aspect in degrees")
    fuel_load_estimate: EnrichmentDatum[str] = Field(..., description="Vegetation fuel dryness/density index")


class EnrichmentSnapshot(BaseModel):
    """Unified collection of all contextual enrichment for a given target entity.
    
    Provides independent provenance per domain. Allows missing or partially degraded
    context without corrupting other domains.
    """
    snapshot_id: str = Field(..., description="Unique snapshot identifier")
    target_id: str = Field(..., description="Observation ID or Incident ID enriched by this snapshot")
    target_type: str = Field(..., description="'observation' or 'incident'")
    geospatial: Optional[GeospatialEnrichment] = Field(None, description="OSM / GIS context")
    weather: Optional[WeatherEnrichment] = Field(None, description="Atmospheric weather context")
    historical: Optional[HistoricalEnrichment] = Field(None, description="Historical recurrence context")
    terrain: Optional[TerrainEnrichment] = Field(None, description="Topographic terrain context")
    created_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp of snapshot compilation")

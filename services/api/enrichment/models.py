"""Enrichment output domain models for ThermalIntel.

Provides the typed EnrichmentResult contract between Phase 2 (Geo/Weather/History Enrichment)
and Phase 3 (Intelligence & ML Engine) / Phase 4 (Incident Aggregation).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from services.api.schemas.incident import GeospatialContext, HistoricalContext, WeatherContext
from services.api.schemas.v2.enrichment import EnrichmentSnapshot


class EnrichmentStatus(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"


class EnrichmentResult(BaseModel):
    """Unified contextual enrichment container for a single thermal hotspot.
    
    Combines:
    - OpenStreetMap geospatial telemetry & proximity metrics
    - Open-Meteo hyperlocal atmospheric observations
    - Historical detection recurrence and persistence scoring
    - Subsystem telemetry availability status
    - V2 Canonical EnrichmentSnapshot with atomic provenance per source
    """
    hotspot_id: str = Field(..., description="Target hotspot identifier")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    status: EnrichmentStatus = Field(
        default=EnrichmentStatus.COMPLETE,
        description="Overall enrichment status: complete, partial, or unavailable"
    )

    # Core Phase 0 / Incident Schema Contexts
    geospatial: GeospatialContext = Field(..., description="Geospatial & topographic context")
    weather: WeatherContext = Field(..., description="Atmospheric & fire weather context")
    historical: HistoricalContext = Field(..., description="Historical persistence context")

    # Granular source telemetry indicators
    sources_status: Dict[str, str] = Field(
        default_factory=lambda: {
            "osm": "unknown",
            "weather": "unknown",
            "historical": "unknown",
            "terrain": "unknown"
        },
        description="Source status breakdown (available, cached, unavailable, computed)"
    )

    # Convenience intelligence-ready derived indicators
    nearest_industrial_facility: Optional[str] = Field(
        None,
        description="Name of closest industrial plant/works"
    )
    distance_to_industrial_meters: Optional[float] = Field(
        None,
        ge=0.0,
        description="Distance to nearest industrial facility in meters"
    )
    nearby_industrial_count: int = Field(
        default=0,
        ge=0,
        description="Number of industrial facilities within 5km"
    )
    nearby_infrastructure_count: int = Field(
        default=0,
        ge=0,
        description="Number of critical infrastructure features within 5km"
    )
    nearby_settlement_count: int = Field(
        default=0,
        ge=0,
        description="Number of towns/settlements within 10km"
    )
    persistence_score: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Normalized recurrence persistence score (0 to 1)"
    )
    repeated_activity: bool = Field(
        default=False,
        description="Flagged True if anomaly has recurred in 30d window"
    )
    enriched_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        description="ISO 8601 UTC timestamp of enrichment generation"
    )

    # V2 Canonical Snapshot with granular provenance
    snapshot: Optional[EnrichmentSnapshot] = Field(
        default=None,
        description="Canonical V2 EnrichmentSnapshot with explicit audit lineage per datum"
    )

    def to_incident_dict(self) -> Dict[str, Any]:
        """Convert into database-ready dictionary for incident_details table."""
        return {
            "geospatial": self.geospatial.model_dump(),
            "weather": self.weather.model_dump(),
            "historical": self.historical.model_dump()
        }

    def to_intelligence_kwargs(
        self,
        frp: float = 0.0,
        brightness: float = 0.0
    ) -> Dict[str, Any]:
        """Produce dictionary arguments for ThermalIntelligenceEngine.evaluate_hotspot."""
        return {
            "hotspot_id": self.hotspot_id,
            "frp": frp,
            "brightness": brightness,
            "land_cover": self.geospatial.land_cover,
            "historical_recurrence": self.historical.prior_detections_30d,
            "is_protected_area": self.geospatial.is_protected_area,
            "wind_speed_kmh": self.weather.wind_speed_kmh,
            "relative_humidity_percent": self.weather.relative_humidity_percent,
            "temperature_celsius": self.weather.temperature_celsius,
            "distance_to_settlement_m": self.geospatial.distance_to_settlement_meters,
            "distance_to_infra_m": self.geospatial.distance_to_infrastructure_meters,
            "slope_degrees": self.geospatial.slope_degrees
        }

    def to_v2_snapshot(self, target_type: str = "observation") -> EnrichmentSnapshot:
        """Retrieve attached V2 snapshot or synthesize one from current contexts."""
        if self.snapshot is not None:
            return self.snapshot

        from services.api.geospatial.overpass import derive_geospatial_v2, OSMStatus
        from services.api.weather.open_meteo import WeatherResult, WeatherStatus
        from services.api.geospatial.terrain import TerrainResult
        from services.api.schemas.v2.common import now_utc_iso
        import uuid

        # Synthesize V2 blocks from available context
        osm_status_val = self.sources_status.get("osm", "unavailable")
        try:
            osm_enum = OSMStatus(osm_status_val)
        except ValueError:
            osm_enum = OSMStatus.SUCCESS_NON_EMPTY if osm_status_val == "available" else OSMStatus.UNAVAILABLE

        v2_geo = derive_geospatial_v2(
            target_lat=self.latitude,
            target_lon=self.longitude,
            features=[],
            status=osm_enum
        )

        w_status = WeatherStatus.AVAILABLE if self.sources_status.get("weather") in ("available", "cached") else WeatherStatus.UNAVAILABLE
        w_res = WeatherResult(
            context=self.weather,
            status=w_status
        )
        v2_weather = w_res.to_v2_enrichment(self.latitude, self.longitude)

        # Synthesize historical V2 block
        from services.api.history.recurrence import HistoricalAnalysisResult
        h_res = HistoricalAnalysisResult(
            context=self.historical,
            persistence_score=self.persistence_score,
            repeated_activity=self.repeated_activity,
            status=self.sources_status.get("historical", "computed")
        )
        v2_hist = h_res.to_v2_enrichment()

        # Topographic terrain
        t_res = TerrainResult(
            elevation_meters=self.geospatial.elevation_meters,
            slope_degrees=self.geospatial.slope_degrees,
            fuel_load_estimate=self.geospatial.fuel_load_estimate or "unknown",
            status="available" if self.geospatial.elevation_meters is not None else "unavailable"
        )
        v2_terrain = t_res.to_v2_enrichment()

        return EnrichmentSnapshot(
            snapshot_id=f"SNAP-{uuid.uuid4().hex[:12].upper()}",
            target_id=self.hotspot_id,
            target_type=target_type,
            geospatial=v2_geo,
            weather=v2_weather,
            historical=v2_hist,
            terrain=v2_terrain,
            created_at_utc=now_utc_iso()
        )

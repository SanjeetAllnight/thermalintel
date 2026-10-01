"""Enrichment output domain models for ThermalIntel.

Provides the typed EnrichmentResult contract between Phase 2 (Geo/Weather/History Enrichment)
and Phase 3 (Intelligence & ML Engine) / Phase 4 (Incident Aggregation).
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from services.api.schemas.incident import GeospatialContext, HistoricalContext, WeatherContext


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
            "historical": "unknown"
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

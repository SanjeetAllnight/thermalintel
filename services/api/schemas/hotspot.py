"""Normalized Hotspot schemas for thermal anomaly records."""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from .common import RiskLevel, SourceType, DataMode


class Hotspot(BaseModel):
    """Normalized thermal anomaly record combining satellite ingestion and primary intelligence."""
    id: str = Field(..., description="Unique hotspot identifier (e.g. VIIRS-SNPP-20261001-001)")
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (WGS84)")
    brightness: float = Field(..., description="Channel 21/I-4 brightness temperature in Kelvin")
    scan: float = Field(default=0.375, description="Along-scan pixel resolution in km")
    track: float = Field(default=0.375, description="Along-track pixel resolution in km")
    acq_date: str = Field(..., description="Acquisition date (YYYY-MM-DD)")
    acq_time: str = Field(..., description="Acquisition time (HHMM in UTC)")
    satellite: str = Field(..., description="Satellite identifier (e.g. NOAA-20, Suomi-NPP, Terra, Aqua)")
    instrument: str = Field(default="VIIRS", description="Sensor instrument name (VIIRS or MODIS)")
    confidence: str = Field(..., description="Detection confidence: low, nominal, high (or percentage)")
    version: str = Field(default="1.0NRT", description="NRT or standard processing version")
    bright_t31: Optional[float] = Field(None, description="Channel 31/I-5 brightness temperature in Kelvin")
    frp: float = Field(..., ge=0.0, description="Fire Radiative Power in Megawatts (MW)")
    daynight: str = Field(..., pattern="^[DN]$", description="'D' for daytime, 'N' for nighttime")

    # Enriched and Intelligence fields
    source_type: SourceType = Field(default=SourceType.UNKNOWN, description="Classified thermal source")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Normalized risk severity score (0 to 100)")
    risk_level: RiskLevel = Field(..., description="Categorical risk rating: low, medium, high, critical")
    is_anomaly: bool = Field(default=False, description="Flagged as unusual statistical anomaly by intelligence engine")
    cluster_id: Optional[str] = Field(None, description="Hotspot spatial cluster identifier if clustered")
    cluster_size: Optional[int] = Field(default=1, description="Number of grouped satellite pixels in this cluster")
    nearest_place: Optional[str] = Field(None, description="Human-readable nearby locality or administrative zone")
    last_updated: str = Field(..., description="ISO 8601 UTC timestamp of last record update")

    class Config:
        json_schema_extra = {
            "example": {
                "id": "VIIRS-SNPP-20261001-0042",
                "latitude": 38.7421,
                "longitude": -122.8105,
                "brightness": 348.6,
                "scan": 0.38,
                "track": 0.36,
                "acq_date": "2026-10-01",
                "acq_time": "0845",
                "satellite": "Suomi-NPP",
                "instrument": "VIIRS",
                "confidence": "high",
                "version": "2.0NRT",
                "bright_t31": 298.4,
                "frp": 128.5,
                "daynight": "N",
                "source_type": "wildfire",
                "risk_score": 87.5,
                "risk_level": "critical",
                "is_anomaly": True,
                "cluster_id": "CL-CAL-04",
                "cluster_size": 6,
                "nearest_place": "Geysers Geothermal Field, Sonoma County, CA",
                "last_updated": "2026-10-01T09:15:00Z"
            }
        }


class HotspotsResponse(BaseModel):
    """Envelope response for hotspot query list."""
    items: List[Hotspot] = Field(..., description="List of matching hotspot records")
    total: int = Field(..., description="Total count matching filter criteria")
    page: int = Field(default=1, description="Current page index (1-based)")
    page_size: int = Field(default=50, description="Number of items per page")
    data_mode: DataMode = Field(..., description="Whether records originate from live FIRMS API or fallback demo data")
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp")

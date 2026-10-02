"""Canonical Observation Contract for ThermalIntel V2.

Represents raw provider evidence: what satellite instruments or remote sensors
physically measured. Contains NO ThermalIntel interpretation, classification,
or risk assessment.
"""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator
from .common import now_utc_iso


class Observation(BaseModel):
    """Canonical model for a single remote-sensing thermal observation.
    
    Captures provider evidence with strict provenance and explicit separation
    between detection confidence and downstream intelligence classification.
    """
    observation_id: str = Field(..., description="Unique deterministic observation identifier (e.g. 'OBS-VIIRS-SNPP-20261001-0001')")
    provider: str = Field(..., description="Remote sensing provider organization (e.g. 'NASA_FIRMS', 'COPERNICUS')")
    product: str = Field(..., description="Specific sensor product name (e.g. 'VIIRS_SNPP_NRT', 'MODIS_C61')")
    satellite: Optional[str] = Field(None, description="Spacecraft name (e.g. 'Suomi-NPP', 'NOAA-20', 'Terra', 'Aqua')")
    instrument: Optional[str] = Field(None, description="Sensor instrument payload (e.g. 'VIIRS', 'MODIS')")
    
    # Coordinates (WGS84)
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude in decimal degrees (WGS84)")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude in decimal degrees (WGS84)")
    
    # Timestamps (Explicit UTC)
    acquisition_time_utc: str = Field(..., description="ISO 8601 UTC timestamp when sensor pixel was acquired by satellite")
    ingestion_time_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when observation was ingested by ThermalIntel")
    
    # Radiometric measurements
    brightness: float = Field(..., gt=0.0, description="Primary thermal band brightness temperature in Kelvin (e.g. I-4 / Ch 21)")
    bright_t31: Optional[float] = Field(None, gt=0.0, description="Secondary thermal band brightness temperature in Kelvin (e.g. I-5 / Ch 31)")
    frp: float = Field(..., ge=0.0, description="Fire Radiative Power in Megawatts (MW)")
    
    # Pixel geometry
    scan: Optional[float] = Field(None, ge=0.0, description="Along-scan pixel resolution dimension in km")
    track: Optional[float] = Field(None, ge=0.0, description="Along-track pixel resolution dimension in km")
    daynight: str = Field(..., pattern="^[DN]$", description="'D' for daytime acquisition, 'N' for nighttime")
    
    # Provider detection confidence (Strictly separated from ML classification confidence)
    detection_confidence: str = Field(
        ...,
        description="Provider-native detection confidence category or percentage (e.g. 'low', 'nominal', 'high', '85%'). NOT AI classification confidence."
    )
    
    # Provider-native unmapped attributes & raw lineage
    source_attributes: Dict[str, Any] = Field(
        default_factory=dict,
        description="Raw provider attributes preserved without loss for auditability"
    )
    raw_payload_id: Optional[str] = Field(
        None,
        description="Identifier of the raw provider response payload in raw storage"
    )
    schema_version: str = Field(default="2.0", description="Contract schema version")

    @field_validator("daynight")
    @classmethod
    def validate_daynight(cls, v: str) -> str:
        upper = v.upper()
        if upper not in ("D", "N"):
            raise ValueError("daynight must be 'D' or 'N'")
        return upper

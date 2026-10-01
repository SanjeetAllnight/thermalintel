"""Shared types and enumerations for ThermalIntel schemas."""

from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class DataMode(str, Enum):
    LIVE = "live"
    DEMO = "demo"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceType(str, Enum):
    WILDFIRE = "wildfire"
    INDUSTRIAL = "industrial"
    AGRICULTURAL = "agricultural"
    URBAN = "urban"
    VOLCANIC = "volcanic"
    PRESCRIBED_BURN = "prescribed_burn"
    UNKNOWN = "unknown"


class AlertSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class RiskFactor(BaseModel):
    factor: str = Field(..., description="Short title of the risk factor")
    weight: float = Field(..., ge=0.0, le=1.0, description="Relative weight in score calculation (0 to 1)")
    impact: RiskLevel = Field(..., description="Categorical impact level")
    description: str = Field(..., description="Explainable description of why this factor increases/decreases risk")


class Coordinates(BaseModel):
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)


class HealthResponse(BaseModel):
    status: str = Field(default="ok", description="Overall system health: ok, degraded, or error")
    version: str = Field(default="0.1.0", description="API version")
    data_mode: DataMode = Field(..., description="Current data mode: live or demo")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
    services: Dict[str, str] = Field(
        default_factory=lambda: {
            "database": "connected",
            "firms_api": "ready",
            "intelligence_engine": "online",
        },
        description="Health status of downstream subsystems"
    )

"""Alert schemas for critical thermal anomaly notifications."""

from typing import List, Optional
from pydantic import BaseModel, Field
from .common import AlertSeverity, RiskLevel


class Alert(BaseModel):
    """Notification alert object representing a high-risk or anomalous thermal event."""
    id: str = Field(..., description="Unique alert identifier (e.g. ALT-20261001-001)")
    hotspot_id: str = Field(..., description="Reference ID to the associated Hotspot")
    severity: AlertSeverity = Field(..., description="Severity classification: info, warning, critical")
    title: str = Field(..., description="Concise alert headline")
    message: str = Field(..., description="Detailed alert summary including primary trigger reasons")
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Risk severity index at time of alert")
    location_name: str = Field(..., description="Geographic locality label")
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp when alert was generated")
    is_acknowledged: bool = Field(default=False, description="Whether alert has been acknowledged by operator")
    recommended_action: str = Field(..., description="Immediate operational mitigation recommendation")
    tags: List[str] = Field(default_factory=list, description="Categorical tags (e.g. ['rapid_spread', 'settlement_proximity'])")


class AlertsResponse(BaseModel):
    """Response envelope for GET /api/alerts."""
    items: List[Alert] = Field(..., description="List of active/recent alerts")
    total: int = Field(..., description="Total alert count")
    unread_count: int = Field(..., description="Count of unacknowledged alerts")
    generated_at: str = Field(..., description="ISO 8601 UTC timestamp")

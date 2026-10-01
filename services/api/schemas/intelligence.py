"""Intelligence and ML evaluation schemas for ThermalIntel."""

from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from .common import RiskLevel, SourceType, RiskFactor


class ClassificationResult(BaseModel):
    """Thermal source classification result and confidence breakdown."""
    predicted_source: SourceType = Field(..., description="Top predicted thermal anomaly source")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence probability for top prediction (0 to 1)")
    probabilities: Dict[str, float] = Field(
        ...,
        description="Class probability distribution across all supported source types"
    )
    feature_importance: Optional[Dict[str, float]] = Field(
        default=None,
        description="Key features driving the classification decision"
    )


class AnomalyResult(BaseModel):
    """Statistical and isolation forest anomaly detection metrics."""
    is_anomaly: bool = Field(..., description="True if anomaly score exceeds operational threshold")
    anomaly_score: float = Field(..., ge=0.0, le=1.0, description="Normalized anomaly deviation index (0 to 1)")
    baseline_deviation: float = Field(
        ...,
        description="Standard deviations away from 30-day baseline FRP/temperature for this region"
    )
    anomaly_rationale: str = Field(..., description="Concise explanation of why this hotspot is statistically anomalous")


class RiskAssessment(BaseModel):
    """Composite risk score and explainable attribution factors."""
    risk_score: float = Field(..., ge=0.0, le=100.0, description="Composite risk index from 0 to 100")
    risk_level: RiskLevel = Field(..., description="Categorical rating: low, medium, high, critical")
    frp_component: float = Field(..., ge=0.0, le=100.0, description="Sub-score derived from Fire Radiative Power")
    weather_component: float = Field(..., ge=0.0, le=100.0, description="Sub-score derived from wind, temp, humidity")
    proximity_component: float = Field(..., ge=0.0, le=100.0, description="Sub-score derived from human/critical asset distance")
    historical_component: float = Field(..., ge=0.0, le=100.0, description="Sub-score derived from site recurrence patterns")
    explainable_factors: List[RiskFactor] = Field(
        ...,
        description="Ranked explanatory factors justifying the composite risk score"
    )
    recommended_action: str = Field(
        ...,
        description="Actionable operational recommendation for responders and analysts"
    )


class IntelligenceResult(BaseModel):
    """Unified intelligence payload returned by the ML subsystem."""
    hotspot_id: str = Field(..., description="ID of the analyzed hotspot")
    classification: ClassificationResult = Field(..., description="Source classification results")
    anomaly: AnomalyResult = Field(..., description="Anomaly detection evaluation")
    risk: RiskAssessment = Field(..., description="Comprehensive risk assessment")
    model_version: str = Field(default="v1.0-rf-heuristic", description="Active ML model / rule-engine identifier")
    evaluated_at: str = Field(..., description="ISO 8601 UTC timestamp of intelligence generation")

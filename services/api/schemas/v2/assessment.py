"""Canonical Assessment Contract for ThermalIntel V2.

Represents reproducible machine learning and intelligence inference results.
Strictly distinguishes:
1. Detection confidence (provider signal quality)
2. Classification confidence (ML model probability)
3. Data completeness / quality (context availability)
4. Anomaly score (deviation index)
5. Risk score (composite consequence index)
"""

from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from .common import SourceType, RiskLevel, RiskFactor, now_utc_iso


class ClassificationAssessment(BaseModel):
    """Source classification inference result."""
    predicted_source: SourceType = Field(..., description="Top predicted thermal source category")
    classification_confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="ML posterior probability for top predicted source (0 to 1). NOT provider detection confidence."
    )
    probabilities: Dict[str, float] = Field(
        ...,
        description="Complete class probability distribution across all supported source categories"
    )
    feature_importance: Optional[Dict[str, float]] = Field(
        None,
        description="Key normalized feature weights influencing the classification inference"
    )


class AnomalyAssessment(BaseModel):
    """Statistical and Isolation Forest anomaly inference."""
    is_anomaly: bool = Field(..., description="True if anomaly score crosses operational statistical threshold")
    anomaly_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Normalized anomaly score (0: typical, 1: extreme outlier). NOT risk score."
    )
    baseline_deviation_sigma: float = Field(
        ...,
        description="Number of standard deviations away from 30-day regional baseline FRP/temperature"
    )
    anomaly_rationale: str = Field(..., description="Concise explanation justifying statistical anomaly status")


class RiskAssessmentResult(BaseModel):
    """Multi-factor explainable risk synthesis."""
    risk_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Composite operational risk score from 0.0 to 100.0. NOT anomaly or classification confidence."
    )
    severity: RiskLevel = Field(..., description="Categorical rating: low, medium, high, critical")
    frp_component: float = Field(..., ge=0.0, le=100.0, description="Risk sub-score derived from Fire Radiative Power")
    weather_component: float = Field(..., ge=0.0, le=100.0, description="Risk sub-score derived from ambient weather danger")
    proximity_component: float = Field(..., ge=0.0, le=100.0, description="Risk sub-score derived from asset/community proximity")
    historical_component: float = Field(..., ge=0.0, le=100.0, description="Risk sub-score derived from site recurrence profile")
    factors: List[RiskFactor] = Field(..., description="Ranked list of explainable risk drivers with weights and impact")
    recommended_action: str = Field(..., description="Operational responder recommendation")


class DataQualityAssessment(BaseModel):
    """Uncertainty and contextual completeness metrics."""
    completeness_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Proportion of expected enrichment domains successfully integrated (0 to 1)"
    )
    uncertainty_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Overall model epistemic and aleatoric uncertainty (0: certain, 1: highly uncertain)"
    )
    missing_sources: List[str] = Field(
        default_factory=list,
        description="Names of providers or context modules that were degraded or unavailable during evaluation"
    )


class AssessmentMethodology(BaseModel):
    """Provenance and reproducibility contract for intelligence decisions.
    
    Guarantees every assessment can be reproduced or audited historically.
    """
    method: str = Field(..., description="Method name (e.g. 'RandomForest+IsolationForest+MultiFactorRisk')")
    algorithm_version: str = Field(..., description="Semantic algorithm release version (e.g. 'v2.0.0-rf-heuristic')")
    input_hash: str = Field(..., description="SHA-256 hash of input observation + enrichment vectors used for inference")
    as_of_utc: str = Field(..., description="Logical evaluation timestamp (distinct from creation time for historical replays)")


class Assessment(BaseModel):
    """Canonical Assessment Contract uniting all intelligence inference subsystems."""
    assessment_id: str = Field(..., description="Unique deterministic assessment identifier (e.g. 'ASM-20261001-0001')")
    target_id: str = Field(..., description="Observation ID or Incident ID evaluated")
    target_type: str = Field(..., description="'observation' or 'incident'")
    classification: ClassificationAssessment = Field(..., description="Source classification results")
    anomaly: AnomalyAssessment = Field(..., description="Anomaly detection evaluation")
    risk: RiskAssessmentResult = Field(..., description="Explainable composite risk assessment")
    data_quality: DataQualityAssessment = Field(..., description="Data completeness and uncertainty metrics")
    methodology: AssessmentMethodology = Field(..., description="Audit and reproducibility metadata")
    created_at_utc: str = Field(default_factory=now_utc_iso, description="ISO 8601 UTC timestamp when assessment was stored")

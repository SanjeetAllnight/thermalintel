"""Composite Risk & Severity Scoring Subsystem.

Redesigned for truthful, reproducible, evidence-based operational intelligence.

Core Philosophy:
The Composite Risk Score is an OPERATIONAL HAZARD HEURISTIC (0.0 to 100.0), NOT a
calibrated physical probability of damage or economic loss. It provides emergency
dispatchers and command analysts with an immediate, consistent priority ranking.

Conceptual Decomposition:
1. HAZARD INTENSITY / LIKELIHOOD:
   - Radiometric Fire Radiative Power (FRP) and brightness intensity (Weight: 0.35)
   - Atmospheric Fire Weather: wind vectors, relative humidity, temperature (Weight: 0.25)
   - Statistical Baseline Anomaly Surge: relative departure from regional norm (Weight: 0.10)
2. EXPOSURE & SPATIAL VULNERABILITY:
   - Geospatial Proximity: distance to populated settlements and critical infrastructure (Weight: 0.20)
3. SITE CONTEXT & TEMPORAL PERSISTENCE:
   - Historical Recurrence: differentiates stationary industrial flare stacks from uncontained wildland fires (Weight: 0.10)

Missing Data Handling:
- Telemetry domains that are unavailable (weather, geospatial, historical) have their weights
  dynamically rebalanced rather than fabricating observed values.
- Missing context penalizes data quality completeness and elevates uncertainty.
"""

import math
from typing import Dict, List, Optional
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.intelligence import RiskAssessment, AnomalyResult
from services.api.schemas.v2.assessment import RiskAssessmentResult
from services.api.schemas.v2.common import RiskFactor as V2RiskFactor, RiskLevel as V2RiskLevel
from services.intelligence.config import (
    score_to_risk_level,
    DEFAULT_WEIGHT_FRP,
    DEFAULT_WEIGHT_WEATHER,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_ANOMALY,
    DEFAULT_WEIGHT_HISTORY,
    RECURRENT_FLARE_SUPPRESSION_COUNT,
)
from services.intelligence.features import FeatureVector
from services.intelligence.explain import ExplanationGenerator
from services.intelligence.thresholds import (
    RECURRENT_MIN_PASSES_30D,
    RISK_SCORE_MIN,
    RISK_SCORE_MAX,
)


class RiskAssessor:
    """Calculates multi-criteria composite risk scores and synthesizes explainable factors."""

    def __init__(
        self,
        weight_frp: float = DEFAULT_WEIGHT_FRP,
        weight_weather: float = DEFAULT_WEIGHT_WEATHER,
        weight_proximity: float = DEFAULT_WEIGHT_PROXIMITY,
        weight_anomaly: float = DEFAULT_WEIGHT_ANOMALY,
        weight_history: float = DEFAULT_WEIGHT_HISTORY,
    ):
        self.weight_frp = float(weight_frp)
        self.weight_weather = float(weight_weather)
        self.weight_proximity = float(weight_proximity)
        self.weight_anomaly = float(weight_anomaly)
        self.weight_history = float(weight_history)

    def assess_risk(
        self,
        features: FeatureVector,
        source_type: SourceType,
        anomaly_result: AnomalyResult,
    ) -> RiskAssessment:
        """Compute composite 0-100 risk score and return backward-compatible RiskAssessment."""
        (
            composite,
            risk_level,
            frp_comp,
            weather_comp,
            prox_comp,
            hist_comp,
            factors,
            rec,
        ) = self._compute_components(features, source_type, anomaly_result)

        return RiskAssessment(
            risk_score=composite,
            risk_level=risk_level,
            frp_component=round(frp_comp, 1),
            weather_component=round(weather_comp, 1),
            proximity_component=round(prox_comp, 1),
            historical_component=round(hist_comp, 1),
            explainable_factors=factors,
            recommended_action=rec,
        )

    def assess_risk_v2(
        self,
        features: FeatureVector,
        source_type: SourceType,
        anomaly_result: AnomalyResult,
    ) -> RiskAssessmentResult:
        """Compute composite 0-100 risk score and return canonical V2 RiskAssessmentResult."""
        (
            composite,
            risk_level,
            frp_comp,
            weather_comp,
            prox_comp,
            hist_comp,
            factors,
            rec,
        ) = self._compute_components(features, source_type, anomaly_result)

        v2_factors = [
            V2RiskFactor(
                factor=f.factor,
                weight=f.weight,
                impact=V2RiskLevel(f.impact.value if hasattr(f.impact, "value") else str(f.impact)),
                description=f.description,
            )
            for f in factors
        ]
        v2_severity = V2RiskLevel(risk_level.value if hasattr(risk_level, "value") else str(risk_level))

        return RiskAssessmentResult(
            risk_score=composite,
            severity=v2_severity,
            frp_component=round(frp_comp, 1),
            weather_component=round(weather_comp, 1),
            proximity_component=round(prox_comp, 1),
            historical_component=round(hist_comp, 1),
            factors=v2_factors,
            recommended_action=rec,
        )

    def _compute_components(
        self,
        features: FeatureVector,
        source_type: SourceType,
        anomaly_result: AnomalyResult,
    ):
        """Internal deterministic risk synthesis engine."""
        # 1. FRP Component (0 to 100)
        frp_comp = _safe_float(features.frp_norm) * 100.0

        # 2. Weather Component (0 to 100)
        if features.has_weather and features.fire_weather_score is not None:
            weather_comp = _safe_float(features.fire_weather_score) * 100.0
        else:
            weather_comp = 25.0  # Schema placeholder; weight is set to 0.0 if weather is unavailable

        # 3. Proximity Component (0 to 100)
        if features.has_geospatial:
            settlement_score = _safe_float(features.settlement_proximity_score) * 100.0
            infra_score = _safe_float(features.infra_proximity_score) * 100.0
            protected_bonus = 10.0 if features.is_protected_area else 0.0
            slope_bonus = _safe_float(features.slope_factor) * 15.0

            prox_comp = (
                (max(settlement_score, infra_score) * 0.70)
                + (min(settlement_score, infra_score) * 0.20)
                + protected_bonus
                + slope_bonus
            )
            prox_comp = min(100.0, max(0.0, prox_comp))
        else:
            prox_comp = 20.0  # Schema placeholder; weight is set to 0.0 if geospatial is unavailable

        # 4. Historical Component (0 to 100)
        # Deliberate differentiation:
        # Stationary industrial flare: High recurrence indicates routine infrastructure operations -> LOWER spread risk.
        # Active vegetation fire: High recurrence indicates persistent, multi-day uncontained burn -> HIGHER operational risk.
        prior_30d = features.prior_detections_30d
        is_recurrent = features.is_recurrent_site or (prior_30d is not None and prior_30d >= RECURRENT_MIN_PASSES_30D)

        if is_recurrent:
            if features.is_industrial_land_cover or features.industrial_proximity_score >= 0.50 or source_type == SourceType.INDUSTRIAL:
                # Contained industrial facility with continuous flaring
                hist_comp = 15.0
            else:
                # Persistent multi-day wildland fire resisting containment
                passes = prior_30d or RECURRENT_MIN_PASSES_30D
                hist_comp = min(85.0, 45.0 + (passes * 3.0))
        elif prior_30d is not None and prior_30d > 0:
            hist_comp = min(80.0, 30.0 + (prior_30d * 8.0))
        elif prior_30d == 0:
            hist_comp = 35.0  # Sudden new ignition
        else:
            hist_comp = 30.0  # History absent / neutral baseline

        # 5. Anomaly Component (0 to 100)
        anomaly_score = _safe_float(anomaly_result.anomaly_score)
        anomaly_comp = anomaly_score * 100.0

        # 6. Dynamic Weight Normalization based on actually available evidence
        active_weights: Dict[str, float] = {
            "frp": self.weight_frp,
            "weather": self.weight_weather if features.has_weather else 0.0,
            "proximity": self.weight_proximity if features.has_geospatial else 0.0,
            "anomaly": self.weight_anomaly,
            "history": self.weight_history if features.has_history else 0.0,
        }
        total_weight = sum(active_weights.values())
        if total_weight <= 0.0:
            total_weight = 1.0
        norm_weights = {k: v / total_weight for k, v in active_weights.items()}

        # 7. Composite score calculation
        composite = (
            (frp_comp * norm_weights["frp"])
            + (weather_comp * norm_weights["weather"])
            + (prox_comp * norm_weights["proximity"])
            + (anomaly_comp * norm_weights["anomaly"])
            + (hist_comp * norm_weights["history"])
        )

        # Satellite confidence scaling (+/- 5 points based on satellite confidence)
        confidence_delta = (_safe_float(features.satellite_confidence) - 0.65) * 8.0
        composite += confidence_delta

        # Source-specific operational modulation
        if source_type == SourceType.PRESCRIBED_BURN:
            # Prescribed burns operate under active perimeter containment plans
            composite *= 0.75
        elif source_type == SourceType.AGRICULTURAL:
            composite *= 0.85

        # Clamp strictly to [0.0, 100.0]
        composite = round(min(RISK_SCORE_MAX, max(RISK_SCORE_MIN, _safe_float(composite))), 1)
        risk_level = score_to_risk_level(composite)

        # Clamp individual components strictly to [0.0, 100.0]
        frp_comp_clamped = min(100.0, max(0.0, frp_comp))
        weather_comp_clamped = min(100.0, max(0.0, weather_comp))
        prox_comp_clamped = min(100.0, max(0.0, prox_comp))
        hist_comp_clamped = min(100.0, max(0.0, hist_comp))

        # 8. Generate explainable factors and operational recommendation
        factors = ExplanationGenerator.generate_factors(
            features=features,
            risk_score=composite,
            frp_comp=frp_comp_clamped,
            weather_comp=weather_comp_clamped,
            prox_comp=prox_comp_clamped,
            hist_comp=hist_comp_clamped,
            anomaly_score=anomaly_score,
            is_anomaly=anomaly_result.is_anomaly,
        )

        rec = ExplanationGenerator.generate_recommendation(
            risk_score=composite,
            predicted_source=source_type,
        )

        return (
            composite,
            risk_level,
            frp_comp_clamped,
            weather_comp_clamped,
            prox_comp_clamped,
            hist_comp_clamped,
            factors,
            rec,
        )


def _safe_float(val: Optional[float], default: float = 0.0) -> float:
    """Sanitize float against NaN, infinity, or None."""
    if val is None:
        return default
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (ValueError, TypeError):
        return default

"""Composite Risk & Severity Scoring Subsystem.

Combines:
- Radiometric intensity (FRP & Brightness)
- Atmospheric fire weather (Wind, Humidity, Temperature)
- Geospatial exposure (Proximity to human settlements & critical infrastructure)
- Statistical anomaly deviation
- Historical recurrence & site persistence

Produces a normalized 0-100 composite index and explainable attribution factors.
"""

from typing import Optional, Dict, Any, List
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.intelligence import RiskAssessment, AnomalyResult
from services.intelligence.config import (
    score_to_risk_level,
    DEFAULT_WEIGHT_FRP,
    DEFAULT_WEIGHT_WEATHER,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_ANOMALY,
    DEFAULT_WEIGHT_HISTORY,
)
from services.intelligence.features import FeatureVector
from services.intelligence.explain import ExplanationGenerator


class RiskAssessor:
    """Calculates multi-criteria composite risk score and synthesizes explainable factors."""

    def __init__(
        self,
        weight_frp: float = DEFAULT_WEIGHT_FRP,
        weight_weather: float = DEFAULT_WEIGHT_WEATHER,
        weight_proximity: float = DEFAULT_WEIGHT_PROXIMITY,
        weight_anomaly: float = DEFAULT_WEIGHT_ANOMALY,
        weight_history: float = DEFAULT_WEIGHT_HISTORY,
    ):
        self.weight_frp = weight_frp
        self.weight_weather = weight_weather
        self.weight_proximity = weight_proximity
        self.weight_anomaly = weight_anomaly
        self.weight_history = weight_history

    def assess_risk(
        self,
        features: FeatureVector,
        source_type: SourceType,
        anomaly_result: AnomalyResult,
    ) -> RiskAssessment:
        """Compute composite 0-100 risk score, categorical severity level,

        and explainable attribution factors.
        """
        # 1. FRP Component (0 to 100)
        frp_comp = features.frp_norm * 100.0

        # 2. Weather Component (0 to 100)
        if features.has_weather and features.fire_weather_score is not None:
            weather_comp = features.fire_weather_score * 100.0
        else:
            weather_comp = 25.0  # Neutral baseline when telemetry is absent

        # 3. Proximity Component (0 to 100)
        if features.has_geospatial:
            settlement_score = features.settlement_proximity_score * 100.0
            infra_score = features.infra_proximity_score * 100.0
            protected_bonus = 10.0 if features.is_protected_area else 0.0
            slope_bonus = features.slope_factor * 15.0

            prox_comp = (
                (max(settlement_score, infra_score) * 0.70)
                + (min(settlement_score, infra_score) * 0.20)
                + protected_bonus
                + slope_bonus
            )
            prox_comp = min(100.0, max(0.0, prox_comp))
        else:
            prox_comp = 20.0  # Neutral baseline when spatial GIS context is absent

        # 4. Historical Component (0 to 100)
        if features.is_recurrent_site or (features.prior_detections_30d and features.prior_detections_30d >= 10):
            # Controlled or recurring stationary emitters have low spread/growth risk
            hist_comp = 15.0
        elif features.prior_detections_30d is not None and features.prior_detections_30d > 0:
            hist_comp = min(80.0, 30.0 + (features.prior_detections_30d * 8.0))
        else:
            hist_comp = 35.0  # New sudden detection baseline

        # 5. Anomaly Component (0 to 100)
        anomaly_comp = anomaly_result.anomaly_score * 100.0

        # 6. Dynamic Weight Normalization based on available evidence
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
        confidence_delta = (features.satellite_confidence - 0.65) * 8.0
        composite += confidence_delta

        # Source-specific risk modulation (classification informs mechanism, does not dictate score)
        if source_type == SourceType.PRESCRIBED_BURN:
            # Prescribed burn has intentional containment mitigations
            composite *= 0.75
        elif source_type == SourceType.AGRICULTURAL:
            composite *= 0.85

        # Clamp strictly to [0.0, 100.0]
        composite = round(min(100.0, max(0.0, composite)), 1)
        risk_level = score_to_risk_level(composite)

        # 8. Generate explainable factors and operational recommendation
        factors = ExplanationGenerator.generate_factors(
            features=features,
            risk_score=composite,
            frp_comp=frp_comp,
            weather_comp=weather_comp,
            prox_comp=prox_comp,
            hist_comp=hist_comp,
            anomaly_score=anomaly_result.anomaly_score,
            is_anomaly=anomaly_result.is_anomaly,
        )

        rec = ExplanationGenerator.generate_recommendation(
            risk_score=composite,
            predicted_source=source_type,
        )

        return RiskAssessment(
            risk_score=composite,
            risk_level=risk_level,
            frp_component=round(float(min(100.0, max(0.0, frp_comp))), 1),
            weather_component=round(float(min(100.0, max(0.0, weather_comp))), 1),
            proximity_component=round(float(min(100.0, max(0.0, prox_comp))), 1),
            historical_component=round(float(min(100.0, max(0.0, hist_comp))), 1),
            explainable_factors=factors,
            recommended_action=rec,
        )

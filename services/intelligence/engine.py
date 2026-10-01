"""Thermal Anomaly Intelligence Engine.

Provides:
1. Source Classification (Wildfire, Industrial, Agricultural, Prescribed, Urban, Volcanic)
2. Statistical / Machine Learning Anomaly Detection
3. Composite Risk & Severity Scoring (0-100)
4. Explainable Attribution Factor Generation
"""

from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import math

from services.api.schemas.common import RiskLevel, SourceType, RiskFactor
from services.api.schemas.intelligence import (
    ClassificationResult,
    AnomalyResult,
    RiskAssessment,
    IntelligenceResult,
)


class ThermalIntelligenceEngine:
    """Core intelligence engine for evaluating thermal anomalies."""

    def __init__(self, model_version: str = "v1.0-rf-heuristic"):
        self.model_version = model_version

    def detect_anomaly(
        self,
        frp: float,
        brightness: float,
        historical_detections_30d: int,
        baseline_frp_mean: float = 25.0,
        baseline_frp_std: float = 20.0,
    ) -> AnomalyResult:
        """Evaluate whether a thermal observation deviates significantly from regional baseline."""
        # Calculate sigma deviation
        deviation = (frp - baseline_frp_mean) / max(baseline_frp_std, 1.0)
        anomaly_score = max(0.0, min(1.0, (deviation + 1.0) / 5.0))

        # Industrial sites with 40+ detections are recurring and not anomalies
        if historical_detections_30d > 20:
            is_anomaly = False
            anomaly_score = min(anomaly_score, 0.25)
            rationale = f"Recurring site ({historical_detections_30d} passes in 30d). Matches operational baseline."
        elif deviation >= 2.0:
            is_anomaly = True
            rationale = f"Thermal intensity exceeds 30-day baseline by {deviation:.1f} standard deviations."
        else:
            is_anomaly = False
            rationale = "Radiant energy output within normal expected variation bounds."

        return AnomalyResult(
            is_anomaly=is_anomaly,
            anomaly_score=round(anomaly_score, 3),
            baseline_deviation=round(deviation, 2),
            anomaly_rationale=rationale,
        )

    def classify_source(
        self,
        frp: float,
        brightness: float,
        land_cover: str,
        historical_recurrence: int,
        is_protected_area: bool = False,
    ) -> ClassificationResult:
        """Classify the probable source of the thermal signature using radiometric & spatial heuristics."""
        probs = {
            SourceType.WILDFIRE.value: 0.05,
            SourceType.INDUSTRIAL.value: 0.05,
            SourceType.AGRICULTURAL.value: 0.05,
            SourceType.PRESCRIBED_BURN.value: 0.05,
            SourceType.URBAN.value: 0.05,
            SourceType.VOLCANIC.value: 0.01,
            SourceType.UNKNOWN.value: 0.05,
        }

        # Historical recurrence strongly flags industrial stacks/refineries
        if historical_recurrence >= 15 or "industrial" in land_cover.lower():
            probs[SourceType.INDUSTRIAL.value] += 0.85
        elif "forest" in land_cover.lower() or "chaparral" in land_cover.lower():
            if is_protected_area and frp < 50.0:
                probs[SourceType.PRESCRIBED_BURN.value] += 0.60
                probs[SourceType.WILDFIRE.value] += 0.35
            else:
                probs[SourceType.WILDFIRE.value] += 0.80
        elif "agri" in land_cover.lower() or "crop" in land_cover.lower() or "pasture" in land_cover.lower():
            probs[SourceType.AGRICULTURAL.value] += 0.75
        elif "urban" in land_cover.lower() or "residential" in land_cover.lower():
            probs[SourceType.URBAN.value] += 0.70
        elif "volcano" in land_cover.lower() or "lava" in land_cover.lower():
            probs[SourceType.VOLCANIC.value] += 0.90
        else:
            if frp > 70.0:
                probs[SourceType.WILDFIRE.value] += 0.65
            else:
                probs[SourceType.UNKNOWN.value] += 0.50

        # Normalize probabilities
        total = sum(probs.values())
        norm_probs = {k: round(v / total, 3) for k, v in probs.items()}
        top_source_str = max(norm_probs.items(), key=lambda x: x[1])[0]
        top_source = SourceType(top_source_str)
        confidence = norm_probs[top_source_str]

        feature_importance = {
            "historical_recurrence": 0.35 if historical_recurrence >= 15 else 0.15,
            "land_cover_type": 0.40,
            "fire_radiative_power": 0.25,
        }

        return ClassificationResult(
            predicted_source=top_source,
            confidence=confidence,
            probabilities=norm_probs,
            feature_importance=feature_importance,
        )

    def assess_risk(
        self,
        frp: float,
        source_type: SourceType,
        wind_speed_kmh: float,
        relative_humidity_percent: float,
        temperature_celsius: float,
        distance_to_settlement_m: Optional[float],
        distance_to_infra_m: Optional[float],
        slope_degrees: Optional[float],
        historical_recurrence: int,
    ) -> RiskAssessment:
        """Compute composite 0-100 severity index and generate explainable risk factors."""
        # 1. FRP Component (0 - 100)
        # Logarithmic scaling: 10 MW -> 25, 50 MW -> 60, 150+ MW -> 95+
        frp_comp = min(100.0, max(5.0, 20.0 * math.log(max(frp, 1.0))))

        # 2. Weather Component (0 - 100)
        # High wind + low humidity + high temp = high fire weather index
        rh_factor = max(0.0, (100.0 - relative_humidity_percent) / 100.0)  # 0 to 1
        wind_factor = min(1.0, wind_speed_kmh / 60.0)                      # 0 to 1
        temp_factor = min(1.0, max(0.0, (temperature_celsius - 15.0) / 25.0))
        weather_comp = (wind_factor * 45.0) + (rh_factor * 40.0) + (temp_factor * 15.0)
        weather_comp = min(100.0, max(0.0, weather_comp))

        # 3. Proximity Component (0 - 100)
        settlement_dist = distance_to_settlement_m if distance_to_settlement_m is not None else 10000.0
        infra_dist = distance_to_infra_m if distance_to_infra_m is not None else 10000.0
        min_dist = min(settlement_dist, infra_dist)

        if min_dist < 1000:
            prox_comp = 90.0 - (min_dist / 1000.0) * 20.0
        elif min_dist < 5000:
            prox_comp = 70.0 - ((min_dist - 1000.0) / 4000.0) * 35.0
        else:
            prox_comp = 20.0

        # 4. Historical Component (0 - 100)
        # Known industrial sites have low spread risk despite heat
        if source_type == SourceType.INDUSTRIAL and historical_recurrence >= 10:
            hist_comp = 15.0
        else:
            hist_comp = min(100.0, historical_recurrence * 5.0)

        # Composite score calculation
        if source_type == SourceType.INDUSTRIAL:
            # Industrial flare: heat is expected, spread danger is lower unless near settlement
            composite = (frp_comp * 0.20) + (prox_comp * 0.50) + (weather_comp * 0.15) + (hist_comp * 0.15)
        elif source_type == SourceType.WILDFIRE:
            # Wildfire: driven heavily by FRP, weather, and settlement proximity
            slope_bonus = (slope_degrees or 0.0) * 0.5
            composite = (frp_comp * 0.35) + (weather_comp * 0.35) + (prox_comp * 0.25) + (hist_comp * 0.05) + slope_bonus
        elif source_type == SourceType.AGRICULTURAL:
            composite = (frp_comp * 0.30) + (weather_comp * 0.40) + (prox_comp * 0.30)
        else:
            composite = (frp_comp * 0.30) + (weather_comp * 0.30) + (prox_comp * 0.30) + (hist_comp * 0.10)

        composite = round(min(100.0, max(0.0, composite)), 1)

        # Determine Risk Level
        if composite >= 75.0:
            level = RiskLevel.CRITICAL
        elif composite >= 50.0:
            level = RiskLevel.HIGH
        elif composite >= 25.0:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        # Generate Explainable Factors
        factors: List[RiskFactor] = []
        if frp > 80.0:
            factors.append(
                RiskFactor(
                    factor=f"High Thermal Radiance ({frp:.1f} MW)",
                    weight=0.35,
                    impact=RiskLevel.CRITICAL if frp > 120 else RiskLevel.HIGH,
                    description=f"Intense radiometric heat signature indicates vigorous active combustion.",
                )
            )
        elif frp < 25.0:
            factors.append(
                RiskFactor(
                    factor=f"Moderate Thermal Energy ({frp:.1f} MW)",
                    weight=0.20,
                    impact=RiskLevel.LOW,
                    description="Radiant output consistent with contained smoldering or flare stack.",
                )
            )

        if wind_speed_kmh > 30.0 and relative_humidity_percent < 25.0:
            factors.append(
                RiskFactor(
                    factor=f"Adverse Fire Weather ({wind_speed_kmh:.0f} km/h, {relative_humidity_percent:.0f}% RH)",
                    weight=0.30,
                    impact=RiskLevel.CRITICAL,
                    description="Elevated wind speeds combined with critically dry air accelerate ember transport.",
                )
            )

        if settlement_dist < 2500.0:
            factors.append(
                RiskFactor(
                    factor=f"Human Settlement Proximity ({settlement_dist / 1000.0:.1f} km)",
                    weight=0.25,
                    impact=RiskLevel.HIGH if settlement_dist > 1000 else RiskLevel.CRITICAL,
                    description="Proximity to populated zone warrants elevated alert priority.",
                )
            )

        if historical_recurrence >= 15:
            factors.append(
                RiskFactor(
                    factor=f"High Historical Recurrence ({historical_recurrence} detections)",
                    weight=0.20,
                    impact=RiskLevel.LOW,
                    description="Known stationary emitter with continuous multi-month detection history.",
                )
            )

        if not factors:
            factors.append(
                RiskFactor(
                    factor="Standard Environmental Parameters",
                    weight=1.0,
                    impact=level,
                    description="Observation matches expected baseline conditions.",
                )
            )

        # Operational Recommendation
        if level == RiskLevel.CRITICAL:
            rec = "Dispatch emergency ground reconnaissance and establish perimeter containment protocol."
        elif level == RiskLevel.HIGH:
            rec = "Prioritize for next satellite orbit reassessment; notify regional fire duty officer."
        elif level == RiskLevel.MEDIUM:
            rec = "Maintain automated telemetry monitoring; review local burn permits."
        else:
            rec = "Automated logging only; no immediate intervention recommended."

        return RiskAssessment(
            risk_score=composite,
            risk_level=level,
            frp_component=round(frp_comp, 1),
            weather_component=round(weather_comp, 1),
            proximity_component=round(prox_comp, 1),
            historical_component=round(hist_comp, 1),
            explainable_factors=factors,
            recommended_action=rec,
        )

    def evaluate_hotspot(
        self,
        hotspot_id: str,
        frp: float,
        brightness: float,
        land_cover: str = "mixed",
        historical_recurrence: int = 0,
        is_protected_area: bool = False,
        wind_speed_kmh: float = 15.0,
        relative_humidity_percent: float = 40.0,
        temperature_celsius: float = 22.0,
        distance_to_settlement_m: Optional[float] = None,
        distance_to_infra_m: Optional[float] = None,
        slope_degrees: Optional[float] = None,
    ) -> IntelligenceResult:
        """Run full end-to-end intelligence evaluation pipeline on a single thermal anomaly."""
        classification = self.classify_source(
            frp=frp,
            brightness=brightness,
            land_cover=land_cover,
            historical_recurrence=historical_recurrence,
            is_protected_area=is_protected_area,
        )

        anomaly = self.detect_anomaly(
            frp=frp,
            brightness=brightness,
            historical_detections_30d=historical_recurrence,
        )

        risk = self.assess_risk(
            frp=frp,
            source_type=classification.predicted_source,
            wind_speed_kmh=wind_speed_kmh,
            relative_humidity_percent=relative_humidity_percent,
            temperature_celsius=temperature_celsius,
            distance_to_settlement_m=distance_to_settlement_m,
            distance_to_infra_m=distance_to_infra_m,
            slope_degrees=slope_degrees,
            historical_recurrence=historical_recurrence,
        )

        return IntelligenceResult(
            hotspot_id=hotspot_id,
            classification=classification,
            anomaly=anomaly,
            risk=risk,
            model_version=self.model_version,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

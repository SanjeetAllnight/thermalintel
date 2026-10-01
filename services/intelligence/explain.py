"""Explainable AI Risk Factor and Operational Recommendation Generator."""

from typing import List, Optional
from services.api.schemas.common import RiskLevel, RiskFactor, SourceType
from services.intelligence.config import score_to_risk_level
from services.intelligence.features import FeatureVector


class ExplanationGenerator:
    """Generates 2 to 5 ranked, explainable RiskFactor objects and operational recommendations

    tied directly to real input signals and calibrated to the computed risk score.
    """

    @classmethod
    def generate_factors(
        cls,
        features: FeatureVector,
        risk_score: float,
        frp_comp: float,
        weather_comp: float,
        prox_comp: float,
        hist_comp: float,
        anomaly_score: float,
        is_anomaly: bool,
    ) -> List[RiskFactor]:
        """Generate ranked, explainable factors justifying the risk score."""
        risk_lvl = score_to_risk_level(risk_score)
        factors: List[RiskFactor] = []

        # 1. Thermal Radiative Power (FRP) Factor
        if features.frp >= 100.0:
            factors.append(
                RiskFactor(
                    factor=f"Extreme Fire Radiative Power ({features.frp:.1f} MW)",
                    weight=0.35,
                    impact=RiskLevel.CRITICAL,
                    description=(
                        f"Very high radiometric energy output ({features.frp:.1f} MW) indicates "
                        "vigorous, high-intensity combustion."
                    ),
                )
            )
        elif features.frp >= 40.0:
            impact = RiskLevel.HIGH if risk_score >= 50.0 else RiskLevel.MEDIUM
            factors.append(
                RiskFactor(
                    factor=f"Elevated Fire Radiative Power ({features.frp:.1f} MW)",
                    weight=0.30,
                    impact=impact,
                    description=(
                        f"Substantial thermal output ({features.frp:.1f} MW) exceeds standard "
                        "background variation."
                    ),
                )
            )
        elif features.frp >= 15.0:
            factors.append(
                RiskFactor(
                    factor=f"Moderate Thermal Energy ({features.frp:.1f} MW)",
                    weight=0.20,
                    impact=RiskLevel.LOW if risk_score < 50.0 else RiskLevel.MEDIUM,
                    description=(
                        f"Radiant heat of {features.frp:.1f} MW is consistent with a localized, "
                        "moderate thermal source."
                    ),
                )
            )
        else:
            factors.append(
                RiskFactor(
                    factor=f"Low Thermal Energy ({features.frp:.1f} MW)",
                    weight=0.15,
                    impact=RiskLevel.LOW,
                    description=(
                        f"Low radiative power ({features.frp:.1f} MW) indicates limited flame intensity "
                        "or smoldering combustion."
                    ),
                )
            )

        # 2. Weather & Atmospheric Conditions Factor
        if features.has_weather and features.fire_weather_score is not None:
            wind = features.wind_speed_kmh or 0.0
            rh = features.relative_humidity_pct or 50.0
            if wind >= 30.0 and rh <= 25.0:
                factors.append(
                    RiskFactor(
                        factor=f"Adverse Fire Weather ({wind:.0f} km/h wind, {rh:.0f}% RH)",
                        weight=0.25,
                        impact=RiskLevel.CRITICAL if wind >= 40.0 else RiskLevel.HIGH,
                        description=(
                            f"Gusty winds ({wind:.0f} km/h) coupled with critically dry air ({rh:.0f}% RH) "
                            "strongly facilitate thermal propagation and spot fires."
                        ),
                    )
                )
            elif wind >= 20.0 or rh <= 35.0:
                factors.append(
                    RiskFactor(
                        factor=f"Elevated Fire Weather ({wind:.0f} km/h wind, {rh:.0f}% RH)",
                        weight=0.20,
                        impact=RiskLevel.MEDIUM,
                        description=(
                            f"Breezy conditions ({wind:.0f} km/h) and moderate humidity ({rh:.0f}%) "
                            "present moderate potential for fire spread."
                        ),
                    )
                )
            else:
                factors.append(
                    RiskFactor(
                        factor=f"Mild Atmospheric Conditions ({wind:.0f} km/h wind, {rh:.0f}% RH)",
                        weight=0.15,
                        impact=RiskLevel.LOW,
                        description="Calm winds and sufficient relative humidity limit atmospheric fire spread risk.",
                    )
                )
        elif not features.has_weather:
            factors.append(
                RiskFactor(
                    factor="Weather Telemetry Offline",
                    weight=0.10,
                    impact=RiskLevel.LOW,
                    description="Hyperlocal weather observations unavailable; score evaluated using baseline atmospheric model.",
                )
            )

        # 3. Proximity & Asset Exposure Factor
        if features.settlement_dist_m is not None and features.settlement_dist_m <= 2500.0:
            dist_km = features.settlement_dist_m / 1000.0
            impact = RiskLevel.CRITICAL if dist_km <= 1.2 else RiskLevel.HIGH
            factors.append(
                RiskFactor(
                    factor=f"Human Settlement Proximity ({dist_km:.1f} km)",
                    weight=0.25,
                    impact=impact,
                    description=f"Thermal signature is located within {dist_km:.1f} km of populated structures or residential boundaries.",
                )
            )
        elif features.infra_dist_m is not None and features.infra_dist_m <= 1000.0:
            dist_m = features.infra_dist_m
            factors.append(
                RiskFactor(
                    factor=f"Critical Infrastructure Proximity ({dist_m:.0f} m)",
                    weight=0.20,
                    impact=RiskLevel.HIGH if dist_m <= 500 else RiskLevel.MEDIUM,
                    description=f"Thermal anomaly detected within {dist_m:.0f} meters of mapped industrial, power, or transit infrastructure.",
                )
            )
        elif features.has_geospatial and features.settlement_dist_m and features.settlement_dist_m > 10000.0:
            factors.append(
                RiskFactor(
                    factor="Remote Spatial Location",
                    weight=0.15,
                    impact=RiskLevel.LOW,
                    description="Observation is located greater than 10 km from mapped human settlements and major assets.",
                )
            )

        # 4. Statistical Anomaly & Historical Persistence Factor
        if is_anomaly and anomaly_score >= 0.65:
            factors.append(
                RiskFactor(
                    factor=f"Statistical Radiance Surge ({anomaly_score:.2f} Anomaly Score)",
                    weight=0.20,
                    impact=RiskLevel.HIGH if anomaly_score >= 0.8 else RiskLevel.MEDIUM,
                    description="Thermal intensity significantly deviates from localized historical background baselines.",
                )
            )
        elif features.is_recurrent_site or (features.prior_detections_30d and features.prior_detections_30d >= 10):
            passes = features.prior_detections_30d or 10
            factors.append(
                RiskFactor(
                    factor=f"High Historical Recurrence ({passes} passes in 30d)",
                    weight=0.20,
                    impact=RiskLevel.LOW,
                    description="Stationary thermal emitter matches established multi-week operational pattern.",
                )
            )

        # Fallback safeguard: guarantee at least 2 factors
        if len(factors) < 2:
            factors.append(
                RiskFactor(
                    factor="Baseline Operational Profile",
                    weight=0.20,
                    impact=risk_lvl,
                    description=f"Evaluation synthesized across radiometric, geospatial, and temporal baselines (Risk Level: {risk_lvl.value}).",
                )
            )

        # Sort factors by weight descending and cap at 4 top factors
        factors.sort(key=lambda f: f.weight, reverse=True)
        return factors[:4]

    @classmethod
    def generate_recommendation(
        cls,
        risk_score: float,
        predicted_source: SourceType,
    ) -> str:
        """Produce an actionable, professional operational recommendation for responders."""
        risk_lvl = score_to_risk_level(risk_score)

        if risk_lvl == RiskLevel.CRITICAL:
            if predicted_source == SourceType.WILDFIRE:
                return (
                    "CRITICAL PRIORITY: Dispatch emergency wildland aerial and ground containment units. "
                    "Issue pre-evacuation notices for populated zones within 5 km."
                )
            elif predicted_source == SourceType.INDUSTRIAL:
                return (
                    "CRITICAL PRIORITY: Alert municipal industrial hazardous materials response and facility emergency manager. "
                    "Initiate remote sensor perimeter monitoring."
                )
            else:
                return (
                    "CRITICAL PRIORITY: Immediate dispatch of field reconnaissance. Verify ignition vector and secure perimeter."
                )
        elif risk_lvl == RiskLevel.HIGH:
            if predicted_source == SourceType.WILDFIRE:
                return (
                    "HIGH PRIORITY: Alert regional fire duty officer and prioritize immediate tasking of next satellite overpass. "
                    "Prepare local suppression readiness."
                )
            elif predicted_source == SourceType.INDUSTRIAL:
                return (
                    "HIGH PRIORITY: Cross-reference facility operational permits and contact plant duty coordinator for status verification."
                )
            else:
                return "HIGH PRIORITY: Schedule tactical surveillance flyover and review local environmental sensors."
        elif risk_lvl == RiskLevel.MEDIUM:
            return (
                "ROUTINE MONITORING: Maintain automated satellite telemetry tracking. "
                "Verify active agricultural or prescribed burn permits in district ledger."
            )
        else:
            return (
                "ADVISORY LOGGING: Thermal observation consistent with baseline operations. "
                "Automated archival logging; no immediate ground intervention required."
            )

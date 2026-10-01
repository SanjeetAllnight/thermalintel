"""Thermal Source Classification subsystem.

Implements the five core intelligence classes:
1. VEGETATION_FIRE
2. POTENTIAL_INDUSTRIAL_FIRE
3. CONTROLLED_HEAT_SOURCE
4. PERSISTENT_THERMAL_SOURCE
5. UNKNOWN

Maps to and adheres to the frozen Pydantic schema: ClassificationResult.
"""

from typing import Dict, Optional, Tuple
from services.api.schemas.common import SourceType
from services.api.schemas.intelligence import ClassificationResult
from services.intelligence.config import (
    ThermalSourceClass,
    INTELLIGENCE_CLASS_TO_SOURCE_TYPE,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    DEFAULT_UNKNOWN_CONFIDENCE,
)
from services.intelligence.features import FeatureVector


class ThermalSourceClassifier:
    """Explainable hybrid classifier combining radiometric signatures, geospatial proximity,

    environmental conditions, and historical persistence.
    """

    def __init__(self, model_version: str = "v1.2-hybrid-rules"):
        self.model_version = model_version

    def classify(self, features: FeatureVector) -> ClassificationResult:
        """Classify a thermal observation and return a structured ClassificationResult."""
        # 1. Compute evidence scores for each of the 5 intelligence classes
        class_evidence = self._compute_class_evidence(features)

        # 2. Normalize evidence into calibrated probabilities
        class_probs = self._normalize_probabilities(class_evidence)

        # 3. Determine winning intelligence class and margin
        top_class_name, top_prob = max(class_probs.items(), key=lambda item: item[1])
        winning_intel_class = ThermalSourceClass(top_class_name)

        sorted_probs = sorted(class_probs.values(), reverse=True)
        margin = sorted_probs[0] - (sorted_probs[1] if len(sorted_probs) > 1 else 0.0)

        # 4. Map to frozen SourceType
        predicted_source = self._map_to_source_type(winning_intel_class, features)

        # 5. Build full probability distribution across all 7 frozen SourceTypes + 5 Intel classes
        full_probabilities = self._build_full_probabilities(class_probs, features)

        # 6. Compute calibrated confidence
        confidence = self._compute_confidence(features, top_prob, margin, winning_intel_class)

        # 7. Compute feature importance attribution
        feature_importance = self._compute_feature_importance(features, winning_intel_class)

        return ClassificationResult(
            predicted_source=predicted_source,
            confidence=round(confidence, 3),
            probabilities=full_probabilities,
            feature_importance=feature_importance,
        )

    def _compute_class_evidence(self, f: FeatureVector) -> Dict[str, float]:
        """Compute accumulated evidence for each candidate class."""
        evidence: Dict[str, float] = {
            ThermalSourceClass.VEGETATION_FIRE.value: 0.10,
            ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value: 0.10,
            ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value: 0.10,
            ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value: 0.10,
            ThermalSourceClass.UNKNOWN.value: 0.15,
        }

        # --- A. PERSISTENT_THERMAL_SOURCE ---
        # Strong indicators: high recurrence, high persistence, stable emitter
        if f.persistence_score >= 0.50 or (f.prior_detections_30d and f.prior_detections_30d >= 10):
            recurrence_boost = min(1.2, f.persistence_score * 1.5)
            evidence[ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value] += 1.0 + recurrence_boost
            # High recurrence makes unexpected industrial fire or wildfire less likely
            if f.industrial_proximity_score >= 0.50:
                evidence[ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value] += 0.80

        # --- B. POTENTIAL_INDUSTRIAL_FIRE ---
        # Strong indicators: close to industrial facility, high FRP/brightness, high confidence, unusual spike
        if f.industrial_proximity_score >= 0.40 or f.is_industrial_land_cover:
            ind_base = f.industrial_proximity_score * 1.2
            if f.frp >= 40.0 and f.satellite_confidence >= 0.70:
                # Intense thermal event near industrial complex = high risk industrial incident
                evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += ind_base + 1.2
                if f.persistence_score < 0.30:  # Sudden emergence, not routine flaring
                    evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += 0.60
            elif f.frp >= 20.0:
                evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += ind_base + 0.40

        # --- C. CONTROLLED_HEAT_SOURCE ---
        # Indicators: protected area with moderate FRP, agricultural stubble burn, low abnormality
        if f.is_protected_area and f.frp < 55.0 and f.frp >= 3.0:
            # Prescribed burn in park / managed forest
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 1.80
        elif f.is_agricultural_land_cover:
            # Agricultural burn (stubble, crop residue)
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 1.20
        elif f.industrial_proximity_score >= 0.70 and f.frp < 30.0 and f.persistence_score >= 0.30:
            # Controlled flare stack within normal thermal limits
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 0.70

        # --- D. VEGETATION_FIRE ---
        # Indicators: vegetation land cover, away from industrial, high FRP, fire weather
        if f.is_vegetation_land_cover:
            if f.is_protected_area and f.frp < 55.0:
                veg_boost = 0.35  # Protected parcel with low/moderate FRP is likely managed prescribed burn
            else:
                veg_boost = 1.0
                if f.frp >= 35.0:
                    veg_boost += 0.60
                if f.fire_weather_score and f.fire_weather_score >= 0.50:
                    veg_boost += f.fire_weather_score * 0.80
                if f.slope_factor > 0.3:
                    veg_boost += f.slope_factor * 0.40
                if f.industrial_proximity_score < 0.20:
                    veg_boost += 0.50
            evidence[ThermalSourceClass.VEGETATION_FIRE.value] += veg_boost
        elif not f.has_industrial_context and f.frp >= 60.0:
            # High FRP in unmapped region with no industrial proximity is likely wildland vegetation fire
            evidence[ThermalSourceClass.VEGETATION_FIRE.value] += 0.90

        # --- E. UNKNOWN / CONTRADICTORY / WEAK EVIDENCE ---
        # If satellite confidence is low or evidence is severely missing/conflicting
        if f.satellite_confidence < 0.45:
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.80
        if not f.has_geospatial and not f.has_history and not f.has_weather:
            # Bare minimum satellite reading with zero context
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.90
        if f.frp < 8.0 and not f.is_recurrent_site and not f.is_protected_area:
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.40

        return evidence

    @staticmethod
    def _normalize_probabilities(evidence: Dict[str, float]) -> Dict[str, float]:
        """Normalize raw scores to sum to 1.0."""
        total = sum(max(0.01, v) for v in evidence.values())
        return {k: round(max(0.01, v) / total, 4) for k, v in evidence.items()}

    def _map_to_source_type(self, intel_class: ThermalSourceClass, f: FeatureVector) -> SourceType:
        """Map winning intelligence class to frozen SourceType enum."""
        if intel_class == ThermalSourceClass.VEGETATION_FIRE:
            return SourceType.WILDFIRE
        elif intel_class == ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE:
            return SourceType.INDUSTRIAL
        elif intel_class == ThermalSourceClass.PERSISTENT_THERMAL_SOURCE:
            return SourceType.INDUSTRIAL
        elif intel_class == ThermalSourceClass.CONTROLLED_HEAT_SOURCE:
            if f.is_agricultural_land_cover:
                return SourceType.AGRICULTURAL
            elif f.is_protected_area or f.is_vegetation_land_cover:
                return SourceType.PRESCRIBED_BURN
            else:
                return SourceType.PRESCRIBED_BURN
        else:
            return SourceType.UNKNOWN

    def _build_full_probabilities(
        self,
        class_probs: Dict[str, float],
        f: FeatureVector,
    ) -> Dict[str, float]:
        """Construct calibrated probabilities matching all 7 SourceTypes plus Intel classes."""
        veg_prob = class_probs.get(ThermalSourceClass.VEGETATION_FIRE.value, 0.05)
        ind_fire_prob = class_probs.get(ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value, 0.05)
        ctrl_prob = class_probs.get(ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value, 0.05)
        persist_prob = class_probs.get(ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value, 0.05)
        unk_prob = class_probs.get(ThermalSourceClass.UNKNOWN.value, 0.05)

        # Distribute into frozen 7 source types
        wildfire_p = veg_prob * 0.90 + ctrl_prob * 0.10
        industrial_p = ind_fire_prob * 0.85 + persist_prob * 0.85
        agri_p = ctrl_prob * 0.65 if f.is_agricultural_land_cover else ctrl_prob * 0.20
        prescribed_p = ctrl_prob * 0.70 if f.is_protected_area else ctrl_prob * 0.15
        urban_p = unk_prob * 0.15 if f.is_urban_land_cover else 0.01
        volcanic_p = 0.005
        unknown_p = unk_prob * 0.80

        raw_source_probs = {
            SourceType.WILDFIRE.value: max(0.001, wildfire_p),
            SourceType.INDUSTRIAL.value: max(0.001, industrial_p),
            SourceType.AGRICULTURAL.value: max(0.001, agri_p),
            SourceType.PRESCRIBED_BURN.value: max(0.001, prescribed_p),
            SourceType.URBAN.value: max(0.001, urban_p),
            SourceType.VOLCANIC.value: max(0.001, volcanic_p),
            SourceType.UNKNOWN.value: max(0.001, unknown_p),
        }
        total_source = sum(raw_source_probs.values())
        norm_source_probs = {k: round(v / total_source, 4) for k, v in raw_source_probs.items()}

        # Combine both sets so callers can inspect standard or intelligence-specific classes
        return {
            **norm_source_probs,
            **class_probs,
        }

    def _compute_confidence(
        self,
        f: FeatureVector,
        top_prob: float,
        margin: float,
        predicted_class: ThermalSourceClass,
    ) -> float:
        """Compute calibrated classification confidence considering available evidence,

        evidence strength, missing context, and ambiguity.
        """
        # If class is UNKNOWN, confidence is naturally constrained
        if predicted_class == ThermalSourceClass.UNKNOWN:
            return round(min(0.55, max(MIN_CONFIDENCE, top_prob * 0.6)), 3)

        # Evidence completeness score: 0.4 to 1.0
        # Thermal is 0.35, Geo is 0.25, Weather is 0.20, History is 0.20
        completeness = 0.35
        if f.has_geospatial:
            completeness += 0.25
        if f.has_weather:
            completeness += 0.20
        if f.has_history:
            completeness += 0.20

        # Radiometric strength
        radiometric_strength = 0.5 * f.satellite_confidence + 0.5 * f.frp_norm

        # Margin factor: clear winner boosts confidence, tie reduces it
        margin_factor = 0.5 + min(0.5, margin * 1.5)

        base_conf = (top_prob * 0.45) + (completeness * 0.30) + (radiometric_strength * 0.25)
        calibrated = base_conf * margin_factor

        return round(max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, calibrated)), 3)

    def _compute_feature_importance(
        self,
        f: FeatureVector,
        predicted_class: ThermalSourceClass,
    ) -> Dict[str, float]:
        """Compute relative importance weights of features driving the classification."""
        importance: Dict[str, float] = {}

        if predicted_class == ThermalSourceClass.VEGETATION_FIRE:
            importance["fire_radiative_power"] = 0.35
            importance["land_cover_vegetation"] = 0.30
            if f.has_weather:
                importance["fire_weather_conditions"] = 0.20
                importance["satellite_confidence"] = 0.15
            else:
                importance["satellite_confidence"] = 0.20
                importance["topographic_slope"] = 0.15
        elif predicted_class in (ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE, ThermalSourceClass.PERSISTENT_THERMAL_SOURCE):
            importance["industrial_proximity"] = 0.40
            importance["historical_persistence"] = 0.30
            importance["fire_radiative_power"] = 0.20
            importance["satellite_confidence"] = 0.10
        elif predicted_class == ThermalSourceClass.CONTROLLED_HEAT_SOURCE:
            importance["land_management_status"] = 0.35
            importance["fire_radiative_power"] = 0.30
            importance["historical_operational_baseline"] = 0.20
            importance["weather_stability"] = 0.15
        else:
            importance["satellite_confidence"] = 0.40
            importance["thermal_intensity"] = 0.30
            importance["unresolved_context"] = 0.30

        # Normalize weights to sum to 1.0
        total = sum(importance.values())
        return {k: round(v / total, 3) for k, v in importance.items()}

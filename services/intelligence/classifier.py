"""Thermal Source Classification subsystem.

Redesigned for truthful, reproducible, evidence-based operational intelligence.

Core Principle:
The system does NOT pretend to have a supervised ML classifier.
Classification is rule-based evidence accumulation across:
1. Radiometric thermal signature (FRP, brightness temperature).
2. Geospatial context (land cover fuel profile, industrial/settlement proximity).
3. Atmospheric fire weather (wind vector, relative humidity, temperature).
4. Historical overpass persistence (recurrent flare stack vs sudden uncontained wildfire).

For each inference, produces:
- predicted_source (frozen SourceType)
- supporting evidence (specific observed signals justifying the category)
- opposing evidence (counter-indications or alternative hypotheses evaluated)
- rule identifier (e.g. RULE_ACTIVE_VEGETATION_WILDFIRE)
- methodology version (e.g. v2.0.0-rules-evidence)
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any

from services.api.schemas.common import SourceType
from services.api.schemas.intelligence import ClassificationResult
from services.api.schemas.v2.assessment import ClassificationAssessment
from services.intelligence.config import (
    ThermalSourceClass,
    INTELLIGENCE_CLASS_TO_SOURCE_TYPE,
    MIN_CONFIDENCE,
    MAX_CONFIDENCE,
    DEFAULT_UNKNOWN_CONFIDENCE,
    METHODOLOGY_RULE_BASED,
    ALGORITHM_VERSION,
)
from services.intelligence.features import FeatureVector
from services.intelligence.thresholds import (
    FRP_HIGH_MW,
    FRP_MODERATE_MW,
    FRP_LOW_MW,
    WIND_HIGH_KMH,
    RH_CRITICAL_PCT,
    INDUSTRIAL_IMMEDIATE_M,
    INDUSTRIAL_VICINITY_M,
    RECURRENT_MIN_PASSES_30D,
)


@dataclass
class ClassificationEvidenceRecord:
    """Detailed evidence dossier accompanying rule-based source classification."""
    predicted_source: SourceType
    intel_class: ThermalSourceClass
    rule_identifier: str
    methodology: str = METHODOLOGY_RULE_BASED
    methodology_version: str = ALGORITHM_VERSION
    supporting_evidence: List[str] = field(default_factory=list)
    opposing_evidence: List[str] = field(default_factory=list)
    rule_support_distribution: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.50
    feature_importance: Dict[str, float] = field(default_factory=dict)


class ThermalSourceClassifier:
    """Explainable rule-based evidence accumulator for thermal source categorization."""

    def __init__(
        self,
        model_version: str = ALGORITHM_VERSION,
        rules_config: Optional[Any] = None,
        taxonomy_config: Optional[Any] = None,
    ):
        self.model_version = model_version
        self._rules_config = rules_config
        self._taxonomy_config = taxonomy_config

    @property
    def rules_config(self) -> Any:
        if self._rules_config is not None:
            return self._rules_config
        try:
            from profiles.loader import get_active_profile
            return get_active_profile().rules
        except Exception:
            return None

    @property
    def taxonomy_config(self) -> Any:
        if self._taxonomy_config is not None:
            return self._taxonomy_config
        try:
            from profiles.loader import get_active_profile
            return get_active_profile().taxonomy
        except Exception:
            return None

    def classify(self, features: FeatureVector) -> ClassificationResult:
        """Classify a thermal observation and return a backward-compatible ClassificationResult."""
        evidence_record = self.evaluate_evidence(features)

        return ClassificationResult(
            predicted_source=evidence_record.predicted_source,
            confidence=round(evidence_record.confidence, 3),
            probabilities=evidence_record.rule_support_distribution,
            feature_importance=evidence_record.feature_importance,
        )

    def classify_v2(self, features: FeatureVector) -> ClassificationAssessment:
        """Classify a thermal observation and return canonical V2 ClassificationAssessment."""
        evidence_record = self.evaluate_evidence(features)

        # Distribute into 7 frozen source types
        source_probs = {
            st.value: evidence_record.rule_support_distribution.get(st.value, 0.01)
            for st in SourceType
        }
        total_p = sum(source_probs.values()) or 1.0
        normalized_probs = {k: round(v / total_p, 4) for k, v in source_probs.items()}

        return ClassificationAssessment(
            predicted_source=evidence_record.predicted_source,
            classification_confidence=round(evidence_record.confidence, 3),
            probabilities=normalized_probs,
            feature_importance=evidence_record.feature_importance,
        )

    def evaluate_evidence(self, f: FeatureVector) -> ClassificationEvidenceRecord:
        """Execute rule-based evidence accumulation, generating supporting and opposing evidence."""
        rc = self.rules_config
        tc = self.taxonomy_config

        # 1. Compute evidence scores and track specific rule assertions
        if rc is not None and hasattr(rc, "evidence_priors") and rc.evidence_priors:
            evidence: Dict[str, float] = dict(rc.evidence_priors)
        else:
            evidence: Dict[str, float] = {
                ThermalSourceClass.VEGETATION_FIRE.value: 0.10,
                ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value: 0.10,
                ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value: 0.10,
                ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value: 0.10,
                ThermalSourceClass.UNKNOWN.value: 0.15,
            }

        # Resolve thresholds
        if rc is not None and hasattr(rc, "thresholds") and rc.thresholds:
            t = rc.thresholds
            frp_high = t.frp_high_mw
            frp_moderate = t.frp_moderate_mw
            recurrent_passes = t.recurrent_min_passes_30d
            persistence_thresh = t.persistence_score_threshold
        else:
            frp_high = FRP_HIGH_MW
            frp_moderate = FRP_MODERATE_MW
            recurrent_passes = RECURRENT_MIN_PASSES_30D
            persistence_thresh = 0.50

        supporting: List[str] = []
        opposing: List[str] = []
        active_rule_id = "RULE_AMBIGUOUS_UNRESOLVED_UNKNOWN"

        # --- A. PERSISTENT_THERMAL_SOURCE ---
        # Strong indicators: continuous 30d/90d detections, stationary emitter, stable moderate FRP
        is_persistent = (
            f.persistence_score >= persistence_thresh
            or (f.prior_detections_30d and f.prior_detections_30d >= recurrent_passes)
            or f.is_recurrent_site
        )
        if is_persistent:
            recurrence_boost = min(1.2, f.persistence_score * 1.5)
            evidence[ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value] += 1.0 + recurrence_boost
            passes = f.prior_detections_30d or "10+"
            supporting.append(
                f"Multi-temporal satellite overpasses ({passes} passes in 30d) confirm stationary recurring emitter."
            )
            if f.industrial_proximity_score >= 0.50 or f.is_industrial_land_cover:
                evidence[ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value] += 0.80
                supporting.append(
                    f"Observation aligns with mapped industrial facility perimeter ({f.industrial_dist_m or 0:.0f}m)."
                )
            if f.frp >= 100.0:
                opposing.append(
                    f"Extreme FRP ({f.frp:.1f} MW) significantly exceeds typical stationary operational flare envelopes."
                )

        # --- B. POTENTIAL_INDUSTRIAL_FIRE ---
        # Strong indicators: close to industrial facility, high FRP/brightness, low persistence (sudden emergence)
        is_near_industrial = f.industrial_proximity_score >= 0.40 or f.is_industrial_land_cover
        if is_near_industrial:
            ind_base = f.industrial_proximity_score * 1.2
            if f.frp >= frp_high and f.satellite_confidence >= 0.70:
                evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += ind_base + 1.2
                supporting.append(
                    f"Intense thermal radiant energy ({f.frp:.1f} MW) detected within industrial complex zone."
                )
                if f.persistence_score < 0.30:
                    evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += 0.60
                    supporting.append("Low historical persistence indicates sudden emergence rather than routine flaring.")
                else:
                    opposing.append("Ongoing multi-week history indicates probable continuous process flare.")
            elif f.frp >= frp_moderate:
                evidence[ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value] += ind_base + 0.40
                supporting.append(f"Moderate thermal activity in vicinity of industrial structures ({f.industrial_dist_m or 0:.0f}m).")

        # --- C. CONTROLLED_HEAT_SOURCE ---
        # Indicators: protected area with moderate FRP, agricultural stubble burn, low abnormality
        if f.is_protected_area and 3.0 <= f.frp < 55.0:
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 1.80
            park_name = f.protected_area_name or "Conservation Area"
            supporting.append(f"Observation located in managed reserve ({park_name}) with bounded FRP ({f.frp:.1f} MW).")
        elif f.is_agricultural_land_cover:
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 1.20
            supporting.append("Agricultural crop/field land cover consistent with seasonal residue clearance.")
        elif f.industrial_proximity_score >= 0.70 and f.frp < 30.0 and f.persistence_score >= 0.30:
            evidence[ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value] += 0.70
            supporting.append("Low-intensity flare stack operating within routine process limits.")

        if f.frp >= 80.0:
            opposing.append(f"Very high radiative energy ({f.frp:.1f} MW) strongly contradicts controlled/prescribed burning.")

        # --- D. VEGETATION_FIRE ---
        # Indicators: combustible vegetation land cover, away from industry, high FRP, adverse fire weather
        if f.is_vegetation_land_cover:
            if f.is_protected_area and f.frp < 55.0:
                veg_boost = 0.35  # Protected parcel with low/moderate FRP is likely managed prescribed burn
            else:
                veg_boost = 1.0
                if f.frp >= 35.0:
                    veg_boost += 0.60
                    supporting.append(f"Substantial combustion intensity ({f.frp:.1f} MW) across vegetative fuel bed.")
                if f.fire_weather_score and f.fire_weather_score >= 0.50:
                    veg_boost += f.fire_weather_score * 0.80
                    wind = f.wind_speed_kmh or 0
                    rh = f.relative_humidity_pct or 0
                    supporting.append(f"Adverse fire weather ({wind:.0f} km/h wind, {rh:.0f}% RH) accelerates wildland spread.")
                if f.slope_factor > 0.3:
                    veg_boost += f.slope_factor * 0.40
                    supporting.append(f"Steep terrain slope ({f.slope_degrees or 0:.1f}°) enhances convective preheating.")
                if f.industrial_proximity_score < 0.20:
                    veg_boost += 0.50
                    opposing.append(f"Remote spatial separation from industrial nodes ({f.industrial_dist_m or 9999:.0f}m).")
            evidence[ThermalSourceClass.VEGETATION_FIRE.value] += veg_boost
        elif not f.has_industrial_context and f.frp >= 60.0:
            evidence[ThermalSourceClass.VEGETATION_FIRE.value] += 0.90
            supporting.append(f"High FRP ({f.frp:.1f} MW) in unmapped wildland zone indicates active vegetation fire.")

        # --- E. UNKNOWN / CONTRADICTORY / WEAK EVIDENCE ---
        if f.satellite_confidence < 0.45:
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.80
            supporting.append("Low provider satellite sensor detection confidence (< 45%).")
        if not f.has_geospatial and not f.has_history and not f.has_weather:
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.90
            supporting.append("Observation lacks geospatial, atmospheric, and historical context.")
        if f.frp < 8.0 and not f.is_recurrent_site and not f.is_protected_area:
            evidence[ThermalSourceClass.UNKNOWN.value] += 0.40
            opposing.append(f"Low thermal radiance ({f.frp:.1f} MW) lacks sufficient distinctive spectral signature.")

        # 2. Normalize evidence into class support distribution
        total_ev = sum(max(0.01, v) for v in evidence.values())
        class_support = {k: round(max(0.01, v) / total_ev, 4) for k, v in evidence.items()}

        # 3. Determine winning intelligence class and margin
        top_class_name, top_prob = max(class_support.items(), key=lambda item: item[1])
        winning_intel_class = ThermalSourceClass(top_class_name)

        sorted_probs = sorted(class_support.values(), reverse=True)
        margin = sorted_probs[0] - (sorted_probs[1] if len(sorted_probs) > 1 else 0.0)

        # 4. Map to frozen SourceType
        predicted_source = self._map_to_source_type(winning_intel_class, f)

        # 5. Determine active Rule Identifier
        if rc is not None and hasattr(rc, "rule_identifiers") and rc.rule_identifiers:
            active_rule_id = rc.rule_identifiers.get(
                winning_intel_class.value, "RULE_AMBIGUOUS_UNRESOLVED_UNKNOWN"
            )
        else:
            if winning_intel_class == ThermalSourceClass.VEGETATION_FIRE:
                active_rule_id = "RULE_ACTIVE_VEGETATION_WILDFIRE"
            elif winning_intel_class == ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE:
                active_rule_id = "RULE_INDUSTRIAL_HAZARD_SPIKE"
            elif winning_intel_class == ThermalSourceClass.PERSISTENT_THERMAL_SOURCE:
                active_rule_id = "RULE_PERSISTENT_INDUSTRIAL_EMITTER"
            elif winning_intel_class == ThermalSourceClass.CONTROLLED_HEAT_SOURCE:
                active_rule_id = "RULE_MANAGED_PRESCRIBED_BURN" if f.is_protected_area else "RULE_AGRICULTURAL_BURNING"
            else:
                active_rule_id = "RULE_AMBIGUOUS_UNRESOLVED_UNKNOWN"

        # 6. Build full probability distribution across all 7 frozen SourceTypes + 5 Intel classes
        full_probabilities = self._build_full_probabilities(class_support, f)

        # 7. Compute rule support confidence
        confidence = self._compute_confidence(f, top_prob, margin, winning_intel_class)

        # 8. Compute feature importance attribution
        feature_importance = self._compute_feature_importance(f, winning_intel_class)

        return ClassificationEvidenceRecord(
            predicted_source=predicted_source,
            intel_class=winning_intel_class,
            rule_identifier=active_rule_id,
            methodology=METHODOLOGY_RULE_BASED,
            methodology_version=self.model_version,
            supporting_evidence=supporting,
            opposing_evidence=opposing,
            rule_support_distribution=full_probabilities,
            confidence=confidence,
            feature_importance=feature_importance,
        )

    def _map_to_source_type(self, intel_class: ThermalSourceClass, f: FeatureVector) -> SourceType:
        """Map winning intelligence class to frozen SourceType enum."""
        tc = self.taxonomy_config
        if tc is not None and hasattr(tc, "class_to_source_type") and tc.class_to_source_type:
            val = tc.class_to_source_type.get(intel_class.value)
            if val is not None:
                if intel_class == ThermalSourceClass.CONTROLLED_HEAT_SOURCE and f.is_agricultural_land_cover:
                    return SourceType.AGRICULTURAL
                return SourceType(val) if isinstance(val, str) else val

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
        """Construct normalized rule-support scores matching all 7 SourceTypes plus Intel classes."""
        veg_prob = class_probs.get(ThermalSourceClass.VEGETATION_FIRE.value, 0.05)
        ind_fire_prob = class_probs.get(ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE.value, 0.05)
        ctrl_prob = class_probs.get(ThermalSourceClass.CONTROLLED_HEAT_SOURCE.value, 0.05)
        persist_prob = class_probs.get(ThermalSourceClass.PERSISTENT_THERMAL_SOURCE.value, 0.05)
        unk_prob = class_probs.get(ThermalSourceClass.UNKNOWN.value, 0.05)

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
        """Compute rule support confidence metric considering evidence completeness and clarity."""
        if predicted_class == ThermalSourceClass.UNKNOWN:
            return round(min(0.55, max(MIN_CONFIDENCE, top_prob * 0.6)), 3)

        completeness = f.completeness_score
        radiometric_strength = 0.5 * f.satellite_confidence + 0.5 * f.frp_norm
        margin_factor = 0.5 + min(0.5, margin * 1.5)

        base_conf = (top_prob * 0.45) + (completeness * 0.30) + (radiometric_strength * 0.25)
        calibrated = base_conf * margin_factor

        return round(max(MIN_CONFIDENCE, min(MAX_CONFIDENCE, calibrated)), 3)

    def _compute_feature_importance(
        self,
        f: FeatureVector,
        predicted_class: ThermalSourceClass,
    ) -> Dict[str, float]:
        """Compute relative importance weights of features driving the classification decision."""
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
        elif predicted_class in (
            ThermalSourceClass.POTENTIAL_INDUSTRIAL_FIRE,
            ThermalSourceClass.PERSISTENT_THERMAL_SOURCE,
        ):
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

        total = sum(importance.values())
        return {k: round(v / total, 3) for k, v in importance.items()}

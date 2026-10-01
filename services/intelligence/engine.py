"""Thermal Anomaly Intelligence Engine.

Provides unified evaluation of satellite thermal anomalies:
1. Source Classification (Wildfire, Industrial, Agricultural, Prescribed, Urban, Volcanic, Unknown)
   with five core intelligence classes:
   - VEGETATION_FIRE
   - POTENTIAL_INDUSTRIAL_FIRE
   - CONTROLLED_HEAT_SOURCE
   - PERSISTENT_THERMAL_SOURCE
   - UNKNOWN
2. Statistical & IsolationForest Anomaly Detection
3. Composite Risk & Severity Scoring (0-100)
4. Explainable AI Attribution Factor Generation
5. Batch and Population-Level Analysis
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from services.api.schemas.common import SourceType, RiskLevel
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.intelligence import (
    ClassificationResult,
    AnomalyResult,
    RiskAssessment,
    IntelligenceResult,
)
from services.intelligence.config import (
    ThermalSourceClass,
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    RANDOM_STATE,
)
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor, FeatureVector
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.anomaly import AnomalyDetector
from services.intelligence.risk import RiskAssessor


class ThermalIntelligenceEngine:
    """Core intelligence engine for evaluating thermal anomalies and contextual risk."""

    def __init__(
        self,
        model_version: str = "v1.2-hybrid-rules",
        baseline_frp_mean: float = DEFAULT_BASELINE_FRP_MEAN,
        baseline_frp_std: float = DEFAULT_BASELINE_FRP_STD,
        sigma_threshold: float = ANOMALY_SIGMA_THRESHOLD,
        random_state: int = RANDOM_STATE,
    ):
        self.model_version = model_version
        self.classifier = ThermalSourceClassifier(model_version=model_version)
        self.anomaly_detector = AnomalyDetector(
            baseline_frp_mean=baseline_frp_mean,
            baseline_frp_std=baseline_frp_std,
            sigma_threshold=sigma_threshold,
            random_state=random_state,
        )
        self.risk_assessor = RiskAssessor()

    def analyze_hotspot(
        self,
        hotspot: Union[Hotspot, Dict[str, Any], Any],
        context: Optional[Union[HotspotContext, Dict[str, Any]]] = None,
        comparable_hotspots: Optional[List[Any]] = None,
    ) -> IntelligenceResult:
        """Primary public entry point: Evaluate a single hotspot with its enriched context

        and optional local comparable observations.
        """
        # Normalize hotspot input
        normalized_hotspot = NormalizedHotspotInput.from_input(hotspot)

        # Normalize context input
        if isinstance(context, HotspotContext):
            ctx = context
        elif isinstance(context, dict):
            ctx = HotspotContext.from_dict(context)
        else:
            ctx = HotspotContext()

        # Extract features
        features = FeatureExtractor.extract(normalized_hotspot, ctx)

        # Extract population features if comparable hotspots provided
        pop_features: Optional[List[FeatureVector]] = None
        if comparable_hotspots:
            pop_features = [
                FeatureExtractor.extract(
                    NormalizedHotspotInput.from_input(ch),
                    HotspotContext(),
                )
                for ch in comparable_hotspots
            ]

        # 1. Source Classification
        classification = self.classifier.classify(features)

        # 2. Anomaly Detection
        anomaly = self.anomaly_detector.detect(features, population_features=pop_features)

        # 3. Composite Risk & Severity Scoring
        risk = self.risk_assessor.assess_risk(
            features=features,
            source_type=classification.predicted_source,
            anomaly_result=anomaly,
        )

        return IntelligenceResult(
            hotspot_id=features.hotspot_id,
            classification=classification,
            anomaly=anomaly,
            risk=risk,
            model_version=self.model_version,
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )

    def batch_analyze(
        self,
        hotspots: List[Union[Hotspot, Dict[str, Any], Any]],
        contexts: Optional[List[Optional[Union[HotspotContext, Dict[str, Any]]]]] = None,
    ) -> List[IntelligenceResult]:
        """Batch evaluate a collection of hotspots, leveraging the entire population for

        multi-variate anomaly detection where population >= 5.
        """
        if not hotspots:
            return []

        # Prepare contexts
        ctx_list: List[HotspotContext] = []
        for i in range(len(hotspots)):
            raw_ctx = contexts[i] if contexts and i < len(contexts) else None
            if isinstance(raw_ctx, HotspotContext):
                ctx_list.append(raw_ctx)
            elif isinstance(raw_ctx, dict):
                ctx_list.append(HotspotContext.from_dict(raw_ctx))
            else:
                ctx_list.append(HotspotContext())

        # Extract all feature vectors
        all_features: List[FeatureVector] = [
            FeatureExtractor.extract(
                NormalizedHotspotInput.from_input(h),
                ctx,
            )
            for h, ctx in zip(hotspots, ctx_list)
        ]

        results: List[IntelligenceResult] = []
        for features in all_features:
            classification = self.classifier.classify(features)
            anomaly = self.anomaly_detector.detect(features, population_features=all_features)
            risk = self.risk_assessor.assess_risk(
                features=features,
                source_type=classification.predicted_source,
                anomaly_result=anomaly,
            )
            results.append(
                IntelligenceResult(
                    hotspot_id=features.hotspot_id,
                    classification=classification,
                    anomaly=anomaly,
                    risk=risk,
                    model_version=self.model_version,
                    evaluated_at=datetime.now(timezone.utc).isoformat(),
                )
            )

        return results

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
        """Backwards-compatible interface matching Phase 0 method signature."""
        hotspot_dict = {
            "id": hotspot_id,
            "frp": frp,
            "brightness": brightness,
            "confidence": "high" if frp > 50 else "nominal",
        }
        context_dict = {
            "land_cover": land_cover,
            "prior_detections_30d": historical_recurrence,
            "is_protected_area": is_protected_area,
            "wind_speed_kmh": wind_speed_kmh,
            "relative_humidity_percent": relative_humidity_percent,
            "temperature_celsius": temperature_celsius,
            "distance_to_settlement_m": distance_to_settlement_m,
            "distance_to_infrastructure_m": distance_to_infra_m,
            "slope_degrees": slope_degrees,
        }
        return self.analyze_hotspot(hotspot=hotspot_dict, context=context_dict)

    def detect_anomaly(
        self,
        frp: float,
        brightness: float,
        historical_detections_30d: int,
        baseline_frp_mean: Optional[float] = None,
        baseline_frp_std: Optional[float] = None,
    ) -> AnomalyResult:
        """Backwards-compatible anomaly detection helper."""
        detector = (
            self.anomaly_detector
            if baseline_frp_mean is None
            else AnomalyDetector(
                baseline_frp_mean=baseline_frp_mean,
                baseline_frp_std=baseline_frp_std or 20.0,
            )
        )
        norm_h = NormalizedHotspotInput(id="ANOMALY-CHECK", frp=frp, brightness=brightness)
        ctx = HotspotContext(prior_detections_30d=historical_detections_30d)
        features = FeatureExtractor.extract(norm_h, ctx)
        return detector.detect(features)

    def classify_source(
        self,
        frp: float,
        brightness: float,
        land_cover: str,
        historical_recurrence: int,
        is_protected_area: bool = False,
    ) -> ClassificationResult:
        """Backwards-compatible classification helper."""
        norm_h = NormalizedHotspotInput(id="CLASSIFY-CHECK", frp=frp, brightness=brightness)
        ctx = HotspotContext(
            land_cover=land_cover,
            prior_detections_30d=historical_recurrence,
            is_protected_area=is_protected_area,
        )
        features = FeatureExtractor.extract(norm_h, ctx)
        return self.classifier.classify(features)

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
        """Backwards-compatible risk assessment helper."""
        norm_h = NormalizedHotspotInput(id="RISK-CHECK", frp=frp, brightness=320.0)
        ctx = HotspotContext(
            wind_speed_kmh=wind_speed_kmh,
            relative_humidity_pct=relative_humidity_percent,
            temperature_c=temperature_celsius,
            distance_to_settlement_m=distance_to_settlement_m,
            distance_to_infrastructure_m=distance_to_infra_m,
            slope_degrees=slope_degrees,
            prior_detections_30d=historical_recurrence,
        )
        features = FeatureExtractor.extract(norm_h, ctx)
        anomaly = self.anomaly_detector.detect(features)
        return self.risk_assessor.assess_risk(
            features=features,
            source_type=source_type,
            anomaly_result=anomaly,
        )

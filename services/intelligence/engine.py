"""Thermal Anomaly Intelligence Engine.

Provides unified, truthful, reproducible evaluation of satellite thermal anomalies:
1. Source Classification: Rule-based evidence accumulation across 7 SourceTypes
   and 5 internal operational classes.
2. Anomaly Detection: Primary historical/site baseline comparison with secondary
   multivariate IsolationForest.
3. Composite Risk & Severity: Multi-criteria operational consequence heuristic (0-100)
   decomposed into hazard intensity, exposure, and site permanence.
4. Explainable AI Factors: Direct signal-grounded attribution factors with centralized thresholds.
5. Canonical V2 Assessment Contract: Deterministic input hashing, reproducibility, and audit provenance.
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
from services.api.schemas.v2.assessment import Assessment
from services.intelligence.config import (
    ThermalSourceClass,
    DEFAULT_BASELINE_FRP_MEAN,
    DEFAULT_BASELINE_FRP_STD,
    ANOMALY_SIGMA_THRESHOLD,
    RANDOM_STATE_PINNED,
    ALGORITHM_VERSION,
    METHODOLOGY_V2_COMPOSITE,
)
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor, FeatureVector
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.anomaly import AnomalyDetector
from services.intelligence.risk import RiskAssessor
from services.intelligence.assessment import AssessmentSynthesizer
from services.intelligence.reproducibility import now_utc_iso


class ThermalIntelligenceEngine:
    """Core intelligence engine for evaluating thermal anomalies and contextual operational risk."""

    def __init__(
        self,
        model_version: str = ALGORITHM_VERSION,
        baseline_frp_mean: float = DEFAULT_BASELINE_FRP_MEAN,
        baseline_frp_std: float = DEFAULT_BASELINE_FRP_STD,
        sigma_threshold: float = ANOMALY_SIGMA_THRESHOLD,
        random_state: int = RANDOM_STATE_PINNED,
        profile: Optional[Union[str, Any]] = None,
        classifier: Optional[ThermalSourceClassifier] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        risk_assessor: Optional[RiskAssessor] = None,
    ):
        self.model_version = model_version

        resolved_profile = None
        if profile is not None:
            if isinstance(profile, str):
                from profiles.loader import load_profile_by_id
                resolved_profile = load_profile_by_id(profile)
            else:
                resolved_profile = profile
        self.profile = resolved_profile

        rules_cfg = resolved_profile.rules if resolved_profile else None
        tax_cfg = resolved_profile.taxonomy if resolved_profile else None
        risk_cfg = resolved_profile.risk if resolved_profile else None

        self.classifier = classifier or ThermalSourceClassifier(
            model_version=model_version,
            rules_config=rules_cfg,
            taxonomy_config=tax_cfg,
        )
        self.anomaly_detector = anomaly_detector or AnomalyDetector(
            baseline_frp_mean=baseline_frp_mean,
            baseline_frp_std=baseline_frp_std,
            sigma_threshold=sigma_threshold,
            random_state=random_state,
        )
        self.risk_assessor = risk_assessor or RiskAssessor(risk_config=risk_cfg)
        self.synthesizer = AssessmentSynthesizer(
            classifier=self.classifier,
            anomaly_detector=self.anomaly_detector,
            risk_assessor=self.risk_assessor,
            algorithm_version=model_version,
        )

    # ==========================================================================
    # Canonical V2 Assessment API (Frozen Domain Contracts)
    # ==========================================================================

    def assess_hotspot(
        self,
        hotspot: Union[Hotspot, Dict[str, Any], Any],
        context: Optional[Union[HotspotContext, Dict[str, Any]]] = None,
        target_id: Optional[str] = None,
        target_type: str = "observation",
        as_of_utc: Optional[str] = None,
        comparable_hotspots: Optional[List[Any]] = None,
    ) -> Assessment:
        """Primary Canonical V2 Entry Point:

        Returns the frozen Assessment domain entity with deterministic input_hash,
        audit methodology, data quality completeness metrics, and explainable factors.
        """
        norm_h = NormalizedHotspotInput.from_input(hotspot)
        ctx = self._normalize_context(context)
        features = FeatureExtractor.extract(norm_h, ctx)

        pop_features: Optional[List[FeatureVector]] = None
        if comparable_hotspots:
            pop_features = [
                FeatureExtractor.extract(NormalizedHotspotInput.from_input(ch), HotspotContext())
                for ch in comparable_hotspots
            ]

        t_id = target_id or norm_h.id
        return self.synthesizer.build_assessment(
            target_id=t_id,
            features=features,
            normalized_hotspot=norm_h,
            context=ctx,
            target_type=target_type,
            as_of_utc=as_of_utc,
            population_features=pop_features,
        )

    def assess_batch(
        self,
        hotspots: List[Union[Hotspot, Dict[str, Any], Any]],
        contexts: Optional[List[Optional[Union[HotspotContext, Dict[str, Any]]]]] = None,
        target_type: str = "observation",
        as_of_utc: Optional[str] = None,
    ) -> List[Assessment]:
        """Batch evaluate a collection of hotspots producing canonical V2 Assessments."""
        if not hotspots:
            return []

        ctx_list = self._prepare_context_list(hotspots, contexts)
        all_inputs = [NormalizedHotspotInput.from_input(h) for h in hotspots]
        all_features = [FeatureExtractor.extract(h, ctx) for h, ctx in zip(all_inputs, ctx_list)]

        assessments: List[Assessment] = []
        for h, ctx, feat in zip(all_inputs, ctx_list, all_features):
            asm = self.synthesizer.build_assessment(
                target_id=h.id,
                features=feat,
                normalized_hotspot=h,
                context=ctx,
                target_type=target_type,
                as_of_utc=as_of_utc,
                population_features=all_features,
            )
            assessments.append(asm)

        return assessments

    # ==========================================================================
    # V1 / Backward-Compatible Public Entry Points
    # ==========================================================================

    def analyze_hotspot(
        self,
        hotspot: Union[Hotspot, Dict[str, Any], Any],
        context: Optional[Union[HotspotContext, Dict[str, Any]]] = None,
        comparable_hotspots: Optional[List[Any]] = None,
    ) -> IntelligenceResult:
        """Evaluate a single hotspot and return backward-compatible IntelligenceResult."""
        normalized_hotspot = NormalizedHotspotInput.from_input(hotspot)
        ctx = self._normalize_context(context)
        features = FeatureExtractor.extract(normalized_hotspot, ctx)

        pop_features: Optional[List[FeatureVector]] = None
        if comparable_hotspots:
            pop_features = [
                FeatureExtractor.extract(NormalizedHotspotInput.from_input(ch), HotspotContext())
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
            evaluated_at=now_utc_iso(),
        )

    def batch_analyze(
        self,
        hotspots: List[Union[Hotspot, Dict[str, Any], Any]],
        contexts: Optional[List[Optional[Union[HotspotContext, Dict[str, Any]]]]] = None,
    ) -> List[IntelligenceResult]:
        """Batch evaluate a collection of hotspots returning IntelligenceResult objects."""
        if not hotspots:
            return []

        ctx_list = self._prepare_context_list(hotspots, contexts)
        all_features: List[FeatureVector] = [
            FeatureExtractor.extract(NormalizedHotspotInput.from_input(h), ctx)
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
                    evaluated_at=now_utc_iso(),
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

    # ==========================================================================
    # Internal Helpers
    # ==========================================================================

    @staticmethod
    def _normalize_context(context: Optional[Union[HotspotContext, Dict[str, Any]]]) -> HotspotContext:
        """Normalize context input safely into HotspotContext dataclass."""
        if isinstance(context, HotspotContext):
            return context
        elif isinstance(context, dict):
            return HotspotContext.from_dict(context)
        return HotspotContext()

    @staticmethod
    def _prepare_context_list(
        hotspots: List[Any],
        contexts: Optional[List[Optional[Union[HotspotContext, Dict[str, Any]]]]],
    ) -> List[HotspotContext]:
        """Align context list length to match hotspot batch size."""
        ctx_list: List[HotspotContext] = []
        for i in range(len(hotspots)):
            raw_ctx = contexts[i] if contexts and i < len(contexts) else None
            if isinstance(raw_ctx, HotspotContext):
                ctx_list.append(raw_ctx)
            elif isinstance(raw_ctx, dict):
                ctx_list.append(HotspotContext.from_dict(raw_ctx))
            else:
                ctx_list.append(HotspotContext())
        return ctx_list

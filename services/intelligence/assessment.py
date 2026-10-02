"""Canonical V2 Assessment Synthesizer for ThermalIntel Intelligence.

Assembles fully typed, reproducible Assessment instances conforming strictly
to the frozen V2 schema (services/api/schemas/v2/assessment.py).
"""

from typing import Optional, List
from datetime import datetime, timezone

from services.api.schemas.v2.assessment import (
    Assessment,
    ClassificationAssessment,
    AnomalyAssessment,
    RiskAssessmentResult,
    DataQualityAssessment,
    AssessmentMethodology,
)
from services.intelligence.config import (
    METHODOLOGY_V2_COMPOSITE,
    ALGORITHM_VERSION,
)
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureVector
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.anomaly import AnomalyDetector
from services.intelligence.risk import RiskAssessor
from services.intelligence.reproducibility import (
    compute_input_hash,
    generate_assessment_id,
    now_utc_iso,
)


class AssessmentSynthesizer:
    """Orchestrates subsystem inferences into the canonical V2 Assessment domain entity."""

    def __init__(
        self,
        classifier: Optional[ThermalSourceClassifier] = None,
        anomaly_detector: Optional[AnomalyDetector] = None,
        risk_assessor: Optional[RiskAssessor] = None,
        algorithm_version: str = ALGORITHM_VERSION,
    ):
        self.classifier = classifier or ThermalSourceClassifier(model_version=algorithm_version)
        self.anomaly_detector = anomaly_detector or AnomalyDetector()
        self.risk_assessor = risk_assessor or RiskAssessor()
        self.algorithm_version = algorithm_version

    def build_assessment(
        self,
        target_id: str,
        features: FeatureVector,
        normalized_hotspot: NormalizedHotspotInput,
        context: Optional[HotspotContext] = None,
        target_type: str = "observation",
        as_of_utc: Optional[str] = None,
        population_features: Optional[List[FeatureVector]] = None,
    ) -> Assessment:
        """Synthesize a complete canonical V2 Assessment object."""
        as_of = as_of_utc or now_utc_iso()
        inp_hash = compute_input_hash(normalized_hotspot, context)
        asm_id = generate_assessment_id(target_id, inp_hash)

        # 1. Classification
        classification_asm: ClassificationAssessment = self.classifier.classify_v2(features)

        # 2. Anomaly
        anomaly_asm: AnomalyAssessment = self.anomaly_detector.detect_v2(
            features, population_features=population_features
        )

        # 3. Composite Risk
        anomaly_res = self.anomaly_detector.detect(features, population_features=population_features)
        risk_asm: RiskAssessmentResult = self.risk_assessor.assess_risk_v2(
            features=features,
            source_type=classification_asm.predicted_source,
            anomaly_result=anomaly_res,
        )

        # 4. Data Quality & Completeness
        data_quality_asm = DataQualityAssessment(
            completeness_score=features.completeness_score,
            uncertainty_score=features.uncertainty_score,
            missing_sources=features.missing_domains,
        )

        # 5. Methodology & Audit Provenance
        methodology_asm = AssessmentMethodology(
            method=METHODOLOGY_V2_COMPOSITE,
            algorithm_version=self.algorithm_version,
            input_hash=inp_hash,
            as_of_utc=as_of,
        )

        return Assessment(
            assessment_id=asm_id,
            target_id=target_id,
            target_type=target_type,
            classification=classification_asm,
            anomaly=anomaly_asm,
            risk=risk_asm,
            data_quality=data_quality_asm,
            methodology=methodology_asm,
            created_at_utc=now_utc_iso(),
        )

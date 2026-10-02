"""ThermalIntel Intelligence and ML Package.

Redesigned for truthful, reproducible, evidence-based operational intelligence.
"""

from .engine import ThermalIntelligenceEngine
from .context import HotspotContext, NormalizedHotspotInput
from .config import ThermalSourceClass, score_to_risk_level
from .features import FeatureExtractor, FeatureVector
from .classifier import ThermalSourceClassifier, ClassificationEvidenceRecord
from .baseline import BaselineEvaluator, BaselineStatus, BaselineEvaluation
from .anomaly import AnomalyDetector
from .risk import RiskAssessor
from .explain import ExplanationGenerator
from .assessment import AssessmentSynthesizer
from .reproducibility import compute_input_hash, generate_assessment_id
from .evaluation import IntelligenceEvaluator, ScenarioCase

__all__ = [
    "ThermalIntelligenceEngine",
    "HotspotContext",
    "NormalizedHotspotInput",
    "ThermalSourceClass",
    "score_to_risk_level",
    "FeatureExtractor",
    "FeatureVector",
    "ThermalSourceClassifier",
    "ClassificationEvidenceRecord",
    "BaselineEvaluator",
    "BaselineStatus",
    "BaselineEvaluation",
    "AnomalyDetector",
    "RiskAssessor",
    "ExplanationGenerator",
    "AssessmentSynthesizer",
    "compute_input_hash",
    "generate_assessment_id",
    "IntelligenceEvaluator",
    "ScenarioCase",
]

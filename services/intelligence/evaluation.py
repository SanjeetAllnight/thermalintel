"""Evaluation and Benchmarking Interface for Thermal Intelligence.

Exposes clean, typed interfaces for Agent G (Replay / Evaluation) to perform:
- Scenario evaluation
- Batch model evaluation
- Historical backtesting
- Accuracy, precision, recall, and risk calibration benchmarking
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from services.api.schemas.common import SourceType, RiskLevel
from services.api.schemas.intelligence import IntelligenceResult
from services.intelligence.context import HotspotContext, NormalizedHotspotInput


@dataclass
class ScenarioCase:
    """A benchmark test scenario with expected ground-truth annotations."""
    case_id: str
    description: str
    hotspot: Dict[str, Any]
    context: Optional[Dict[str, Any]] = None
    expected_source: Optional[SourceType] = None
    expected_risk_level: Optional[RiskLevel] = None
    expected_is_anomaly: Optional[bool] = None
    expected_min_risk_score: Optional[float] = None
    expected_max_risk_score: Optional[float] = None
    tags: List[str] = field(default_factory=list)


@dataclass
class ScenarioEvaluationResult:
    """Individual comparison between actual inference and expected scenario target."""
    case_id: str
    predicted_source: SourceType
    expected_source: Optional[SourceType]
    source_matched: bool
    risk_score: float
    risk_level: RiskLevel
    expected_risk_level: Optional[RiskLevel]
    risk_level_matched: bool
    is_anomaly: bool
    expected_is_anomaly: Optional[bool]
    anomaly_matched: bool
    confidence: float
    duration_ms: float = 0.0


@dataclass
class EvaluationSummaryMetrics:
    """Aggregate benchmark metrics across a scenario suite."""
    total_cases: int
    classification_accuracy: float
    risk_level_concordance: float
    anomaly_concordance: float
    per_class_precision: Dict[str, float] = field(default_factory=dict)
    per_class_recall: Dict[str, float] = field(default_factory=dict)
    mean_confidence: float = 0.0


class IntelligenceEvaluator:
    """Lightweight evaluation harness enabling Agent G to run scenario benchmarks."""

    @classmethod
    def evaluate_case(cls, case: ScenarioCase, engine: Any) -> ScenarioEvaluationResult:
        """Run single scenario case through the intelligence engine and compare against expectations."""
        import time
        t0 = time.perf_counter()
        res: IntelligenceResult = engine.analyze_hotspot(case.hotspot, case.context)
        duration_ms = (time.perf_counter() - t0) * 1000.0

        src_match = (res.classification.predicted_source == case.expected_source) if case.expected_source else True
        risk_match = (res.risk.risk_level == case.expected_risk_level) if case.expected_risk_level else True
        anom_match = (res.anomaly.is_anomaly == case.expected_is_anomaly) if case.expected_is_anomaly is not None else True

        return ScenarioEvaluationResult(
            case_id=case.case_id,
            predicted_source=res.classification.predicted_source,
            expected_source=case.expected_source,
            source_matched=src_match,
            risk_score=res.risk.risk_score,
            risk_level=res.risk.risk_level,
            expected_risk_level=case.expected_risk_level,
            risk_level_matched=risk_match,
            is_anomaly=res.anomaly.is_anomaly,
            expected_is_anomaly=case.expected_is_anomaly,
            anomaly_matched=anom_match,
            confidence=res.classification.confidence,
            duration_ms=round(duration_ms, 2),
        )

    @classmethod
    def evaluate_suite(cls, cases: List[ScenarioCase], engine: Any) -> Tuple[List[ScenarioEvaluationResult], EvaluationSummaryMetrics]:
        """Run a batch of scenarios and aggregate benchmark metrics."""
        results = [cls.evaluate_case(c, engine) for c in cases]
        if not results:
            return [], EvaluationSummaryMetrics(0, 0.0, 0.0, 0.0)

        src_evaluated = [r for r in results if r.expected_source is not None]
        src_acc = (sum(1 for r in src_evaluated if r.source_matched) / len(src_evaluated)) if src_evaluated else 1.0

        risk_evaluated = [r for r in results if r.expected_risk_level is not None]
        risk_acc = (sum(1 for r in risk_evaluated if r.risk_level_matched) / len(risk_evaluated)) if risk_evaluated else 1.0

        anom_evaluated = [r for r in results if r.expected_is_anomaly is not None]
        anom_acc = (sum(1 for r in anom_evaluated if r.anomaly_matched) / len(anom_evaluated)) if anom_evaluated else 1.0

        mean_conf = sum(r.confidence for r in results) / len(results)

        summary = EvaluationSummaryMetrics(
            total_cases=len(results),
            classification_accuracy=round(src_acc, 3),
            risk_level_concordance=round(risk_acc, 3),
            anomaly_concordance=round(anom_acc, 3),
            mean_confidence=round(mean_conf, 3),
        )
        return results, summary

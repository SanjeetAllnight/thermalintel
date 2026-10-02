"""Tests for Agent G Evaluation and Benchmarking Interface."""

import pytest
from services.api.schemas.common import SourceType, RiskLevel
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.evaluation import (
    ScenarioCase,
    IntelligenceEvaluator,
    ScenarioEvaluationResult,
    EvaluationSummaryMetrics,
)


@pytest.fixture
def engine():
    return ThermalIntelligenceEngine()


def test_evaluate_single_case(engine):
    """Verify evaluation of a single annotated scenario case."""
    case = ScenarioCase(
        case_id="EVAL-01-WILDFIRE",
        description="High intensity wildfire scenario",
        hotspot={"id": "OBS-WF-01", "frp": 150.0, "brightness": 370.0, "confidence": "high"},
        context={"land_cover": "coniferous_forest", "wind_speed_kmh": 40.0, "relative_humidity_pct": 12.0},
        expected_source=SourceType.WILDFIRE,
        expected_risk_level=RiskLevel.CRITICAL,
        expected_is_anomaly=True,
    )

    eval_result = IntelligenceEvaluator.evaluate_case(case, engine)
    assert isinstance(eval_result, ScenarioEvaluationResult)
    assert eval_result.case_id == "EVAL-01-WILDFIRE"
    assert eval_result.source_matched is True
    assert eval_result.is_anomaly is True
    assert eval_result.anomaly_matched is True
    assert eval_result.duration_ms > 0.0


def test_evaluate_suite_metrics(engine):
    """Verify aggregate metric calculation across a benchmark suite."""
    cases = [
        ScenarioCase(
            case_id="SUITE-01",
            description="Wildfire test",
            hotspot={"id": "WF-01", "frp": 120.0, "brightness": 360.0},
            context={"land_cover": "forest", "wind_speed_kmh": 35.0},
            expected_source=SourceType.WILDFIRE,
        ),
        ScenarioCase(
            case_id="SUITE-02",
            description="Flare stack test",
            hotspot={"id": "FLARE-01", "frp": 35.0, "brightness": 330.0},
            context={"land_cover": "refinery", "prior_detections_30d": 30, "distance_to_industrial_m": 50.0},
            expected_source=SourceType.INDUSTRIAL,
            expected_is_anomaly=False,
        ),
    ]

    results, summary = IntelligenceEvaluator.evaluate_suite(cases, engine)
    assert len(results) == 2
    assert isinstance(summary, EvaluationSummaryMetrics)
    assert summary.total_cases == 2
    assert summary.classification_accuracy == 1.0
    assert summary.anomaly_concordance == 1.0
    assert summary.mean_confidence > 0.0

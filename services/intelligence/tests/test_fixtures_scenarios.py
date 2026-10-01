"""End-to-end tests for all 10 required operational scenario fixtures."""

import pytest
from services.api.schemas.common import SourceType, RiskLevel
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.tests.fixtures import (
    FIXTURE_POTENTIAL_INDUSTRIAL_FIRE,
    FIXTURE_VEGETATION_FIRE,
    FIXTURE_PERSISTENT_INDUSTRIAL_HEAT,
    FIXTURE_CONTROLLED_HEAT_SOURCE,
    FIXTURE_UNKNOWN_AMBIGUOUS_EVENT,
    FIXTURE_HIGHLY_ANOMALOUS_EVENT,
    FIXTURE_ROUTINE_LOW_RISK_EVENT,
    FIXTURE_MISSING_CONTEXTUAL_DATA,
    FIXTURE_VERY_SMALL_DATASET,
    FIXTURE_SINGLE_HOTSPOT_CASE,
)


@pytest.fixture
def engine():
    return ThermalIntelligenceEngine()


def test_scenario_01_potential_industrial_fire(engine):
    fixture = FIXTURE_POTENTIAL_INDUSTRIAL_FIRE
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.classification.predicted_source == SourceType.INDUSTRIAL
    assert result.risk.risk_score >= 50.0
    assert result.classification.confidence >= 0.70
    assert any("industrial" in f.factor.lower() or "power" in f.factor.lower() for f in result.risk.explainable_factors)


def test_scenario_02_vegetation_fire(engine):
    fixture = FIXTURE_VEGETATION_FIRE
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.classification.predicted_source == SourceType.WILDFIRE
    assert result.risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert result.risk.risk_score >= 65.0
    assert result.anomaly.is_anomaly is True


def test_scenario_03_persistent_industrial_heat(engine):
    fixture = FIXTURE_PERSISTENT_INDUSTRIAL_HEAT
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.classification.predicted_source == SourceType.INDUSTRIAL
    # Flare stack is an operational baseline, anomaly should be suppressed
    assert result.anomaly.is_anomaly is False
    assert result.anomaly.anomaly_score <= 0.30
    assert any("recurrence" in f.factor.lower() for f in result.risk.explainable_factors)


def test_scenario_04_controlled_heat_source(engine):
    fixture = FIXTURE_CONTROLLED_HEAT_SOURCE
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.classification.predicted_source == SourceType.PRESCRIBED_BURN
    assert result.risk.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert result.risk.risk_score < 50.0


def test_scenario_05_unknown_ambiguous_event(engine):
    fixture = FIXTURE_UNKNOWN_AMBIGUOUS_EVENT
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.classification.predicted_source == SourceType.UNKNOWN
    assert result.classification.confidence <= 0.60
    assert result.risk.risk_level == RiskLevel.LOW


def test_scenario_06_highly_anomalous_event(engine):
    fixture = FIXTURE_HIGHLY_ANOMALOUS_EVENT
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.anomaly.is_anomaly is True
    assert result.anomaly.anomaly_score >= 0.85
    assert result.risk.risk_level == RiskLevel.CRITICAL
    assert result.risk.risk_score >= 75.0


def test_scenario_07_routine_low_risk_event(engine):
    fixture = FIXTURE_ROUTINE_LOW_RISK_EVENT
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.risk.risk_level == RiskLevel.LOW
    assert result.risk.risk_score <= 24.0
    assert result.anomaly.is_anomaly is False


def test_scenario_08_missing_contextual_data(engine):
    fixture = FIXTURE_MISSING_CONTEXTUAL_DATA
    result = engine.analyze_hotspot(fixture["hotspot"], fixture["context"])

    assert result.hotspot_id == "SCENARIO-08-MISSING-CONTEXT"
    assert 0.0 <= result.risk.risk_score <= 100.0
    assert result.classification.predicted_source in SourceType
    assert len(result.risk.explainable_factors) >= 2


def test_scenario_09_very_small_dataset(engine):
    results = engine.batch_analyze(FIXTURE_VERY_SMALL_DATASET)

    assert len(results) == 3
    for res in results:
        assert res.anomaly.anomaly_score is not None
        assert 0.0 <= res.risk.risk_score <= 100.0


def test_scenario_10_single_hotspot_case(engine):
    result = engine.analyze_hotspot(FIXTURE_SINGLE_HOTSPOT_CASE)

    assert result.hotspot_id == "SINGLE-STANDALONE-001"
    assert 0.0 <= result.risk.risk_score <= 100.0
    assert result.anomaly.is_anomaly is True

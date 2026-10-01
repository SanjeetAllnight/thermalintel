"""Unit tests for the Risk Scoring subsystem and boundary value analysis."""

import pytest
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.intelligence import AnomalyResult
from services.intelligence.config import score_to_risk_level
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor
from services.intelligence.risk import RiskAssessor


@pytest.fixture
def assessor():
    return RiskAssessor()


def test_risk_severity_boundary_values():
    """Explicitly verify required risk score boundary values:

    0-24 = LOW
    25-49 = MEDIUM
    50-74 = HIGH
    75-100 = CRITICAL
    """
    assert score_to_risk_level(0.0) == RiskLevel.LOW
    assert score_to_risk_level(24.0) == RiskLevel.LOW
    assert score_to_risk_level(24.9) == RiskLevel.LOW

    assert score_to_risk_level(25.0) == RiskLevel.MEDIUM
    assert score_to_risk_level(49.0) == RiskLevel.MEDIUM
    assert score_to_risk_level(49.9) == RiskLevel.MEDIUM

    assert score_to_risk_level(50.0) == RiskLevel.HIGH
    assert score_to_risk_level(74.0) == RiskLevel.HIGH
    assert score_to_risk_level(74.9) == RiskLevel.HIGH

    assert score_to_risk_level(75.0) == RiskLevel.CRITICAL
    assert score_to_risk_level(100.0) == RiskLevel.CRITICAL


def test_separation_of_classification_and_risk(assessor):
    """Verify that POTENTIAL_INDUSTRIAL_FIRE is NOT automatically CRITICAL,

    and UNKNOWN is NOT automatically LOW.
    """
    dummy_anomaly = AnomalyResult(
        is_anomaly=False,
        anomaly_score=0.20,
        baseline_deviation=0.5,
        anomaly_rationale="Baseline normal",
    )

    # 1. Industrial event with low FRP in contained area -> NOT critical
    ind_h = NormalizedHotspotInput(id="LOW-IND", frp=12.0, brightness=310.0, confidence="nominal")
    ind_ctx = HotspotContext(
        distance_to_industrial_m=100.0,
        distance_to_settlement_m=15000.0,
        prior_detections_30d=25,
        is_recurrent_site=True,
    )
    ind_features = FeatureExtractor.extract(ind_h, ind_ctx)
    ind_risk = assessor.assess_risk(ind_features, SourceType.INDUSTRIAL, dummy_anomaly)

    assert ind_risk.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert ind_risk.risk_score < 50.0

    # 2. Unknown event with massive 280 MW thermal radiance next to town -> NOT low
    unk_h = NormalizedHotspotInput(id="HUGE-UNK", frp=280.0, brightness=420.0, confidence="high")
    unk_ctx = HotspotContext(
        distance_to_settlement_m=800.0,
        wind_speed_kmh=45.0,
        relative_humidity_pct=15.0,
    )
    unk_features = FeatureExtractor.extract(unk_h, unk_ctx)
    huge_anomaly = AnomalyResult(
        is_anomaly=True,
        anomaly_score=0.95,
        baseline_deviation=8.0,
        anomaly_rationale="Huge spike",
    )
    unk_risk = assessor.assess_risk(unk_features, SourceType.UNKNOWN, huge_anomaly)

    assert unk_risk.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL)
    assert unk_risk.risk_score >= 65.0


def test_missing_context_dynamic_normalization(assessor):
    """Verify that missing weather and geospatial context does not cause crashes or fabricate high scores."""
    bare_h = NormalizedHotspotInput(id="BARE", frp=20.0, brightness=312.0, confidence="nominal")
    empty_ctx = HotspotContext()
    features = FeatureExtractor.extract(bare_h, empty_ctx)

    dummy_anomaly = AnomalyResult(
        is_anomaly=False,
        anomaly_score=0.15,
        baseline_deviation=0.0,
        anomaly_rationale="Normal",
    )
    risk = assessor.assess_risk(features, SourceType.UNKNOWN, dummy_anomaly)

    assert 0.0 <= risk.risk_score <= 100.0
    assert risk.risk_level in (RiskLevel.LOW, RiskLevel.MEDIUM)
    assert not (risk.risk_score != risk.risk_score)  # Not NaN


def test_composite_risk_components_bounds(assessor):
    h = NormalizedHotspotInput(id="BOUNDS-01", frp=110.0, brightness=360.0)
    ctx = HotspotContext(
        distance_to_settlement_m=1200.0,
        wind_speed_kmh=30.0,
        relative_humidity_pct=20.0,
    )
    features = FeatureExtractor.extract(h, ctx)
    anomaly = AnomalyResult(
        is_anomaly=True,
        anomaly_score=0.80,
        baseline_deviation=4.2,
        anomaly_rationale="Surge",
    )
    risk = assessor.assess_risk(features, SourceType.WILDFIRE, anomaly)

    assert 0.0 <= risk.frp_component <= 100.0
    assert 0.0 <= risk.weather_component <= 100.0
    assert 0.0 <= risk.proximity_component <= 100.0
    assert 0.0 <= risk.historical_component <= 100.0
    assert 0.0 <= risk.risk_score <= 100.0
    assert len(risk.explainable_factors) >= 2
    assert len(risk.recommended_action) > 10


def test_nan_infinity_resilience(assessor):
    """Ensure no NaN, infinity, or division-by-zero can escape into RiskAssessment."""
    h = NormalizedHotspotInput(id="NAN-TEST", frp=float("nan"), brightness=float("inf"))
    ctx = HotspotContext(
        distance_to_settlement_m=float("nan"),
        temperature_c=float("-inf"),
        wind_speed_kmh=float("nan"),
    )
    features = FeatureExtractor.extract(h, ctx)
    anomaly = AnomalyResult(
        is_anomaly=False,
        anomaly_score=0.0,
        baseline_deviation=0.0,
        anomaly_rationale="Safe",
    )
    risk = assessor.assess_risk(features, SourceType.UNKNOWN, anomaly)

    import math
    assert not math.isnan(risk.risk_score)
    assert not math.isinf(risk.risk_score)
    assert not math.isnan(risk.frp_component)
    assert not math.isnan(risk.weather_component)
    assert not math.isnan(risk.proximity_component)
    assert not math.isnan(risk.historical_component)
    assert 0.0 <= risk.risk_score <= 100.0


def test_extreme_risk_clamping(assessor):
    """Test that extreme signals are strictly clamped to [0.0, 100.0]."""
    # Max signals
    h_max = NormalizedHotspotInput(id="MAX-TEST", frp=9999.0, brightness=999.0, confidence="high")
    ctx_max = HotspotContext(
        distance_to_settlement_m=0.0,
        distance_to_infrastructure_m=0.0,
        is_protected_area=True,
        slope_degrees=45.0,
        temperature_c=50.0,
        relative_humidity_pct=0.0,
        wind_speed_kmh=100.0,
    )
    features_max = FeatureExtractor.extract(h_max, ctx_max)
    anomaly_max = AnomalyResult(
        is_anomaly=True,
        anomaly_score=1.0,
        baseline_deviation=20.0,
        anomaly_rationale="Max surge",
    )
    risk_max = assessor.assess_risk(features_max, SourceType.WILDFIRE, anomaly_max)
    assert risk_max.risk_score <= 100.0
    assert risk_max.risk_level == RiskLevel.CRITICAL


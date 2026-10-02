"""Unit tests for the Risk Scoring subsystem and boundary value analysis.

Verifies:
- All 4 component scores and composite risk score remain bounded strictly in [0.0, 100.0].
- Differentiated historical component:
  - Industrial flare recurrence suppresses spread risk.
  - Active wildland fire recurrence increases operational hazard persistence.
- Dynamic normalization when environmental or spatial context is missing.
- NaN, infinity, and negative value resilience.
- Canonical V2 RiskAssessmentResult contract compliance.
"""

import math
import pytest
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.intelligence import AnomalyResult
from services.api.schemas.v2.assessment import RiskAssessmentResult
from services.api.schemas.v2.common import RiskLevel as V2RiskLevel
from services.intelligence.config import score_to_risk_level
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor
from services.intelligence.risk import RiskAssessor


@pytest.fixture
def assessor():
    return RiskAssessor()


@pytest.fixture
def normal_anomaly():
    return AnomalyResult(
        is_anomaly=False,
        anomaly_score=0.15,
        baseline_deviation=0.2,
        anomaly_rationale="Within normal bounds",
    )


def test_risk_severity_boundary_values():
    """Explicitly verify required risk score boundary values:
    0-24.9 = LOW
    25-49.9 = MEDIUM
    50-74.9 = HIGH
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


def test_separation_of_classification_and_risk(assessor, normal_anomaly):
    """Verify that POTENTIAL_INDUSTRIAL_FIRE is NOT automatically CRITICAL,
    and UNKNOWN is NOT automatically LOW.
    """
    # 1. Industrial event with low FRP in contained area -> NOT critical
    ind_h = NormalizedHotspotInput(id="LOW-IND", frp=12.0, brightness=310.0, confidence="nominal")
    ind_ctx = HotspotContext(
        distance_to_industrial_m=100.0,
        distance_to_settlement_m=15000.0,
        prior_detections_30d=25,
        is_recurrent_site=True,
    )
    ind_features = FeatureExtractor.extract(ind_h, ind_ctx)
    ind_risk = assessor.assess_risk(ind_features, SourceType.INDUSTRIAL, normal_anomaly)

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


def test_historical_component_differentiation(assessor, normal_anomaly):
    """Verify that recurrence decreases risk for industrial flaring but increases risk for uncontained wildland fires."""
    # Stationary industrial flare: 30 passes in 30d
    ind_h = NormalizedHotspotInput(id="HIST-IND", frp=35.0, brightness=325.0)
    ind_ctx = HotspotContext(
        land_cover="refinery",
        distance_to_industrial_m=50.0,
        prior_detections_30d=30,
        is_recurrent_site=True,
    )
    ind_risk = assessor.assess_risk(
        FeatureExtractor.extract(ind_h, ind_ctx),
        SourceType.INDUSTRIAL,
        normal_anomaly,
    )

    # Persistent wildland fire: 30 passes in 30d (long-duration uncontained burn)
    wild_h = NormalizedHotspotInput(id="HIST-WILD", frp=35.0, brightness=325.0)
    wild_ctx = HotspotContext(
        land_cover="coniferous_forest",
        distance_to_industrial_m=20000.0,
        prior_detections_30d=30,
        is_recurrent_site=True,
    )
    wild_risk = assessor.assess_risk(
        FeatureExtractor.extract(wild_h, wild_ctx),
        SourceType.WILDFIRE,
        normal_anomaly,
    )

    # Persistent wildfire historical sub-score must be higher than stationary flare
    assert wild_risk.historical_component > ind_risk.historical_component
    assert ind_risk.historical_component == 15.0
    assert wild_risk.historical_component >= 70.0


def test_missing_context_dynamic_normalization(assessor, normal_anomaly):
    """Verify missing weather and geospatial context rebalances weights without fabricating numbers."""
    bare_h = NormalizedHotspotInput(id="BARE", frp=20.0, brightness=312.0, confidence="nominal")
    empty_ctx = HotspotContext()
    features = FeatureExtractor.extract(bare_h, empty_ctx)

    risk = assessor.assess_risk(features, SourceType.UNKNOWN, normal_anomaly)

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


def test_nan_infinity_resilience(assessor, normal_anomaly):
    """Ensure no NaN, infinity, or division-by-zero can escape into RiskAssessment."""
    h = NormalizedHotspotInput(id="NAN-TEST", frp=float("nan"), brightness=float("inf"))
    ctx = HotspotContext(
        distance_to_settlement_m=float("nan"),
        temperature_c=float("-inf"),
        wind_speed_kmh=float("nan"),
    )
    features = FeatureExtractor.extract(h, ctx)
    risk = assessor.assess_risk(features, SourceType.UNKNOWN, normal_anomaly)

    assert not math.isnan(risk.risk_score)
    assert not math.isinf(risk.risk_score)
    assert not math.isnan(risk.frp_component)
    assert not math.isnan(risk.weather_component)
    assert not math.isnan(risk.proximity_component)
    assert not math.isnan(risk.historical_component)
    assert 0.0 <= risk.risk_score <= 100.0


def test_extreme_risk_clamping(assessor):
    """Test that extreme signals are strictly clamped to [0.0, 100.0]."""
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


def test_risk_v2_assessment_contract(assessor, normal_anomaly):
    """Verify assess_risk_v2 returns a valid RiskAssessmentResult conforming to frozen V2 schema."""
    h = NormalizedHotspotInput(id="V2-RISK", frp=75.0, brightness=345.0)
    ctx = HotspotContext(distance_to_settlement_m=2000.0, wind_speed_kmh=25.0)
    features = FeatureExtractor.extract(h, ctx)

    v2_risk = assessor.assess_risk_v2(features, SourceType.WILDFIRE, normal_anomaly)
    assert isinstance(v2_risk, RiskAssessmentResult)
    assert 0.0 <= v2_risk.risk_score <= 100.0
    assert isinstance(v2_risk.severity, (RiskLevel, V2RiskLevel))
    assert len(v2_risk.factors) >= 2
    assert len(v2_risk.recommended_action) > 5

"""Unit tests for the Thermal Source Classifier.

Verifies:
- Every supported class: WILDFIRE, INDUSTRIAL, AGRICULTURAL, PRESCRIBED_BURN, UNKNOWN.
- Rule precedence and evidence accumulation.
- Supporting and opposing evidence generation.
- Rule identifiers and methodology versioning.
- Graceful degradation when context is missing or contradictory.
"""

import pytest
from services.api.schemas.common import SourceType
from services.intelligence.classifier import ThermalSourceClassifier, ClassificationEvidenceRecord
from services.intelligence.config import ThermalSourceClass, ALGORITHM_VERSION, METHODOLOGY_RULE_BASED
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor


@pytest.fixture
def classifier():
    return ThermalSourceClassifier()


def test_classify_vegetation_fire(classifier):
    norm_h = NormalizedHotspotInput(id="VEG-01", frp=135.0, brightness=365.0, confidence="high")
    ctx = HotspotContext(
        land_cover="coniferous_forest",
        distance_to_industrial_m=12000.0,
        temperature_c=30.0,
        relative_humidity_pct=15.0,
        wind_speed_kmh=35.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.WILDFIRE
    assert result.confidence >= 0.70
    assert result.probabilities["VEGETATION_FIRE"] > result.probabilities["POTENTIAL_INDUSTRIAL_FIRE"]
    assert "wildfire" in result.probabilities
    assert result.feature_importance is not None
    assert "fire_radiative_power" in result.feature_importance


def test_classify_potential_industrial_fire(classifier):
    # Intense spike right next to petrochemical refinery with zero prior passes
    norm_h = NormalizedHotspotInput(id="IND-01", frp=150.0, brightness=410.0, confidence="high")
    ctx = HotspotContext(
        land_cover="industrial",
        distance_to_industrial_m=50.0,
        nearby_industrial_count=5,
        prior_detections_30d=1,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.INDUSTRIAL
    assert result.confidence >= 0.75
    assert result.probabilities["POTENTIAL_INDUSTRIAL_FIRE"] > 0.40
    assert "industrial_proximity" in result.feature_importance


def test_classify_persistent_thermal_source(classifier):
    # Known flare stack with 35 prior passes and stable moderate FRP
    norm_h = NormalizedHotspotInput(id="PERSIST-01", frp=35.0, brightness=328.0, confidence="nominal")
    ctx = HotspotContext(
        land_cover="refinery",
        distance_to_industrial_m=100.0,
        nearby_industrial_count=3,
        prior_detections_30d=35,
        is_recurrent_site=True,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.INDUSTRIAL
    assert result.probabilities["PERSISTENT_THERMAL_SOURCE"] > 0.40


def test_classify_controlled_heat_source(classifier):
    # Prescribed burn in national park with moderate FRP
    norm_h = NormalizedHotspotInput(id="CTRL-01", frp=20.0, brightness=315.0, confidence="nominal")
    ctx = HotspotContext(
        land_cover="national_park",
        is_protected_area=True,
        protected_area_name="Yosemite National Park",
        distance_to_industrial_m=40000.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.PRESCRIBED_BURN
    assert result.probabilities["CONTROLLED_HEAT_SOURCE"] > 0.40


def test_classify_agricultural_burn(classifier):
    # Agricultural burn on cropland
    norm_h = NormalizedHotspotInput(id="AGRI-01", frp=16.0, brightness=314.0, confidence="nominal")
    ctx = HotspotContext(
        land_cover="cropland_pasture",
        distance_to_industrial_m=25000.0,
        prior_detections_30d=1,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.AGRICULTURAL
    assert result.probabilities["agricultural"] > 0.20


def test_classify_unknown_when_evidence_weak(classifier):
    # Low FRP, low confidence, zero context
    norm_h = NormalizedHotspotInput(id="UNK-01", frp=5.0, brightness=295.0, confidence="low")
    ctx = HotspotContext()  # Empty context
    features = FeatureExtractor.extract(norm_h, ctx)
    result = classifier.classify(features)

    assert result.predicted_source == SourceType.UNKNOWN
    # Confidence should be constrained for unknown
    assert result.confidence <= 0.60
    assert result.probabilities["UNKNOWN"] >= 0.30


def test_classification_supporting_and_opposing_evidence(classifier):
    """Verify that evaluate_evidence generates both supporting and opposing evidence strings."""
    norm_h = NormalizedHotspotInput(id="EV-01", frp=140.0, brightness=375.0, confidence="high")
    ctx = HotspotContext(
        land_cover="forest",
        distance_to_industrial_m=18000.0,
        temperature_c=32.0,
        relative_humidity_pct=15.0,
        wind_speed_kmh=40.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    evidence: ClassificationEvidenceRecord = classifier.evaluate_evidence(features)

    assert len(evidence.supporting_evidence) >= 2
    assert len(evidence.opposing_evidence) >= 1
    assert evidence.rule_identifier == "RULE_ACTIVE_VEGETATION_WILDFIRE"
    assert evidence.methodology == METHODOLOGY_RULE_BASED
    assert evidence.methodology_version == ALGORITHM_VERSION
    assert any("combustion" in s.lower() or "fuel" in s.lower() or "140" in s for s in evidence.supporting_evidence)


def test_rule_precedence_industrial_over_vegetation(classifier):
    """When high FRP occurs in an industrial plant perimeter, industrial rule takes precedence."""
    norm_h = NormalizedHotspotInput(id="PREC-01", frp=160.0, brightness=400.0, confidence="high")
    ctx = HotspotContext(
        land_cover="heavy_industrial",
        distance_to_industrial_m=80.0,
        nearby_industrial_count=6,
        prior_detections_30d=1,
    )
    features = FeatureExtractor.extract(norm_h, ctx)
    evidence = classifier.evaluate_evidence(features)

    assert evidence.predicted_source == SourceType.INDUSTRIAL
    assert evidence.rule_identifier == "RULE_INDUSTRIAL_HAZARD_SPIKE"


def test_confidence_not_constant(classifier):
    # Complete, high-strength evidence vs. missing weak evidence
    strong_h = NormalizedHotspotInput(id="STRONG", frp=150.0, brightness=370.0, confidence="high")
    strong_ctx = HotspotContext(
        land_cover="dense_forest",
        distance_to_industrial_m=15000.0,
        temperature_c=32.0,
        relative_humidity_pct=15.0,
        wind_speed_kmh=40.0,
        prior_detections_30d=1,
    )
    weak_h = NormalizedHotspotInput(id="WEAK", frp=8.0, brightness=300.0, confidence="low")
    weak_ctx = HotspotContext()

    res_strong = classifier.classify(FeatureExtractor.extract(strong_h, strong_ctx))
    res_weak = classifier.classify(FeatureExtractor.extract(weak_h, weak_ctx))

    assert res_strong.confidence != res_weak.confidence
    assert res_strong.confidence > res_weak.confidence

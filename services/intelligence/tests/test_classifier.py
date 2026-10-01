"""Unit tests for the Thermal Source Classifier."""

import pytest
from services.api.schemas.common import SourceType
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.config import ThermalSourceClass
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

"""Unit tests for the Anomaly Detection subsystem."""

import pytest
from services.intelligence.anomaly import AnomalyDetector
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor


@pytest.fixture
def detector():
    return AnomalyDetector(baseline_frp_mean=25.0, baseline_frp_std=20.0)


def test_statistical_fallback_normal_hotspot(detector):
    # FRP = 25 MW matches baseline mean exactly (deviation = 0.0)
    norm_h = NormalizedHotspotInput(id="NORM-01", frp=25.0, brightness=310.0)
    features = FeatureExtractor.extract(norm_h, HotspotContext())
    result = detector.detect(features)

    assert result.is_anomaly is False
    assert result.anomaly_score < 0.50
    assert result.baseline_deviation == 0.0
    assert "within normal expected variation" in result.anomaly_rationale


def test_statistical_fallback_surge_anomaly(detector):
    # FRP = 145 MW is (145 - 25) / 20 = 6.0 sigma above baseline
    norm_h = NormalizedHotspotInput(id="SURGE-01", frp=145.0, brightness=370.0)
    features = FeatureExtractor.extract(norm_h, HotspotContext())
    result = detector.detect(features)

    assert result.is_anomaly is True
    assert result.anomaly_score >= 0.70
    assert result.baseline_deviation == 6.0
    assert "exceeds" in result.anomaly_rationale or "standard deviations" in result.anomaly_rationale


def test_recurring_flare_suppression(detector):
    # FRP = 35 MW at an industrial site with 30 passes is suppressed
    norm_h = NormalizedHotspotInput(id="FLARE-01", frp=35.0, brightness=325.0)
    ctx = HotspotContext(prior_detections_30d=30, is_recurrent_site=True)
    features = FeatureExtractor.extract(norm_h, ctx)
    result = detector.detect(features)

    assert result.is_anomaly is False
    assert result.anomaly_score <= 0.25
    assert "Recurring site" in result.anomaly_rationale


def test_isolation_forest_population(detector):
    # Population of 8 normal observations + 1 extreme outlier
    pop_raw = [
        {"id": f"P-{i}", "frp": 20.0 + i * 2, "brightness": 305.0 + i}
        for i in range(8)
    ]
    outlier_raw = {"id": "OUTLIER", "frp": 280.0, "brightness": 450.0}

    pop_features = [
        FeatureExtractor.extract(NormalizedHotspotInput.from_input(item), HotspotContext())
        for item in pop_raw + [outlier_raw]
    ]

    outlier_features = FeatureExtractor.extract(
        NormalizedHotspotInput.from_input(outlier_raw),
        HotspotContext(),
    )

    result = detector.detect(outlier_features, population_features=pop_features)
    assert result.is_anomaly is True
    assert result.anomaly_score >= 0.65
    assert 0.0 <= result.anomaly_score <= 1.0


def test_anomaly_detection_determinism(detector):
    norm_h = NormalizedHotspotInput(id="DET-01", frp=95.0, brightness=345.0)
    features = FeatureExtractor.extract(norm_h, HotspotContext())

    run1 = detector.detect(features)
    run2 = detector.detect(features)

    assert run1.is_anomaly == run2.is_anomaly
    assert run1.anomaly_score == run2.anomaly_score
    assert run1.baseline_deviation == run2.baseline_deviation
    assert run1.anomaly_rationale == run2.anomaly_rationale

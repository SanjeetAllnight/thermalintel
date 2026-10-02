"""Comprehensive unit tests for the Historical / Site Baseline Layer."""

import math
import pytest
from services.intelligence.baseline import (
    BaselineEvaluator,
    BaselineStatus,
    BaselineEvaluation,
)
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor


@pytest.fixture
def evaluator():
    return BaselineEvaluator(baseline_frp_mean=25.0, baseline_frp_std=20.0, sigma_threshold=2.0)


def test_baseline_insufficient_history(evaluator):
    """When no historical passes exist within 1km, status must be NO_BASELINE."""
    norm_h = NormalizedHotspotInput(id="NEW-SITE", frp=30.0, brightness=310.0)
    ctx = HotspotContext(prior_detections_30d=None, prior_detections_90d=None, is_recurrent_site=False)
    features = FeatureExtractor.extract(norm_h, ctx)

    eval_res = evaluator.evaluate_site_baseline(features)
    assert eval_res.status == BaselineStatus.NO_BASELINE
    assert eval_res.has_sufficient_history is False
    assert eval_res.deviation_sigma is not None
    assert 0.0 <= eval_res.anomaly_score <= 1.0


def test_baseline_sufficient_history_normal(evaluator):
    """A recurring industrial flare operating within routine historical levels must be NORMAL."""
    norm_h = NormalizedHotspotInput(id="FLARE-NORM", frp=35.0, brightness=325.0)
    ctx = HotspotContext(
        prior_detections_30d=28,
        prior_detections_90d=80,
        is_recurrent_site=True,
        land_cover="industrial",
        distance_to_industrial_m=50.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)

    eval_res = evaluator.evaluate_site_baseline(features)
    assert eval_res.status == BaselineStatus.NORMAL
    assert eval_res.is_anomaly is False
    assert eval_res.has_sufficient_history is True
    assert eval_res.anomaly_score <= 0.30
    assert "Recurring site" in eval_res.rationale


def test_baseline_sufficient_history_abnormal_surge(evaluator):
    """A sudden extreme surge at a recurring site must be flagged ABNORMAL."""
    norm_h = NormalizedHotspotInput(id="FLARE-SURGE", frp=180.0, brightness=420.0)
    ctx = HotspotContext(
        prior_detections_30d=25,
        is_recurrent_site=True,
        land_cover="refinery",
        distance_to_industrial_m=60.0,
    )
    features = FeatureExtractor.extract(norm_h, ctx)

    eval_res = evaluator.evaluate_site_baseline(features)
    assert eval_res.status == BaselineStatus.ABNORMAL
    assert eval_res.is_anomaly is True
    assert eval_res.anomaly_score >= 0.65
    assert "Unprecedented radiance spike" in eval_res.rationale


def test_baseline_zero_variance_identical_samples(evaluator):
    """When std == 0.0 and observation matches mean, must not divide by zero and return deviation = 0.0."""
    norm_h = NormalizedHotspotInput(id="ZERO-VAR-SAME", frp=40.0, brightness=320.0)
    features = FeatureExtractor.extract(norm_h, HotspotContext())

    eval_res = evaluator.evaluate_site_baseline(
        features,
        custom_baseline_mean=40.0,
        custom_baseline_std=0.0,
    )
    assert eval_res.status == BaselineStatus.NORMAL
    assert eval_res.deviation_sigma == 0.0
    assert eval_res.is_anomaly is False
    assert eval_res.anomaly_score == 0.0
    assert "Zero-variance" in eval_res.rationale


def test_baseline_zero_variance_divergent_sample(evaluator):
    """When std == 0.0 and observation differs from mean, must not divide by zero and handle gracefully."""
    norm_h = NormalizedHotspotInput(id="ZERO-VAR-DIFF", frp=120.0, brightness=380.0)
    features = FeatureExtractor.extract(norm_h, HotspotContext())

    eval_res = evaluator.evaluate_site_baseline(
        features,
        custom_baseline_mean=40.0,
        custom_baseline_std=0.0,
    )
    assert not math.isnan(eval_res.deviation_sigma)
    assert not math.isinf(eval_res.deviation_sigma)
    assert eval_res.status == BaselineStatus.ABNORMAL
    assert eval_res.is_anomaly is True


def test_baseline_missing_frp(evaluator):
    """When FRP is None or NaN, must cleanly degrade without crashing."""
    norm_h = NormalizedHotspotInput(id="NO-FRP", frp=0.0, brightness=300.0)
    # Simulate None FRP
    features = FeatureExtractor.extract(norm_h, HotspotContext())
    features.frp = None

    eval_res = evaluator.evaluate_site_baseline(features)
    assert eval_res.status == BaselineStatus.NO_BASELINE
    assert eval_res.deviation_sigma == 0.0
    assert eval_res.is_anomaly is False
    assert "unavailable" in eval_res.rationale.lower()


def test_baseline_detection_frequency_calculation(evaluator):
    """Verify detection frequency per day is calculated accurately."""
    norm_h = NormalizedHotspotInput(id="FREQ-01", frp=30.0, brightness=315.0)
    ctx = HotspotContext(prior_detections_30d=15)
    features = FeatureExtractor.extract(norm_h, ctx)

    eval_res = evaluator.evaluate_site_baseline(features)
    assert eval_res.detection_frequency_per_day == 0.50  # 15 / 30
    assert eval_res.frp_percentile is not None
    assert 0.0 <= eval_res.frp_percentile <= 1.0

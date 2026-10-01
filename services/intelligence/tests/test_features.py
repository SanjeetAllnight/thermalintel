"""Unit tests for feature extraction and normalization."""

import pytest
from services.api.schemas.hotspot import Hotspot
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor, FeatureVector


def test_feature_extraction_from_dict():
    raw_hotspot = {
        "id": "HOTSPOT-TEST-01",
        "frp": 120.0,
        "brightness": 350.0,
        "confidence": "high",
        "daynight": "N",
    }
    raw_ctx = {
        "land_cover": "coniferous_forest",
        "distance_to_settlement_m": 1500.0,
        "wind_speed_kmh": 35.0,
        "relative_humidity_pct": 20.0,
        "temperature_c": 28.0,
        "prior_detections_30d": 2,
    }
    norm_h = NormalizedHotspotInput.from_input(raw_hotspot)
    ctx = HotspotContext.from_dict(raw_ctx)
    features = FeatureExtractor.extract(norm_h, ctx)

    assert features.hotspot_id == "HOTSPOT-TEST-01"
    assert features.frp == 120.0
    assert features.brightness == 350.0
    assert features.is_night is True
    assert features.satellite_confidence == 0.95
    assert features.is_vegetation_land_cover is True
    assert features.has_thermal is True
    assert features.has_geospatial is True
    assert features.has_weather is True
    assert features.has_history is True
    assert 0.0 <= features.frp_norm <= 1.0
    assert 0.0 <= features.brightness_norm <= 1.0
    assert 0.0 <= features.settlement_proximity_score <= 1.0
    assert 0.0 <= features.fire_weather_score <= 1.0


def test_feature_extraction_from_hotspot_model():
    h = Hotspot(
        id="MODEL-HOTSPOT-01",
        latitude=34.0,
        longitude=-118.0,
        brightness=320.0,
        acq_date="2026-10-01",
        acq_time="1200",
        satellite="Suomi-NPP",
        confidence="nominal",
        frp=45.0,
        daynight="D",
        risk_score=50.0,
        risk_level="medium",
        last_updated="2026-10-01T12:05:00Z",
    )
    norm_h = NormalizedHotspotInput.from_input(h)
    features = FeatureExtractor.extract(norm_h, HotspotContext())

    assert features.hotspot_id == "MODEL-HOTSPOT-01"
    assert features.frp == 45.0
    assert features.is_night is False
    assert features.has_weather is False
    assert features.has_geospatial is False
    assert features.has_history is False
    assert features.fire_weather_score is None


def test_feature_normalization_edge_cases():
    # Test zero, negative, and extreme FRP
    zero_h = NormalizedHotspotInput(id="ZERO-FRP", frp=0.0, brightness=280.0)
    feat_zero = FeatureExtractor.extract(zero_h)
    assert feat_zero.frp == 0.0
    assert feat_zero.frp_norm == 0.0
    assert feat_zero.brightness_norm == 0.0

    neg_h = NormalizedHotspotInput(id="NEG-FRP", frp=-10.0, brightness=-50.0)
    feat_neg = FeatureExtractor.extract(neg_h)
    assert feat_neg.frp == 0.0
    assert feat_neg.frp_norm == 0.0
    assert feat_neg.brightness_norm == 0.0

    huge_h = NormalizedHotspotInput(id="HUGE-FRP", frp=1500.0, brightness=600.0)
    feat_huge = FeatureExtractor.extract(huge_h)
    assert feat_huge.frp_norm == 1.0
    assert feat_huge.brightness_norm == 1.0


def test_proximity_normalization():
    # Distance <= immediate_dist (1500m for settlement) -> 1.0
    ctx_close = HotspotContext(distance_to_settlement_m=500.0)
    feat_close = FeatureExtractor.extract(NormalizedHotspotInput(id="P1", frp=10.0, brightness=300.0), ctx_close)
    assert feat_close.settlement_proximity_score == 1.0

    # Distance >= max_dist (7500m) -> 0.0
    ctx_far = HotspotContext(distance_to_settlement_m=10000.0)
    feat_far = FeatureExtractor.extract(NormalizedHotspotInput(id="P2", frp=10.0, brightness=300.0), ctx_far)
    assert feat_far.settlement_proximity_score == 0.0


def test_ml_vector_conversion():
    norm_h = NormalizedHotspotInput(id="VEC-01", frp=50.0, brightness=330.0)
    ctx = HotspotContext(land_cover="forest", temperature_c=25.0, wind_speed_kmh=20.0)
    features = FeatureExtractor.extract(norm_h, ctx)
    vec = features.to_ml_vector()

    assert len(vec) == 8
    assert all(isinstance(v, (int, float)) for v in vec)
    assert all(not (v != v) for v in vec)  # No NaN values

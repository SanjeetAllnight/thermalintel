"""Unit and integration tests for ThermalIntelligenceEngine."""

import pytest
from services.api.schemas.intelligence import IntelligenceResult
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.context import HotspotContext


@pytest.fixture
def engine():
    return ThermalIntelligenceEngine()


def test_analyze_hotspot_returns_valid_schema(engine):
    hotspot_data = {
        "id": "VIIRS-SNPP-20261001-001",
        "latitude": 38.7421,
        "longitude": -122.8105,
        "brightness": 352.4,
        "frp": 142.8,
        "confidence": "high",
        "daynight": "N",
    }
    context_data = {
        "land_cover": "dense_coniferous_forest",
        "distance_to_settlement_m": 1200.0,
        "distance_to_infrastructure_m": 450.0,
        "temperature_celsius": 29.4,
        "relative_humidity_percent": 14.0,
        "wind_speed_kmh": 38.5,
        "prior_detections_30d": 1,
    }

    result = engine.analyze_hotspot(hotspot_data, context_data)

    assert isinstance(result, IntelligenceResult)
    assert result.hotspot_id == "VIIRS-SNPP-20261001-001"
    assert result.classification.predicted_source.value == "wildfire"
    assert result.classification.confidence >= 0.70
    assert result.anomaly.is_anomaly is True
    assert result.risk.risk_score >= 50.0
    assert len(result.risk.explainable_factors) >= 2
    assert result.model_version is not None
    assert result.evaluated_at is not None


def test_batch_analyze(engine):
    hotspots = [
        {"id": f"BATCH-{i}", "frp": 15.0 + i * 5, "brightness": 310.0 + i * 2}
        for i in range(6)
    ]
    results = engine.batch_analyze(hotspots)

    assert len(results) == 6
    for i, res in enumerate(results):
        assert isinstance(res, IntelligenceResult)
        assert res.hotspot_id == f"BATCH-{i}"
        assert 0.0 <= res.risk.risk_score <= 100.0


def test_evaluate_hotspot_backwards_compatibility(engine):
    """Verify that the Phase 0 signature evaluate_hotspot still functions exactly as expected."""
    result = engine.evaluate_hotspot(
        hotspot_id="VIIRS-SNPP-001",
        frp=125.0,
        brightness=350.0,
        land_cover="dense_forest",
        historical_recurrence=1,
        is_protected_area=False,
        wind_speed_kmh=40.0,
        relative_humidity_percent=15.0,
        temperature_celsius=30.0,
        distance_to_settlement_m=1200.0,
        distance_to_infra_m=500.0,
        slope_degrees=25.0,
    )

    assert isinstance(result, IntelligenceResult)
    assert result.hotspot_id == "VIIRS-SNPP-001"
    assert result.classification.predicted_source.value == "wildfire"
    assert result.risk.risk_score >= 50.0


def test_deterministic_repeated_runs(engine):
    hotspot_data = {"id": "REPRO-01", "frp": 60.0, "brightness": 335.0}
    context_data = {"land_cover": "forest", "prior_detections_30d": 3}

    res1 = engine.analyze_hotspot(hotspot_data, context_data)
    res2 = engine.analyze_hotspot(hotspot_data, context_data)

    assert res1.classification.predicted_source == res2.classification.predicted_source
    assert res1.classification.confidence == res2.classification.confidence
    assert res1.anomaly.is_anomaly == res2.anomaly.is_anomaly
    assert res1.anomaly.anomaly_score == res2.anomaly.anomaly_score
    assert res1.risk.risk_score == res2.risk.risk_score
    assert res1.risk.risk_level == res2.risk.risk_level

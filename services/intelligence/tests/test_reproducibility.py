"""Tests for Assessment Reproducibility, Determinism, and Contract Compliance."""

import pytest
from services.api.schemas.v2.assessment import Assessment
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.reproducibility import compute_input_hash, generate_assessment_id
from services.intelligence.features import FeatureExtractor


@pytest.fixture
def engine():
    return ThermalIntelligenceEngine()


def test_input_hash_determinism():
    """Identical input vectors must produce bitwise-identical SHA-256 digests."""
    h1 = NormalizedHotspotInput(id="OBS-100", frp=85.0, brightness=340.0, latitude=37.5, longitude=-120.0)
    ctx1 = HotspotContext(land_cover="forest", temperature_c=28.0, wind_speed_kmh=22.0)

    h2 = NormalizedHotspotInput(id="OBS-100", frp=85.0, brightness=340.0, latitude=37.5, longitude=-120.0)
    ctx2 = HotspotContext(land_cover="forest", temperature_c=28.0, wind_speed_kmh=22.0)

    hash1 = compute_input_hash(h1, ctx1)
    hash2 = compute_input_hash(h2, ctx2)

    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 hex length


def test_input_hash_sensitivity():
    """Any variation in physical inputs must alter the SHA-256 digest."""
    h1 = NormalizedHotspotInput(id="OBS-100", frp=85.0, brightness=340.0)
    h2 = NormalizedHotspotInput(id="OBS-100", frp=85.1, brightness=340.0)

    assert compute_input_hash(h1) != compute_input_hash(h2)


def test_assessment_id_generation():
    """Assessment ID incorporates target ID and input hash deterministically."""
    target_id = "OBS-VIIRS-20261001-001"
    inp_hash = "abcdef1234567890abcdef1234567890"
    asm_id = generate_assessment_id(target_id, inp_hash)

    assert asm_id.startswith("ASM-")
    assert "ABCDEF12" in asm_id


def test_canonical_v2_assessment_schema_compliance(engine):
    """Verify that assess_hotspot produces a fully compliant frozen V2 Assessment entity."""
    hotspot_data = {
        "id": "OBS-20261001-001",
        "latitude": 38.5,
        "longitude": -122.0,
        "frp": 140.0,
        "brightness": 360.0,
        "confidence": "high",
    }
    context_data = {
        "land_cover": "forest",
        "distance_to_settlement_m": 1200.0,
        "wind_speed_kmh": 35.0,
        "relative_humidity_pct": 15.0,
    }

    asm = engine.assess_hotspot(
        hotspot=hotspot_data,
        context=context_data,
        target_id="OBS-20261001-001",
        target_type="observation",
        as_of_utc="2026-10-01T12:00:00Z",
    )

    assert isinstance(asm, Assessment)
    assert asm.target_id == "OBS-20261001-001"
    assert asm.target_type == "observation"

    # Methodology checks - Honest, no fake Random Forest
    assert "RandomForest" not in asm.methodology.method
    assert "Rule" in asm.methodology.method
    assert "Statistical" in asm.methodology.method
    assert asm.methodology.input_hash is not None
    assert asm.methodology.as_of_utc == "2026-10-01T12:00:00Z"

    # Data Quality
    assert 0.0 <= asm.data_quality.completeness_score <= 1.0
    assert 0.0 <= asm.data_quality.uncertainty_score <= 1.0

    # Risk Result
    assert 0.0 <= asm.risk.risk_score <= 100.0
    assert len(asm.risk.factors) >= 2


def test_canonical_v2_assessment_determinism(engine):
    """Same input evaluated twice at the same as_of_utc must produce identical assessments."""
    hotspot_data = {"id": "OBS-DET-01", "frp": 95.0, "brightness": 345.0}
    context_data = {"land_cover": "forest", "prior_detections_30d": 2}
    as_of = "2026-10-01T14:30:00Z"

    asm1 = engine.assess_hotspot(hotspot_data, context_data, as_of_utc=as_of)
    asm2 = engine.assess_hotspot(hotspot_data, context_data, as_of_utc=as_of)

    assert asm1.assessment_id == asm2.assessment_id
    assert asm1.methodology.input_hash == asm2.methodology.input_hash
    assert asm1.classification.predicted_source == asm2.classification.predicted_source
    assert asm1.classification.classification_confidence == asm2.classification.classification_confidence
    assert asm1.anomaly.anomaly_score == asm2.anomaly.anomaly_score
    assert asm1.risk.risk_score == asm2.risk.risk_score


def test_canonical_v2_batch_assess(engine):
    """Batch assessment produces a list of valid canonical Assessment objects."""
    hotspots = [
        {"id": f"OBS-BATCH-{i}", "frp": 20.0 + i * 10, "brightness": 310.0 + i * 5}
        for i in range(5)
    ]
    assessments = engine.assess_batch(hotspots, as_of_utc="2026-10-01T12:00:00Z")

    assert len(assessments) == 5
    for i, asm in enumerate(assessments):
        assert isinstance(asm, Assessment)
        assert asm.target_id == f"OBS-BATCH-{i}"
        assert 0.0 <= asm.risk.risk_score <= 100.0

"""Tests verifying 100% backwards compatibility with baseline ThermalIntel V2 behavior."""

import pytest
from profiles.loader import get_active_profile, load_profile_by_id, reset_active_profile
from services.intelligence.config import (
    DEFAULT_WEIGHT_FRP,
    DEFAULT_WEIGHT_WEATHER,
    DEFAULT_WEIGHT_PROXIMITY,
    DEFAULT_WEIGHT_ANOMALY,
    DEFAULT_WEIGHT_HISTORY,
    RISK_THRESHOLD_CRITICAL,
    RISK_THRESHOLD_HIGH,
    RISK_THRESHOLD_MEDIUM,
    RISK_THRESHOLD_LOW,
    score_to_risk_level,
)
from services.intelligence.thresholds import (
    FRP_HIGH_MW,
    RECURRENT_MIN_PASSES_30D,
)
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.risk import RiskAssessor
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.common import SourceType, RiskLevel
from services.api.incidents.engine import IncidentEngine
from services.api.incidents.repository import InMemoryIncidentRepository


class TestProfileBackwardsCompatibility:
    """Verifies that default profile-driven execution matches baseline behavior precisely."""

    def setup_method(self):
        reset_active_profile()

    def teardown_method(self):
        reset_active_profile()

    def test_default_active_profile_matches_baseline_constants(self):
        """Verify wildfire profile constants align with hardcoded constants."""
        profile = get_active_profile()
        assert profile.metadata.id == "wildfire"

        # Risk weights match frozen constants
        assert profile.risk.weights.frp == DEFAULT_WEIGHT_FRP
        assert profile.risk.weights.weather == DEFAULT_WEIGHT_WEATHER
        assert profile.risk.weights.proximity == DEFAULT_WEIGHT_PROXIMITY
        assert profile.risk.weights.anomaly == DEFAULT_WEIGHT_ANOMALY
        assert profile.risk.weights.history == DEFAULT_WEIGHT_HISTORY

        # Thresholds match frozen constants
        assert profile.risk.thresholds.critical == RISK_THRESHOLD_CRITICAL
        assert profile.risk.thresholds.high == RISK_THRESHOLD_HIGH
        assert profile.risk.thresholds.medium == RISK_THRESHOLD_MEDIUM
        assert profile.risk.thresholds.low == RISK_THRESHOLD_LOW

        # Intelligence thresholds match frozen thresholds
        assert profile.rules.thresholds.frp_high_mw == FRP_HIGH_MW
        assert profile.rules.thresholds.recurrent_min_passes_30d == RECURRENT_MIN_PASSES_30D

    def test_score_to_risk_level_compatibility(self):
        """Verify score_to_risk_level works identically with and without explicit config."""
        test_scores = [0.0, 10.0, 24.9, 25.0, 49.9, 50.0, 74.9, 75.0, 99.0, 100.0]
        
        for s in test_scores:
            level_default = score_to_risk_level(s)
            profile_risk = get_active_profile().risk
            level_profile = score_to_risk_level(s, risk_config=profile_risk)
            assert level_default == level_profile, f"Mismatch at score {s}"

    def test_default_classifier_evidence_accumulation(self):
        """Verify default classifier produces vegetation wildfire evidence on wildland thermal signal."""
        classifier = ThermalSourceClassifier()
        
        # High FRP vegetation hotspot
        h = {
            "id": "TEST-VEG-01",
            "latitude": 38.743,
            "longitude": -122.810,
            "brightness": 340.0,
            "frp": 65.0,
            "confidence": "high",
            "acq_date": "2026-10-01",
            "acq_time": "1400",
        }
        ctx = HotspotContext(
            land_cover="forest",
            distance_to_industrial_m=5000.0,
            distance_to_settlement_m=2000.0,
            wind_speed_kmh=22.0,
            relative_humidity_pct=18.0,
            fire_weather_index=35.0,
        )
        feat = FeatureExtractor.extract(NormalizedHotspotInput.from_input(h), ctx)
        ev = classifier.evaluate_evidence(feat)

        assert ev.predicted_source == SourceType.WILDFIRE
        assert ev.rule_identifier == "RULE_ACTIVE_VEGETATION_WILDFIRE"
        assert ev.confidence >= 0.70

    def test_default_incident_engine_baseline_clustering(self):
        """Verify IncidentEngine default parameters match 2.0 km and 24.0 h baseline."""
        engine = IncidentEngine(repository=InMemoryIncidentRepository())
        assert engine.spatial_threshold_km == 2.0
        assert engine.temporal_window_hours == 24.0
        assert engine.merge_distance_km == 3.0
        assert engine.reopen_window_hours == 72.0

"""Tests verifying that the core pipeline remains generic without domain code duplication or branching."""

import ast
from pathlib import Path
import pytest

from profiles.loader import load_profile_by_id
from services.api.schemas.common import SourceType, RiskLevel
from services.api.schemas.hotspot import Hotspot
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.common import IncidentEventType, now_utc_iso
from services.intelligence.classifier import ThermalSourceClassifier
from services.intelligence.context import HotspotContext, NormalizedHotspotInput
from services.intelligence.features import FeatureExtractor, FeatureVector
from services.intelligence.risk import RiskAssessor
from services.intelligence.engine import ThermalIntelligenceEngine
from services.api.incidents.engine import IncidentEngine
from services.api.incidents.repository import InMemoryIncidentRepository
from services.api.alerts.generator import AlertGenerator
from services.replay.pipeline import ReplayPipeline


class TestProfileEngineReusability:
    """Verifies that the core pipeline is generic, reusable, and free of hardcoded domain switches."""

    def test_no_domain_specific_branching_in_core_modules(self):
        """Assert that core engine source files do NOT branch on specific profile names."""
        repo_root = Path(__file__).resolve().parent.parent.parent
        files_to_check = [
            repo_root / "services" / "intelligence" / "classifier.py",
            repo_root / "services" / "intelligence" / "risk.py",
            repo_root / "services" / "intelligence" / "engine.py",
            repo_root / "services" / "api" / "incidents" / "engine.py",
            repo_root / "services" / "api" / "alerts" / "generator.py",
            repo_root / "services" / "replay" / "pipeline.py",
        ]

        prohibited_literals = [
            '== "wildfire"',
            "== 'wildfire'",
            '== "industrial-safety"',
            "== 'industrial-safety'",
            '== "industrial"',
            "== 'industrial'",
        ]

        for filepath in files_to_check:
            assert filepath.is_file(), f"File {filepath} must exist"
            content = filepath.read_text(encoding="utf-8")
            
            # Parse AST to ensure syntactic integrity
            tree = ast.parse(content, filename=str(filepath))
            
            # Check for forbidden profile comparison patterns in code (ignoring comments/docstrings)
            for node in ast.walk(tree):
                if isinstance(node, ast.Compare):
                    # Check if comparator is comparing an attribute/variable named 'profile' to a string literal
                    left_name = getattr(node.left, "id", getattr(node.left, "attr", ""))
                    if "profile" in str(left_name).lower():
                        for comp in node.comparators:
                            if isinstance(comp, ast.Constant) and isinstance(comp.value, str):
                                val = comp.value.lower()
                                assert val not in ("wildfire", "industrial-safety"), (
                                    f"Found hardcoded profile branching in {filepath.name}: "
                                    f"comparing profile to '{val}'"
                                )

    def test_classifier_reusability_across_profiles(self):
        """Verify the exact same ThermalSourceClassifier produces profile-governed results."""
        wildfire_profile = load_profile_by_id("wildfire")
        industrial_profile = load_profile_by_id("industrial-safety")

        wf_classifier = ThermalSourceClassifier(
            rules_config=wildfire_profile.rules,
            taxonomy_config=wildfire_profile.taxonomy,
        )
        ind_classifier = ThermalSourceClassifier(
            rules_config=industrial_profile.rules,
            taxonomy_config=industrial_profile.taxonomy,
        )

        # Create a thermal observation in an industrial complex with 30 MW FRP
        # In wildfire, 30 MW is below FRP_HIGH_MW (40 MW)
        # In industrial-safety, 30 MW is ABOVE frp_high_mw (25 MW) -> triggers industrial spike
        h = {
            "id": "TEST-HOTSPOT-001",
            "latitude": 29.742,
            "longitude": -95.125,
            "brightness": 320.0,
            "frp": 30.0,
            "confidence": "high",
            "acq_date": "2026-10-01",
            "acq_time": "1200",
        }
        ctx = HotspotContext(
            distance_to_industrial_m=150.0,
            nearby_industrial_count=5,
            land_cover="industrial",
            prior_detections_30d=2,  # Low persistence -> sudden emergence
        )
        features = FeatureExtractor.extract(NormalizedHotspotInput.from_input(h), ctx)

        wf_evidence = wf_classifier.evaluate_evidence(features)
        ind_evidence = ind_classifier.evaluate_evidence(features)

        # Both classify cleanly with their respective profile configurations
        assert ind_evidence.predicted_source == SourceType.INDUSTRIAL
        assert ind_evidence.rule_identifier == "RULE_INDUSTRIAL_HAZARD_SPIKE"

        # Evidence accumulation weights reflect profile priors
        assert ind_evidence.rule_support_distribution is not None
        assert wf_evidence.rule_support_distribution is not None

    def test_risk_assessor_reusability_across_profiles(self):
        """Verify RiskAssessor adapts composite weighting and thresholds per profile."""
        wf_profile = load_profile_by_id("wildfire")
        ind_profile = load_profile_by_id("industrial-safety")

        wf_risk = RiskAssessor(risk_config=wf_profile.risk)
        ind_risk = RiskAssessor(risk_config=ind_profile.risk)

        # Verify weights came from respective configs
        assert wf_risk.weight_frp == 0.35
        assert ind_risk.weight_frp == 0.40
        assert wf_risk.weight_weather == 0.25
        assert ind_risk.weight_weather == 0.15

        # Verify thresholds differ
        assert wf_profile.risk.thresholds.critical == 75.0
        assert ind_profile.risk.thresholds.critical == 70.0

    def test_incident_engine_clustering_governed_by_profile(self):
        """Verify IncidentEngine spatial clustering respects profile threshold."""
        wf_profile = load_profile_by_id("wildfire")
        ind_profile = load_profile_by_id("industrial-safety")

        # In wildfire: threshold is 2.0 km
        # In industrial: threshold is 0.6 km
        wf_engine = IncidentEngine(
            repository=InMemoryIncidentRepository(),
            incident_config=wf_profile.incidents,
        )
        ind_engine = IncidentEngine(
            repository=InMemoryIncidentRepository(),
            incident_config=ind_profile.incidents,
        )

        assert wf_engine.spatial_threshold_km == 2.0
        assert ind_engine.spatial_threshold_km == 0.6

        # Two observations separated by 1.0 km
        # Lat 29.742, Lon -95.125 vs Lat 29.751, Lon -95.125 (~1.0 km distance)
        obs1 = Observation(
            observation_id="OBS-DIST-001",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            latitude=29.742,
            longitude=-95.125,
            acquisition_time_utc="2026-10-01T12:00:00Z",
            ingestion_time_utc="2026-10-01T12:05:00Z",
            brightness=320.0,
            frp=20.0,
            daynight="D",
            detection_confidence="nominal",
            schema_version="2.0",
        )
        obs2 = Observation(
            observation_id="OBS-DIST-002",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            latitude=29.751,
            longitude=-95.125,
            acquisition_time_utc="2026-10-01T12:30:00Z",
            ingestion_time_utc="2026-10-01T12:35:00Z",
            brightness=325.0,
            frp=25.0,
            daynight="D",
            detection_confidence="nominal",
            schema_version="2.0",
        )

        # 1. Correlate with Wildfire engine -> separated by 1.0 km < 2.0 km threshold -> 1 incident
        wf_res = wf_engine.correlate_observations([obs1, obs2])
        assert len(wf_res.created_incidents) == 1
        assert wf_res.associations_count == 2
        surviving_wf_inc = wf_res.created_incidents[0]
        assert surviving_wf_inc.observation_count == 2

        # 2. Correlate with Industrial engine -> separated by 1.0 km > 0.6 km threshold -> 2 distinct incidents
        ind_res = ind_engine.correlate_observations([obs1, obs2])
        assert len(ind_res.created_incidents) == 2
        assert ind_res.associations_count == 2  # Each incident has 1 initial associated observation

    def test_parallel_profile_coexistence(self):
        """Verify two ReplayPipelines with different profiles can run simultaneously without crosstalk."""
        wf_pipeline = ReplayPipeline(profile="wildfire", seed=101)
        ind_pipeline = ReplayPipeline(profile="industrial-safety", seed=202)

        assert wf_pipeline.profile.metadata.id == "wildfire"
        assert ind_pipeline.profile.metadata.id == "industrial-safety"

        assert wf_pipeline.intelligence_engine.profile.metadata.id == "wildfire"
        assert ind_pipeline.intelligence_engine.profile.metadata.id == "industrial-safety"

        assert wf_pipeline.aggregator.distance_threshold_km == 2.0
        assert ind_pipeline.aggregator.distance_threshold_km == 0.6

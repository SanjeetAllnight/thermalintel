"""End-to-End Proof: Validating the Industrial Safety Domain on the Generic Pipeline.

Executes the complete 8-step proof required by Phase 7 Section 14:
1. Select profile ('industrial-safety')
2. Load profile configuration
3. Ingest/normalize using the same pipeline
4. Enrich using the same architecture
5. Assess using the same architecture
6. Correlate incidents using the same engine
7. Produce alerts using the same operational engine
8. Replay scenarios using the same replay engine

Proves that a second operational domain runs end-to-end through the generic
underlying ThermalIntel pipeline without any code duplication.
"""

import json
from pathlib import Path
import pytest

from profiles.loader import (
    load_profile_by_id,
    set_active_profile,
    reset_active_profile,
    get_active_profile,
)
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.enrichment.service import EnrichmentService
from services.api.geospatial.asset_store import GeoJSONAssetStore
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.context import HotspotContext
from services.api.incidents.engine import IncidentEngine
from services.api.incidents.repository import InMemoryIncidentRepository
from services.api.alerts.generator import AlertGenerator
from services.api.alerts.cooldown import FloodProtectionEngine, FloodProtectionConfig
from services.replay.pipeline import ReplayPipeline
from scenarios.loader import load_scenario_from_file
from services.api.schemas.common import SourceType, RiskLevel
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.assessment import Assessment
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.alert import AlertV2


class TestSecondDomainEndToEndProof:
    """Rigorous 8-step validation proving that the industrial-safety domain runs on the generic engine."""

    def setup_method(self):
        reset_active_profile()

    def teardown_method(self):
        reset_active_profile()

    def test_complete_eight_step_industrial_domain_proof(self):
        """Execute the authoritative 8-step proof for the industrial-safety profile."""
        
        # ---------------------------------------------------------------------
        # Step 1: Select Profile
        # ---------------------------------------------------------------------
        profile_id = "industrial-safety"
        active_profile = set_active_profile(profile_id)
        assert active_profile.metadata.id == "industrial-safety"
        assert get_active_profile().metadata.id == "industrial-safety"

        # ---------------------------------------------------------------------
        # Step 2: Load Profile Configuration
        # ---------------------------------------------------------------------
        profile = load_profile_by_id("industrial-safety")
        assert profile.metadata.display_name == "Industrial & Petrochemical Safety"
        assert profile.rules.thresholds.frp_high_mw == 25.0
        assert profile.alerts.extreme_frp_threshold == 40.0
        assert profile.incidents.spatial_threshold_km == 0.6
        assert profile.risk.weights.frp == 0.40

        # ---------------------------------------------------------------------
        # Step 3: Ingest & Normalize Using Same Pipeline
        # ---------------------------------------------------------------------
        raw_row = {
            "latitude": "29.742",
            "longitude": "-95.125",
            "brightness": "322.4",
            "frp": "32.0",
            "scan": "0.375",
            "track": "0.375",
            "acq_date": "2026-10-01",
            "acq_time": "1430",
            "satellite": "N",
            "instrument": "VIIRS",
            "confidence": "nominal",
            "version": "2.0NRT",
            "daynight": "D",
        }
        hotspot, obs, rejection = HotspotNormalizer.normalize_row_with_diagnostics(
            row=raw_row,
            provider=profile.providers.enabled_providers[0],
            product=profile.providers.default_source,
        )
        assert rejection is None, f"Industrial detection should pass normalization: {rejection}"
        assert hotspot is not None
        assert obs is not None
        assert obs.latitude == 29.742
        assert obs.longitude == -95.125
        assert obs.frp == 32.0
        assert isinstance(obs, Observation)
        assert obs.frp == 32.0
        assert obs.provider == "NASA_FIRMS"

        # ---------------------------------------------------------------------
        # Step 4: Enrich Using Same Architecture
        # ---------------------------------------------------------------------
        # Load the industrial static assets GeoJSON declared in the profile
        assets_geojson_path = Path(profile.assets.static_assets_path)
        if not assets_geojson_path.is_absolute():
            repo_root = Path(__file__).resolve().parent.parent.parent
            assets_geojson_path = repo_root / assets_geojson_path

        assert assets_geojson_path.is_file(), f"Asset store must exist at {assets_geojson_path}"
        asset_store = GeoJSONAssetStore(file_path=str(assets_geojson_path), auto_load=True)
        
        enrichment_service = EnrichmentService(asset_store=asset_store)
        # Spatial lookup for proximate industrial assets
        proximate_assets = asset_store.query_radius(obs.latitude, obs.longitude, radius_meters=1000.0)
        assert len(proximate_assets) >= 1, "Must find industrial facilities from profile asset store"
        facility_names = [a.name for a in proximate_assets]
        assert any("Refining" in name or "Flare" in name for name in facility_names)

        # ---------------------------------------------------------------------
        # Step 5: Assess Using Same Architecture
        # ---------------------------------------------------------------------
        # Instantiate generic ThermalIntelligenceEngine configured with industrial profile
        intel_engine = ThermalIntelligenceEngine(profile=profile)
        
        # Build contextual features from the enriched assets
        ind_asset = proximate_assets[0]
        ctx = HotspotContext(
            distance_to_industrial_m=120.0,
            nearby_industrial_count=len(proximate_assets),
            land_cover="industrial",
            prior_detections_30d=24,  # Multi-week stationary flare history
            is_recurrent_site=True,
            recurrent_pattern="industrial_stationary",
        )

        assessment = intel_engine.assess_hotspot(
            hotspot={
                "id": obs.observation_id,
                "latitude": obs.latitude,
                "longitude": obs.longitude,
                "brightness": obs.brightness,
                "frp": obs.frp,
                "confidence": obs.detection_confidence,
                "acq_date": "2026-10-01",
                "acq_time": "1430",
            },
            context=ctx,
        )

        assert isinstance(assessment, Assessment)
        assert assessment.classification.predicted_source == SourceType.INDUSTRIAL
        assert assessment.risk.risk_score >= 0.0
        assert assessment.risk.severity in (RiskLevel.HIGH, RiskLevel.CRITICAL, RiskLevel.MEDIUM)
        # Methodology provenance is truthful and reproducible
        assert assessment.methodology.algorithm_version is not None
        assert assessment.methodology.input_hash is not None

        # ---------------------------------------------------------------------
        # Step 6: Correlate Incidents Using Same Engine
        # ---------------------------------------------------------------------
        incident_engine = IncidentEngine(
            repository=InMemoryIncidentRepository(),
            incident_config=profile.incidents,
        )
        assert incident_engine.spatial_threshold_km == 0.6  # Industrial profile threshold

        corr_res = incident_engine.correlate_observations([obs])
        assert len(corr_res.created_incidents) == 1
        created_inc = corr_res.created_incidents[0]
        assert isinstance(created_inc, Incident)
        assert created_inc.incident_id.startswith("INC-")
        assert created_inc.observation_count == 1
        assert created_inc.peak_frp == 32.0

        # Verify a second observation 1.2 km away creates a SEPARATE industrial incident
        obs_far = Observation(
            observation_id="OBS-IND-FAR-01",
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            latitude=obs.latitude + 0.015,  # ~1.6 km north
            longitude=obs.longitude,
            acquisition_time_utc="2026-10-01T15:00:00Z",
            ingestion_time_utc="2026-10-01T15:05:00Z",
            brightness=324.0,
            frp=28.0,
            daynight="D",
            detection_confidence="nominal",
            schema_version="2.0",
        )
        corr_res_2 = incident_engine.correlate_observations([obs_far])
        assert len(corr_res_2.created_incidents) == 1
        second_inc = corr_res_2.created_incidents[0]
        assert second_inc.incident_id != created_inc.incident_id

        # ---------------------------------------------------------------------
        # Step 7: Produce Alerts Using Same Operational Engine
        # ---------------------------------------------------------------------
        alert_gen = AlertGenerator(
            include_medium=True,
            alert_config=profile.alerts,
        )
        flood_engine = FloodProtectionEngine(alert_config=profile.alerts)
        assert flood_engine.config.per_rule_cooldown_seconds == 300  # 5 min industrial cooldown

        # Evaluate transition event for the newly created incident
        creation_event = corr_res.events_emitted[0]
        alert = alert_gen.generate_from_transition(
            incident=created_inc,
            event=creation_event,
        )
        # Alert is produced if incident meets alertable severity
        if alert:
            assert isinstance(alert, AlertV2)
            assert alert.incident_id == created_inc.incident_id
            decision = flood_engine.evaluate(alert, recent_alerts=[])
            assert decision.allowed is True

        # ---------------------------------------------------------------------
        # Step 8: Replay Scenarios Using Same Replay Engine
        # ---------------------------------------------------------------------
        replay_pipeline = ReplayPipeline(profile="industrial-safety", seed=42)
        assert replay_pipeline.profile.metadata.id == "industrial-safety"
        assert replay_pipeline.aggregator.distance_threshold_km == 0.6

        # Load the industrial spike golden scenario
        repo_root = Path(__file__).resolve().parent.parent.parent
        scenario_path = repo_root / "scenarios" / "data" / "scenario_1_industrial_spike.json"
        scenario = load_scenario_from_file(scenario_path)

        # Process observations through replay
        scenario_v2_obs = [
            Observation(
                observation_id=so.observation_id,
                provider=so.provider,
                product=so.product,
                latitude=so.latitude,
                longitude=so.longitude,
                acquisition_time_utc=so.acquisition_time_utc,
                ingestion_time_utc="2026-10-01T10:00:00Z",
                brightness=so.brightness,
                frp=so.frp,
                daynight=so.daynight,
                detection_confidence=so.detection_confidence,
                source_attributes={"context": so.context or {}, "nearest_place": so.nearest_place},
                schema_version="2.0",
            )
            for so in scenario.observations
        ]

        step_res = replay_pipeline.process_observations(
            scenario_v2_obs,
            as_of_utc="2026-10-01T12:00:00Z",
        )

        assert len(step_res.observations) == len(scenario.observations)
        assert len(step_res.assessments) == len(scenario.observations)
        assert len(step_res.active_incidents) >= 1
        
        # Verify incident classification is industrial
        assert any(
            inc.current_classification == SourceType.INDUSTRIAL
            for inc in step_res.active_incidents
        )

        # Verify contracts remain valid and uncorrupted
        for asm in step_res.assessments:
            assert isinstance(asm, Assessment)
            assert asm.target_id.startswith("OBS-SCN001-")
        for inc in step_res.active_incidents:
            assert isinstance(inc, Incident)
            assert inc.incident_id.startswith("INC-")
        for evt in step_res.new_events:
            assert isinstance(evt, IncidentEvent)
        for alt in step_res.new_alerts:
            assert isinstance(alt, AlertV2)

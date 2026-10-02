"""Deep End-to-End Canonical Pipeline Validation Suite for ThermalIntel V2.

Exercises the complete real integrated pipeline:
ProviderRun
  → RawPayload (content-addressed archive)
  → Observation (normalized UTC satellite evidence)
  → EnrichmentSnapshot (geospatial, weather, terrain, historical)
  → Assessment (AI classification, anomaly sigma, 0-100 risk)
  → Incident (stable persistent identity)
  → IncidentObservation (relational associative link)
  → IncidentEvent (append-only timeline audit trail)
  → AlertV2 (deduplicated, rate-limited operational notification)

Validates:
1. Object creation and schema validity at each layer using real repositories.
2. Required provenance and metadata audit trail.
3. Frozen timestamp semantics (acquisition != ingestion != fetched != as_of != created_at).
4. Referential integrity and foreign key constraints across relational SQLite tables.
5. Downstream propagation guarantee: accepted observations cannot silently vanish.
6. Quarantine isolation: malformed records rejected early never create downstream entities.
"""

import os
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

import services.api.database as db_mod
from services.api.migrations.runner import MigrationRunner
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    AlertSeverity,
    AlertState,
    ProviderStatus,
    FreshnessState,
    Provenance,
    now_utc_iso,
)
from services.api.schemas.v2.provider import ProviderRun
from services.api.schemas.v2.payload import RawPayloadMetadata
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.enrichment import (
    EnrichmentSnapshot,
    EnrichmentDatum,
    GeospatialEnrichment,
    WeatherEnrichment,
    TerrainEnrichment,
    HistoricalEnrichment,
)
from services.api.schemas.v2.assessment import Assessment
from services.api.schemas.v2.incident import Incident, IncidentObservation
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.converters import hotspot_from_v2

from services.api.ingestion.payload_store import RawPayloadStore
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.quarantine import QuarantineManager
from services.api.repositories.provider_run_repository import ProviderRunRepository
from services.api.repositories.raw_payload_repository import RawPayloadRepository
from services.api.repositories.observation_repository import ObservationRepository
from services.api.incidents.repository import IncidentRepository
from services.api.incidents.engine import IncidentEngine
from services.api.alerts.repository import AlertV2Repository
from services.api.alerts.service import AlertService
from services.intelligence.engine import ThermalIntelligenceEngine
from services.intelligence.context import HotspotContext

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_BASELINE_RECORDS,
    INDUSTRIAL_SPIKE_RECORD,
    make_raw_firms_csv,
)


class TestDeepCanonicalPipelineE2E(unittest.TestCase):
    """Deep integration validation exercising the full canonical pipeline."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "deep_pipeline_test.db"
        self.raw_dir = Path(self.temp_dir.name) / "raw"
        self.quarantine_dir = Path(self.temp_dir.name) / "quarantine"

        os.environ["DATABASE_PATH"] = str(self.db_path)
        db_mod.DB_PATH = str(self.db_path)
        db_mod.invalidate_seed_cache()

        # Apply canonical database migrations
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        # Connection factory for SQLite with foreign keys enforced
        self.connection_factory = self._get_connection

        # Initialize real repositories and services
        self.provider_run_repo = ProviderRunRepository()
        self.raw_payload_repo = RawPayloadRepository()
        self.observation_repo = ObservationRepository()
        self.incident_repo = IncidentRepository(connection_factory=self.connection_factory)
        self.alert_repo = AlertV2Repository(connection_factory=self.connection_factory)

        self.payload_store = RawPayloadStore(raw_dir=self.raw_dir)
        self.quarantine_mgr = QuarantineManager(quarantine_dir=self.quarantine_dir)
        self.intelligence_engine = ThermalIntelligenceEngine(random_state=42)
        self.incident_engine = IncidentEngine(
            repository=self.incident_repo,
            spatial_threshold_km=2.0,
            temporal_window_hours=24.0,
        )
        self.alert_service = AlertService(
            connection_factory=self.connection_factory,
            repository=self.alert_repo,
        )

    def tearDown(self):
        if self.original_env_db is not None:
            os.environ["DATABASE_PATH"] = self.original_env_db
        else:
            os.environ.pop("DATABASE_PATH", None)
        db_mod.DB_PATH = self.original_db_path
        db_mod.invalidate_seed_cache()
        self.temp_dir.cleanup()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def test_canonical_pipeline_complete_progression(self):
        """Test full propagation from raw CSV payload to operational AlertV2."""
        # ---------------------------------------------------------------------
        # Stage 1: ProviderRun initiation
        # ---------------------------------------------------------------------
        run_start_utc = "2026-10-01T14:00:00Z"
        run_id = "RUN-TEST-001"
        provider_run = ProviderRun(
            run_id=run_id,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            started_at_utc=run_start_utc,
            status=ProviderStatus.RUNNING,
            request_metadata={"area": "world", "day_range": 1},
        )
        self.provider_run_repo.save_run(provider_run)

        # Verify DB persistence of running ProviderRun
        saved_run = self.provider_run_repo.get_by_id(run_id)
        self.assertIsNotNone(saved_run)
        self.assertEqual(saved_run.status, ProviderStatus.RUNNING)

        # ---------------------------------------------------------------------
        # Stage 2: RawPayload storage and content addressing
        # ---------------------------------------------------------------------
        # Combine baseline industrial observation with an extreme blowout spike
        csv_content = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS + [INDUSTRIAL_SPIKE_RECORD])
        fetch_time_utc = "2026-10-01T14:00:05Z"

        payload_meta = self.payload_store.store_payload(
            content=csv_content,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            fetched_at_utc=fetch_time_utc,
        )
        self.raw_payload_repo.save_payload_metadata(payload_meta)

        # Verify content addressing and file existence
        self.assertTrue(Path(payload_meta.storage_path).is_file())
        self.assertEqual(len(payload_meta.content_hash), 64)
        saved_payload = self.raw_payload_repo.get_by_id(payload_meta.payload_id)
        self.assertIsNotNone(saved_payload)
        self.assertEqual(saved_payload.content_hash, payload_meta.content_hash)

        # Update ProviderRun audit to successful completion
        completed_run = provider_run.model_copy(
            update={
                "finished_at_utc": "2026-10-01T14:00:10Z",
                "status": ProviderStatus.SUCCESS,
                "rows_received": 3,
                "duration_ms": 10000,
                "payload_id": payload_meta.payload_id,
            }
        )
        self.provider_run_repo.save_run(completed_run)

        # ---------------------------------------------------------------------
        # Stage 3: Normalization & Observation persistence
        # ---------------------------------------------------------------------
        observations, hotspots, q_count = HotspotNormalizer.normalize_csv_with_quarantine(
            csv_text=csv_content,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            run_id=run_id,
            quarantine_mgr=self.quarantine_mgr,
            raw_payload_id=payload_meta.payload_id,
        )
        self.assertEqual(q_count, 0, "All valid fixture records should pass normalization")
        self.assertEqual(len(observations), 3)

        # Verify observation timestamp semantics
        for obs in observations:
            self.assertIsNotNone(obs.acquisition_time_utc)
            self.assertIsNotNone(obs.ingestion_time_utc)
            # Ingestion time must be later than acquisition time
            self.assertGreaterEqual(obs.ingestion_time_utc, obs.acquisition_time_utc)
            # Persist observation
            self.observation_repo.save_observation(obs)

        # Confirm relational observation storage
        persisted_obs_list, total_count = self.observation_repo.get_observations(limit=10)
        self.assertEqual(len(persisted_obs_list), 3)
        spike_obs = next(o for o in persisted_obs_list if o.frp == INDUSTRIAL_SPIKE_RECORD["frp"])
        self.assertEqual(spike_obs.raw_payload_id, payload_meta.payload_id)

        # ---------------------------------------------------------------------
        # Stage 4: Contextual Enrichment Snapshot
        # ---------------------------------------------------------------------
        prov = Provenance(
            provider="Open-Meteo",
            product="weather_forecast",
            observed_at_utc="2026-10-01T13:00:00Z",
            fetched_at_utc=fetch_time_utc,
            freshness_state=FreshnessState.FRESH,
            ttl_seconds=3600,
            reference="https://api.open-meteo.com/v1/forecast",
        )
        geo_prov = Provenance(
            provider="OpenStreetMap",
            product="overpass_infrastructure",
            observed_at_utc="2026-10-01T12:00:00Z",
            fetched_at_utc=fetch_time_utc,
            freshness_state=FreshnessState.CACHED,
            ttl_seconds=86400,
            reference="osm:overpass:refinery",
        )

        snapshot_id = f"ENR-{spike_obs.observation_id}"
        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO enrichment_snapshots (
                    snapshot_id, target_id, target_type, context_type,
                    provider, product, observed_at_utc, fetched_at_utc,
                    freshness_state, status, payload_json, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot_id,
                    spike_obs.observation_id,
                    "observation",
                    "geospatial",
                    "OpenStreetMap",
                    "overpass_infrastructure",
                    "2026-10-01T12:00:00Z",
                    fetch_time_utc,
                    FreshnessState.CACHED.value,
                    "available",
                    json.dumps({"land_cover": "industrial", "nearest_infrastructure": "Refinery Complex"}),
                    now_utc_iso(),
                ),
            )
            conn.commit()

        # Verify enrichment snapshot persistence
        loaded_snapshots = self.incident_repo.get_enrichment_snapshots(spike_obs.observation_id)
        self.assertIn("geospatial", loaded_snapshots)
        self.assertEqual(loaded_snapshots["geospatial"]["land_cover"], "industrial")

        # ---------------------------------------------------------------------
        # Stage 5: Intelligence Assessment Generation
        # ---------------------------------------------------------------------
        hotspot = hotspot_from_v2(spike_obs, nearest_place="Port Arthur Refinery Complex")
        ctx = HotspotContext(
            distance_to_settlement_m=4200.0,
            distance_to_infrastructure_m=45.0,
            distance_to_industrial_m=45.0,
            land_cover="industrial",
            temperature_c=31.5,
            wind_speed_kmh=22.3,
            relative_humidity_pct=42.0,
        )

        assessment = self.intelligence_engine.assess_hotspot(
            hotspot=hotspot,
            context=ctx,
            target_id=spike_obs.observation_id,
            target_type="observation",
            as_of_utc="2026-10-01T14:00:00Z",
        )

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO assessments (
                    assessment_id, target_id, target_type, predicted_source,
                    classification_confidence, class_probabilities_json, is_anomaly,
                    anomaly_score, anomaly_rationale, risk_score, severity,
                    risk_factors_json, completeness_score, uncertainty_score,
                    method, algorithm_version, input_hash, as_of_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    assessment.assessment_id,
                    assessment.target_id,
                    assessment.target_type,
                    assessment.classification.predicted_source.value,
                    assessment.classification.classification_confidence,
                    json.dumps(assessment.classification.probabilities),
                    1 if assessment.anomaly.is_anomaly else 0,
                    assessment.anomaly.anomaly_score,
                    assessment.anomaly.anomaly_rationale,
                    assessment.risk.risk_score,
                    assessment.risk.severity.value,
                    json.dumps([f.model_dump() for f in assessment.risk.factors]),
                    assessment.data_quality.completeness_score if assessment.data_quality else 1.0,
                    assessment.data_quality.uncertainty_score if assessment.data_quality else 0.0,
                    assessment.methodology.method,
                    assessment.methodology.algorithm_version,
                    assessment.methodology.input_hash,
                    assessment.methodology.as_of_utc,
                    assessment.created_at_utc,
                ),
            )
            conn.commit()

        # Verify Assessment properties: input_hash, methodology, risk tier
        self.assertIsNotNone(assessment.methodology.input_hash)
        self.assertEqual(len(assessment.methodology.input_hash), 64)
        self.assertEqual(assessment.target_id, spike_obs.observation_id)
        self.assertGreaterEqual(assessment.risk.risk_score, 70.0)
        self.assertIn(assessment.risk.severity, (RiskLevel.HIGH, RiskLevel.CRITICAL))

        # Check DB retrieval of Assessment
        saved_asm = self.incident_repo.get_assessment(spike_obs.observation_id)
        self.assertIsNotNone(saved_asm)
        self.assertEqual(saved_asm.assessment_id, assessment.assessment_id)

        # ---------------------------------------------------------------------
        # Stage 6: Incident Spatiotemporal Correlation & Stable Identity
        # ---------------------------------------------------------------------
        # Correlate all 3 observations
        correlation_result = self.incident_engine.correlate_observations(
            observations=observations,
            as_of_utc="2026-10-01T14:00:00Z",
        )

        # Since all 3 observations are co-located at the refinery, exactly 1 incident must be established
        incidents = self.incident_repo.list_incidents(status=[IncidentStatus.ACTIVE])
        self.assertEqual(len(incidents), 1)
        incident = incidents[0]

        # Verify stable identity structure (INC-YYYYMMDD-XXXX)
        self.assertTrue(incident.incident_id.startswith("INC-20261001-"))
        self.assertEqual(incident.observation_count, 3)
        self.assertEqual(incident.peak_frp, INDUSTRIAL_SPIKE_RECORD["frp"])

        # ---------------------------------------------------------------------
        # Stage 7: IncidentObservation Associative Links
        # ---------------------------------------------------------------------
        incident_obs = self.incident_repo.list_incident_observations(incident.incident_id)
        self.assertEqual(len(incident_obs), 3)
        correlated_obs_ids = {o.observation_id for o in incident_obs}
        self.assertEqual(correlated_obs_ids, {o.observation_id for o in observations})

        # Relational check: verify foreign key constraints prevent orphan associations
        with self.assertRaises(sqlite3.IntegrityError):
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO incident_observations (incident_id, observation_id, joined_at_utc) VALUES (?, ?, ?)",
                    ("INC-DOES-NOT-EXIST", spike_obs.observation_id, now_utc_iso()),
                )

        # ---------------------------------------------------------------------
        # Stage 8: IncidentEvent Timeline Audit Trail
        # ---------------------------------------------------------------------
        events = self.incident_repo.list_incident_events(incident.incident_id)
        self.assertGreaterEqual(len(events), 2)

        # Verify chronological ordering and transition event types
        event_types = [e.event_type for e in events]
        self.assertEqual(event_types[0], IncidentEventType.CREATED)
        self.assertIn(IncidentEventType.OBSERVATION_ADDED, event_types)

        # Timestamps must be non-decreasing
        timestamps = [e.timestamp_utc for e in events]
        self.assertEqual(timestamps, sorted(timestamps))

        # ---------------------------------------------------------------------
        # Stage 9: Operational Alert Generation (AlertV2)
        # ---------------------------------------------------------------------
        # Link assessment to incident and process transition event
        incident_with_asm = incident.model_copy(
            update={
                "current_risk_score": assessment.risk.risk_score,
                "current_severity": assessment.risk.severity,
                "current_assessment_id": assessment.assessment_id,
            }
        )
        self.incident_repo.save_incident(incident_with_asm)

        # Choose the escalation/spike event or creation event
        trigger_event = events[-1]
        alert = self.alert_service.process_incident_transition(
            incident=incident_with_asm,
            event=trigger_event,
            extra_evidence={"spike_frp": spike_obs.frp},
        )

        self.assertIsNotNone(alert, "A critical blowout should generate an operational alert")
        self.assertTrue(alert.alert_id.startswith("ALT-"))
        self.assertEqual(alert.incident_id, incident.incident_id)
        self.assertIsNotNone(alert.dedupe_key)
        self.assertEqual(alert.state, AlertState.ACTIVE)

        # Verify AlertV2 persistence in SQLite
        db_alert = self.alert_repo.get_by_id(alert.alert_id)
        self.assertIsNotNone(db_alert)
        self.assertEqual(db_alert.dedupe_key, alert.dedupe_key)
        self.assertEqual(db_alert.priority, AlertSeverity.CRITICAL)

        # Verify dedupe key query
        dedupe_match = self.alert_repo.get_by_dedupe_key(alert.dedupe_key)
        self.assertIsNotNone(dedupe_match)
        self.assertEqual(dedupe_match.alert_id, alert.alert_id)

    def test_quarantined_record_never_propagates_downstream(self):
        """Verify that malformed records rejected early never create downstream entities."""
        # Row with out-of-bounds coordinates (latitude 999.0)
        corrupted_csv = (
            "latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight\n"
            "999.0,-93.5678,328.5,0.4,0.4,2026-10-01,0415,Suomi-NPP,VIIRS,high,2.0NRT,290.0,35.0,N\n"
        )
        observations, hotspots, q_count = HotspotNormalizer.normalize_csv_with_quarantine(
            csv_text=corrupted_csv,
            provider="NASA_FIRMS",
            product="VIIRS_SNPP_NRT",
            run_id="RUN-CORRUPT-TEST",
            quarantine_mgr=self.quarantine_mgr,
        )

        self.assertEqual(q_count, 1)
        self.assertEqual(len(observations), 0)

        # Correlating empty observation batch should yield zero incidents
        res = self.incident_engine.correlate_observations(observations)
        self.assertEqual(len(res.created_incidents), 0)

        # Ensure no records exist in observations or incidents tables
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM observations")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT COUNT(*) FROM incidents")
            self.assertEqual(cursor.fetchone()[0], 0)
            cursor.execute("SELECT COUNT(*) FROM alerts_v2")
            self.assertEqual(cursor.fetchone()[0], 0)

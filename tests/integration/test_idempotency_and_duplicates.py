"""Idempotency and Duplicate Handling Validation Suite for ThermalIntel V2.

Verifies:
1. Same provider observation processed twice yields no duplicate observations.
2. Same raw payload processed twice preserves content hash and single record.
3. Repeated ingestion runs produce zero duplicate entities in database.
4. Duplicate incident association does not create duplicate IncidentObservation rows.
5. Reprocessing does not emit duplicate active alerts or duplicate incident events.
6. Concurrent duplicate ingestion attempts safely preserve unique constraints.
7. Input order independence: shuffled ingestion yields identical incident clusters.
"""

import os
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List

import services.api.database as db_mod
from services.api.migrations.runner import MigrationRunner
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    AlertSeverity,
    AlertState,
    now_utc_iso,
)
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident, IncidentObservation
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.converters import hotspot_from_v2

from services.api.ingestion.payload_store import RawPayloadStore
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.quarantine import QuarantineManager
from services.api.repositories.raw_payload_repository import RawPayloadRepository
from services.api.repositories.observation_repository import ObservationRepository
from services.api.incidents.repository import IncidentRepository
from services.api.incidents.engine import IncidentEngine
from services.api.alerts.repository import AlertV2Repository
from services.api.alerts.service import AlertService
from services.intelligence.engine import ThermalIntelligenceEngine

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_BASELINE_RECORDS,
    INDUSTRIAL_SPIKE_RECORD,
    VEGETATION_FIRE_RECORDS,
    make_raw_firms_csv,
)


class TestIdempotencyAndDuplicates(unittest.TestCase):
    """Deep validation of idempotent persistence and deduplication integrity."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "idempotency_test.db"
        self.raw_dir = Path(self.temp_dir.name) / "raw"
        self.quarantine_dir = Path(self.temp_dir.name) / "quarantine"

        os.environ["DATABASE_PATH"] = str(self.db_path)
        db_mod.DB_PATH = str(self.db_path)
        db_mod.invalidate_seed_cache()

        # Apply migrations
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        self.connection_factory = self._get_connection

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

    def test_same_raw_payload_stored_twice(self):
        """Storing identical raw payload content twice yields identical hash and deduplicated file."""
        csv_text = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS)
        
        meta1 = self.payload_store.store_payload(csv_text, provider="NASA_FIRMS", product="VIIRS")
        self.raw_payload_repo.save_payload_metadata(meta1)

        meta2 = self.payload_store.store_payload(csv_text, provider="NASA_FIRMS", product="VIIRS")
        self.raw_payload_repo.save_payload_metadata(meta2)

        # Content hash must be 100% identical
        self.assertEqual(meta1.content_hash, meta2.content_hash)
        self.assertEqual(meta1.payload_id, meta2.payload_id)
        self.assertEqual(meta1.storage_path, meta2.storage_path)

        # Verify only 1 row exists in raw_payloads table
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM raw_payloads")
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_same_observation_persisted_twice(self):
        """Upserting the identical observation multiple times does not increase record count."""
        csv_text = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS)
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        self.assertEqual(len(observations), 2)

        # First persistence run
        for obs in observations:
            self.observation_repo.save_observation(obs)

        obs_list1, total1 = self.observation_repo.get_observations()
        self.assertEqual(total1, 2)

        # Second persistence run (same observations)
        for obs in observations:
            self.observation_repo.save_observation(obs)

        obs_list2, total2 = self.observation_repo.get_observations()
        self.assertEqual(total2, 2)
        self.assertEqual([o.observation_id for o in obs_list1], [o.observation_id for o in obs_list2])

    def test_repeated_incident_correlation_no_duplicate_incidents(self):
        """Re-correlating already ingested observations must be a deterministic idempotent no-op."""
        csv_text = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS)
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)

        # First correlation
        res1 = self.incident_engine.correlate_observations(observations, as_of_utc="2026-10-01T10:00:00Z")
        self.assertEqual(len(res1.created_incidents), 1)

        incidents_after_run1 = self.incident_repo.list_incidents(
            status=[IncidentStatus.ACTIVE, IncidentStatus.MONITORING]
        )
        self.assertEqual(len(incidents_after_run1), 1)
        inc_id = incidents_after_run1[0].incident_id

        obs_links1 = self.incident_repo.list_incident_observations(inc_id)
        self.assertEqual(len(obs_links1), 2)

        events1 = self.incident_repo.list_incident_events(inc_id)
        event_count1 = len(events1)

        # Second correlation with the same observations
        res2 = self.incident_engine.correlate_observations(observations, as_of_utc="2026-10-01T10:05:00Z")
        self.assertEqual(len(res2.created_incidents), 0)

        # Assert no new incidents, no duplicate observation links, no duplicate events
        incidents_after_run2 = self.incident_repo.list_incidents(
            status=[IncidentStatus.ACTIVE, IncidentStatus.MONITORING]
        )
        self.assertEqual(len(incidents_after_run2), 1)
        self.assertEqual(incidents_after_run2[0].incident_id, inc_id)

        obs_links2 = self.incident_repo.list_incident_observations(inc_id)
        self.assertEqual(len(obs_links2), 2)

        events2 = self.incident_repo.list_incident_events(inc_id)
        self.assertEqual(len(events2), event_count1)

    def test_unique_constraint_on_incident_observations_table(self):
        """Relational constraint prevents assigning the same observation to the same incident twice."""
        csv_text = make_raw_firms_csv([INDUSTRIAL_BASELINE_RECORDS[0]])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        obs = observations[0]
        self.observation_repo.save_observation(obs)

        res = self.incident_engine.correlate_observations([obs])
        inc_id = res.created_incidents[0].incident_id

        # Directly attempt to insert a duplicate (incident_id, observation_id) pair via SQL
        with self.assertRaises(sqlite3.IntegrityError):
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO incident_observations (incident_id, observation_id, joined_at_utc) VALUES (?, ?, ?)",
                    (inc_id, obs.observation_id, now_utc_iso()),
                )

    def test_alert_deduplication_under_repeated_events(self):
        """Processing duplicate events with identical dedupe_key yields exactly 1 active alert."""
        csv_text = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        obs = observations[0]

        res = self.incident_engine.correlate_observations([obs])
        incident = res.created_incidents[0]
        events = self.incident_repo.list_incident_events(incident.incident_id)
        trigger_event = events[0]

        # First alert generation
        alert1 = self.alert_service.process_incident_transition(
            incident=incident,
            event=trigger_event,
            extra_evidence={"frp": obs.frp},
        )
        self.assertIsNotNone(alert1)
        self.assertEqual(alert1.state, AlertState.ACTIVE)

        # Second alert generation with the identical incident transition event
        alert2 = self.alert_service.process_incident_transition(
            incident=incident,
            event=trigger_event,
            extra_evidence={"frp": obs.frp},
        )
        # Duplicate should be suppressed / return None
        self.assertIsNone(alert2, "Duplicate incident transition must not create a second alert")

        # Third attempt: directly inserting duplicate dedupe_key into SQLite must fail unique constraint
        with self.assertRaises(sqlite3.IntegrityError):
            with self._get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO alerts_v2 (
                        alert_id, incident_id, observation_id, rule_id, dedupe_key,
                        priority, state, title, message, evidence_json, metadata_json,
                        created_at_utc
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "ALT-MANUAL-DUP", incident.incident_id, obs.observation_id,
                        alert1.rule_id, alert1.dedupe_key, alert1.priority.value,
                        AlertState.ACTIVE.value, "Duplicate", "Message", "{}", "{}",
                        now_utc_iso(),
                    ),
                )

    def test_order_invariance_shuffled_ingestion(self):
        """Ingesting observations in different order produces the identical incident grouping."""
        records = [
            INDUSTRIAL_BASELINE_RECORDS[0],
            INDUSTRIAL_BASELINE_RECORDS[1],
            VEGETATION_FIRE_RECORDS[0],  # ~500 km away, forms separate incident
        ]

        # Normalization produces deterministic observation models
        csv_text = make_raw_firms_csv(records)
        obs_forward, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)

        # Forward order correlation in fresh database
        engine1 = IncidentEngine(repository=self.incident_repo)
        res1 = engine1.correlate_observations(obs_forward)
        self.assertEqual(len(res1.created_incidents), 2)
        forward_ids = sorted([inc.incident_id for inc in res1.created_incidents])

        # Clear and run in reversed order
        with self._get_connection() as conn:
            conn.execute("DELETE FROM incident_observations")
            conn.execute("DELETE FROM incident_events")
            conn.execute("DELETE FROM incidents")
            conn.execute("DELETE FROM observations")
            conn.commit()

        obs_reversed = list(reversed(obs_forward))
        engine2 = IncidentEngine(repository=self.incident_repo)
        res2 = engine2.correlate_observations(obs_reversed)
        self.assertEqual(len(res2.created_incidents), 2)
        reversed_ids = sorted([inc.incident_id for inc in res2.created_incidents])

        # Cluster IDs and memberships must be 100% identical regardless of input order
        self.assertEqual(forward_ids, reversed_ids)

    def test_concurrent_duplicate_ingestion_safety(self):
        """Simultaneous duplicate ingestion runs safely coordinate via SQLite transactions."""
        csv_text = make_raw_firms_csv(INDUSTRIAL_BASELINE_RECORDS)
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)

        def ingest_task():
            # Create thread-local engine pointing to same SQLite database
            repo = IncidentRepository(connection_factory=self.connection_factory)
            engine = IncidentEngine(repository=repo)
            return engine.correlate_observations(observations)

        # Run 4 concurrent workers attempting to correlate identical observations
        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = [executor.submit(ingest_task) for _ in range(4)]
            results = [f.result() for f in futures]

        # Exactly 1 incident must be present in the database
        incidents = self.incident_repo.list_incidents(
            status=[IncidentStatus.ACTIVE, IncidentStatus.MONITORING]
        )
        self.assertEqual(len(incidents), 1)

        # Exactly 2 observations must be linked to the incident
        linked_obs = self.incident_repo.list_incident_observations(incidents[0].incident_id)
        self.assertEqual(len(linked_obs), 2)

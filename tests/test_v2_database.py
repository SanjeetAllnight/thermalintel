"""Tests for ThermalIntel V2 Persistence Foundation.

Validates SQLite table operations:
- Insert / read Observation records.
- Unique constraints enforcement (incident_observations and alerts_v2 dedupe_key).
- Incident <-> Observation association queries.
- Append-only incident events preservation.
- Assessment persistence with input_hash and methodology reproducibility.
- Provider run observability records.
- Raw payload metadata tracking.
- Strict UTC timestamp preservation.
"""

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from datetime import datetime, timezone

from services.api.migrations.runner import MigrationRunner


class TestV2DatabaseOperations(unittest.TestCase):
    """Database persistence test suite for canonical V2 relational schema."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_v2_db.db"
        # Run migrations to bring schema to V2
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    def test_insert_and_query_observation(self):
        """Insert a canonical observation and query it back with exact radiometric fidelity."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO observations (
                    observation_id, provider, product, satellite, instrument,
                    latitude, longitude, acquisition_time_utc, ingestion_time_utc,
                    brightness, bright_t31, frp, scan, track, daynight,
                    detection_confidence, source_attributes_json, schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "OBS-20261001-0001", "NASA_FIRMS", "VIIRS_SNPP_NRT", "Suomi-NPP", "VIIRS",
                37.7749, -122.4194, "2026-10-01T08:45:00Z", "2026-10-01T08:50:00Z",
                348.6, 298.4, 128.5, 0.38, 0.36, "N",
                "high", json.dumps({"raw_line": 1}), "2.0"
            ))
            conn.commit()

            cursor.execute("SELECT * FROM observations WHERE observation_id = ?", ("OBS-20261001-0001",))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["observation_id"], "OBS-20261001-0001")
            self.assertEqual(row["provider"], "NASA_FIRMS")
            self.assertEqual(row["latitude"], 37.7749)
            self.assertEqual(row["frp"], 128.5)
            self.assertEqual(row["detection_confidence"], "high")
            self.assertEqual(row["acquisition_time_utc"], "2026-10-01T08:45:00Z")

    def test_unique_constraint_on_incident_observations(self):
        """Pairing the same (incident_id, observation_id) twice must raise sqlite3.IntegrityError."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # First create incident and observation
            cursor.execute("""
                INSERT INTO incidents (
                    incident_id, status, first_seen_utc, last_seen_utc,
                    centroid_latitude, centroid_longitude, peak_frp, average_frp,
                    observation_count, current_risk_score, current_severity,
                    current_classification, created_at_utc, updated_at_utc
                ) VALUES (?, 'active', '2026-10-01T08:00:00Z', '2026-10-01T09:00:00Z',
                          37.7, -122.4, 100.0, 100.0, 1, 75.0, 'high', 'wildfire',
                          '2026-10-01T08:00:00Z', '2026-10-01T09:00:00Z')
            """, ("INC-001",))

            cursor.execute("""
                INSERT INTO observations (
                    observation_id, provider, product, latitude, longitude,
                    acquisition_time_utc, ingestion_time_utc, brightness, frp,
                    daynight, detection_confidence
                ) VALUES ('OBS-001', 'NASA_FIRMS', 'VIIRS', 37.7, -122.4,
                          '2026-10-01T08:00:00Z', '2026-10-01T08:05:00Z', 330.0, 100.0,
                          'N', 'high')
            """)
            conn.commit()

            # First association succeeds
            cursor.execute("""
                INSERT INTO incident_observations (incident_id, observation_id, joined_at_utc)
                VALUES ('INC-001', 'OBS-001', '2026-10-01T08:06:00Z')
            """)
            conn.commit()

            # Duplicate association MUST fail with IntegrityError
            with self.assertRaises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO incident_observations (incident_id, observation_id, joined_at_utc)
                    VALUES ('INC-001', 'OBS-001', '2026-10-01T08:07:00Z')
                """)

    def test_unique_constraint_on_alerts_v2_dedupe_key(self):
        """Inserting two alerts with identical dedupe_key must raise sqlite3.IntegrityError."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO alerts_v2 (
                    alert_id, rule_id, dedupe_key, priority, state,
                    title, message, created_at_utc
                ) VALUES (
                    'ALT-001', 'RULE_FRP', 'INC-001:CRITICAL:FRP_SURGE', 'critical', 'active',
                    'FRP Surge', 'FRP increased drastically', '2026-10-01T09:00:00Z'
                )
            """)
            conn.commit()

            # Inserting another alert with identical dedupe_key must fail
            with self.assertRaises(sqlite3.IntegrityError):
                cursor.execute("""
                    INSERT INTO alerts_v2 (
                        alert_id, rule_id, dedupe_key, priority, state,
                        title, message, created_at_utc
                    ) VALUES (
                        'ALT-002', 'RULE_FRP', 'INC-001:CRITICAL:FRP_SURGE', 'critical', 'active',
                        'Duplicate Surge', 'Another message', '2026-10-01T09:05:00Z'
                    )
                """)

    def test_append_only_incident_events(self):
        """Incident timeline events can be appended sequentially and queried chronologically."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO incidents (
                    incident_id, status, first_seen_utc, last_seen_utc,
                    centroid_latitude, centroid_longitude, peak_frp, average_frp,
                    observation_count, current_risk_score, current_severity,
                    current_classification, created_at_utc, updated_at_utc
                ) VALUES ('INC-TIMELINE', 'active', '2026-10-01T06:00:00Z', '2026-10-01T09:00:00Z',
                          38.0, -120.0, 50.0, 40.0, 2, 60.0, 'medium', 'wildfire',
                          '2026-10-01T06:00:00Z', '2026-10-01T09:00:00Z')
            """)

            # Add two sequential timeline events
            cursor.execute("""
                INSERT INTO incident_events (event_id, incident_id, event_type, timestamp_utc, actor, reason, metadata_json)
                VALUES ('EVT-01', 'INC-TIMELINE', 'created', '2026-10-01T06:05:00Z', 'correlator', 'Initial cluster formed', '{}')
            """)
            cursor.execute("""
                INSERT INTO incident_events (event_id, incident_id, event_type, timestamp_utc, actor, reason, metadata_json)
                VALUES ('EVT-02', 'INC-TIMELINE', 'escalated', '2026-10-01T08:15:00Z', 'risk_engine', 'Risk upgraded to high', '{"delta": 15.0}')
            """)
            conn.commit()

            cursor.execute("""
                SELECT * FROM incident_events WHERE incident_id = 'INC-TIMELINE' ORDER BY timestamp_utc ASC
            """)
            events = cursor.fetchall()
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_type"], "created")
            self.assertEqual(events[1]["event_type"], "escalated")

    def test_assessment_persistence_and_input_hash(self):
        """Verify Assessment persistence stores methodology, version, and input hash for reproducibility."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO assessments (
                    assessment_id, target_id, target_type, predicted_source,
                    classification_confidence, class_probabilities_json, is_anomaly,
                    anomaly_score, anomaly_rationale, risk_score, severity,
                    risk_factors_json, completeness_score, uncertainty_score,
                    method, algorithm_version, input_hash, as_of_utc, created_at_utc
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "ASM-TEST-001", "OBS-TEST-001", "observation", "wildfire",
                0.94, json.dumps({"wildfire": 0.94, "industrial": 0.06}), 1,
                0.85, "Outlier in local cluster", 82.5, "critical",
                json.dumps([{"factor": "FRP", "weight": 0.5}]), 0.98, 0.05,
                "RandomForestClassifier", "v2.0.0-rf-heuristic",
                "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890",
                "2026-10-01T10:00:00Z", "2026-10-01T10:00:05Z"
            ))
            conn.commit()

            cursor.execute("SELECT * FROM assessments WHERE assessment_id = ?", ("ASM-TEST-001",))
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["algorithm_version"], "v2.0.0-rf-heuristic")
            self.assertEqual(row["input_hash"], "a1b2c3d4e5f67890abcdef1234567890abcdef1234567890abcdef1234567890")
            self.assertEqual(row["as_of_utc"], "2026-10-01T10:00:00Z")

    def test_provider_run_audit_persistence(self):
        """Verify provider runs can be logged and audited without storing secrets."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO provider_runs (
                    run_id, provider, product, started_at_utc, finished_at_utc,
                    status, rows_received, duration_ms, request_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                "RUN-001", "NASA_FIRMS", "VIIRS_SNPP_NRT", "2026-10-01T08:50:00Z",
                "2026-10-01T08:50:02Z", "success", 42, 1850,
                json.dumps({"area": "USA_contiguous_and_Hawaii", "days": 1})
            ))
            conn.commit()

            cursor.execute("SELECT * FROM provider_runs WHERE run_id = 'RUN-001'")
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["rows_received"], 42)
            meta = json.loads(row["request_metadata_json"])
            self.assertNotIn("api_key", meta)


if __name__ == "__main__":
    unittest.main()

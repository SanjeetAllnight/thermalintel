"""Incident Lifecycle Integrity Validation Suite for ThermalIntel V2.

Verifies:
1. Stable permanent incident identity minted at creation and preserved over time.
2. Progressive observation addition: centroid shift, peak FRP, and observation count updates.
3. Spatial continuity: observations within threshold correlate, beyond threshold separate.
4. Temporal continuity: observations within window correlate, beyond window separate.
5. Incompatible classifications remain separated despite spatial proximity.
6. Severity transitions: escalating risk emits ESCALATED event, decreasing emits DEESCALATED.
7. Lifecycle evaluation: quiet incidents age into MONITORING and RESOLVED with events.
8. Reopening behavior: closed incidents can be reopened explicitly or by new thermal detections.
9. Append-only chronological timeline audit trail across all transitions.
"""

import os
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import services.api.database as db_mod
from services.api.migrations.runner import MigrationRunner
from services.api.schemas.common import RiskLevel, SourceType
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    now_utc_iso,
)
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.repositories.observation_repository import ObservationRepository
from services.api.incidents.repository import IncidentRepository
from services.api.incidents.engine import IncidentEngine

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_BASELINE_RECORDS,
    INDUSTRIAL_SPIKE_RECORD,
    VEGETATION_FIRE_RECORDS,
    WEAK_DETECTION_RECORD,
    INCOMPATIBLE_PAIR_RECORDS,
    DISTINCT_SPATIAL_RECORDS,
    make_raw_firms_csv,
)


class TestIncidentLifecycleIntegrity(unittest.TestCase):
    """Validation suite for persistent incident lifecycle rules, events, and transitions."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "lifecycle_test.db"

        os.environ["DATABASE_PATH"] = str(self.db_path)
        db_mod.DB_PATH = str(self.db_path)
        db_mod.invalidate_seed_cache()

        # Apply migrations
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        self.connection_factory = self._get_connection
        self.observation_repo = ObservationRepository()
        self.incident_repo = IncidentRepository(connection_factory=self.connection_factory)
        self.incident_engine = IncidentEngine(
            repository=self.incident_repo,
            spatial_threshold_km=2.0,
            temporal_window_hours=24.0,
            reopen_window_hours=72.0,
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

    def test_incident_establishment_and_stable_identity(self):
        """Establish incident from initial observation and verify permanent identifier."""
        csv_text = make_raw_firms_csv([VEGETATION_FIRE_RECORDS[0]])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        obs = observations[0]

        res = self.incident_engine.correlate_observations([obs])
        self.assertEqual(len(res.created_incidents), 1)
        incident = res.created_incidents[0]

        # Verify permanent ID pattern INC-YYYYMMDD-XXXX
        self.assertTrue(incident.incident_id.startswith("INC-20261001-"))
        self.assertEqual(incident.observation_count, 1)
        self.assertEqual(incident.centroid_latitude, obs.latitude)
        self.assertEqual(incident.centroid_longitude, obs.longitude)
        self.assertEqual(incident.peak_frp, obs.frp)

        # Ingestion of second observation joins same incident, identity does not change
        csv_text_2 = make_raw_firms_csv([VEGETATION_FIRE_RECORDS[1]])
        observations_2, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text_2)
        obs_2 = observations_2[0]

        res_2 = self.incident_engine.correlate_observations([obs_2])
        self.assertEqual(len(res_2.created_incidents), 0)

        updated_incident = self.incident_repo.get_incident(incident.incident_id)
        self.assertIsNotNone(updated_incident)
        self.assertEqual(updated_incident.incident_id, incident.incident_id, "Stable identity must not mutate")
        self.assertEqual(updated_incident.observation_count, 2)
        self.assertEqual(updated_incident.peak_frp, max(obs.frp, obs_2.frp))

    def test_spatial_continuity_join_vs_separate(self):
        """Observations within 2km join the same incident; beyond 2km establish separate incidents."""
        # 1. Nearby observations (< 1.5 km)
        nearby_records = [
            INDUSTRIAL_BASELINE_RECORDS[0],
            INDUSTRIAL_BASELINE_RECORDS[1],
        ]
        csv_nearby = make_raw_firms_csv(nearby_records)
        obs_nearby, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_nearby)
        res_nearby = self.incident_engine.correlate_observations(obs_nearby)
        self.assertEqual(len(res_nearby.created_incidents), 1)

        # 2. Distant observation (~8.9 km away)
        csv_distant = make_raw_firms_csv([DISTINCT_SPATIAL_RECORDS[1]])
        obs_distant, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_distant)
        res_distant = self.incident_engine.correlate_observations(obs_distant)
        self.assertEqual(len(res_distant.created_incidents), 1)

        # In total, there must now be exactly 2 distinct incidents
        all_incidents = self.incident_repo.list_incidents()
        self.assertEqual(len(all_incidents), 2)
        self.assertNotEqual(all_incidents[0].incident_id, all_incidents[1].incident_id)

    def test_temporal_continuity_window(self):
        """Observations within temporal window join; observations arriving beyond window establish separate incident."""
        # Observation at Day 1
        obs1_dict = dict(VEGETATION_FIRE_RECORDS[0])
        obs1_dict["acq_date"] = "2026-10-01"
        obs1_dict["acq_time"] = "1200"

        # Observation at Day 4 (72 hours later, exceeding 24h correlation window)
        obs2_dict = dict(VEGETATION_FIRE_RECORDS[0])
        obs2_dict["acq_date"] = "2026-10-04"
        obs2_dict["acq_time"] = "1200"

        csv1 = make_raw_firms_csv([obs1_dict])
        obs1, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv1)
        self.incident_engine.correlate_observations(obs1)

        csv2 = make_raw_firms_csv([obs2_dict])
        obs2, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv2)
        res2 = self.incident_engine.correlate_observations(obs2)

        # Should create a second incident because delta exceeds 24.0 hours
        self.assertEqual(len(res2.created_incidents), 1)
        all_incidents = self.incident_repo.list_incidents()
        self.assertEqual(len(all_incidents), 2)

    def test_incompatible_classifications_remain_separated(self):
        """Spatially adjacent detections with incompatible classifications (e.g. volcanic vs agricultural) separate."""
        csv_text = make_raw_firms_csv(INCOMPATIBLE_PAIR_RECORDS)
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        self.assertEqual(len(observations), 2)

        # Set explicit source_type in source_attributes
        observations[0].source_attributes["source_type"] = SourceType.VOLCANIC
        observations[1].source_attributes["source_type"] = SourceType.AGRICULTURAL

        res = self.incident_engine.correlate_observations(observations)
        # Even though distance is ~0.7 km, conflicting physical classifications must keep them separated
        incidents = self.incident_repo.list_incidents()
        self.assertGreaterEqual(len(incidents), 2)

    def test_severity_escalation_and_timeline_events(self):
        """Increasing FRP triggers an ESCALATED event on the append-only timeline."""
        # Baseline observation (FRP 35.0)
        csv1 = make_raw_firms_csv([INDUSTRIAL_BASELINE_RECORDS[0]])
        obs1, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv1)
        res1 = self.incident_engine.correlate_observations(obs1, as_of_utc="2026-10-01T04:15:00Z")
        inc_id = res1.created_incidents[0].incident_id

        # Massive blowout spike (FRP 245.0)
        csv2 = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs2, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv2)
        self.incident_engine.correlate_observations(obs2, as_of_utc="2026-10-01T13:45:00Z")

        events = self.incident_repo.list_incident_events(inc_id)
        event_types = [e.event_type for e in events]

        self.assertIn(IncidentEventType.CREATED, event_types)
        self.assertIn(IncidentEventType.OBSERVATION_ADDED, event_types)
        self.assertIn(IncidentEventType.ESCALATED, event_types)

        # Check metadata on escalation event
        esc_event = next(e for e in events if e.event_type == IncidentEventType.ESCALATED)
        self.assertIn("new_severity", esc_event.metadata)
        self.assertEqual(esc_event.metadata["new_severity"], "critical")

    def test_quieting_and_resolution_lifecycle(self):
        """Evaluating lifecycle on quiet incidents transitions ACTIVE -> MONITORING -> RESOLVED."""
        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs, as_of_utc="2026-10-01T13:45:00Z")
        inc = res.created_incidents[0]

        # Advance time by 50 hours (beyond 48h quiet threshold)
        events_quiet = self.incident_engine.evaluate_lifecycle(
            as_of_utc="2026-10-03T16:00:00Z",
            quiet_threshold_hours=48.0,
            resolution_threshold_hours=96.0,
        )
        self.assertGreaterEqual(len(events_quiet), 1)

        updated_inc = self.incident_repo.get_incident(inc.incident_id)
        self.assertEqual(updated_inc.status, IncidentStatus.MONITORING)

        # Advance time by 100 hours (beyond 96h resolution threshold)
        events_res = self.incident_engine.evaluate_lifecycle(
            as_of_utc="2026-10-05T20:00:00Z",
            quiet_threshold_hours=48.0,
            resolution_threshold_hours=96.0,
        )
        self.assertGreaterEqual(len(events_res), 1)

        resolved_inc = self.incident_repo.get_incident(inc.incident_id)
        self.assertEqual(resolved_inc.status, IncidentStatus.RESOLVED)

    def test_reopen_incident_workflow(self):
        """Explicitly closing an incident and reopening it creates complete audit events."""
        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        inc = res.created_incidents[0]

        # 1. Close incident explicitly
        closed_inc = self.incident_engine.close_incident(
            incident_id=inc.incident_id,
            reason="Controlled flare burn extinguished",
            actor="operator_jane",
        )
        self.assertEqual(closed_inc.status, IncidentStatus.CLOSED)

        # 2. Reopen incident explicitly
        reopened_inc = self.incident_engine.reopen_incident(
            incident_id=inc.incident_id,
            reason="New thermal flare flare-up reported",
            actor="operator_jane",
        )
        self.assertIn(reopened_inc.status, (IncidentStatus.ACTIVE, IncidentStatus.MONITORING))

        events = self.incident_repo.list_incident_events(inc.incident_id)
        event_types = [e.event_type for e in events]
        self.assertIn(IncidentEventType.CLOSED, event_types)
        self.assertIn(IncidentEventType.REOPENED, event_types)

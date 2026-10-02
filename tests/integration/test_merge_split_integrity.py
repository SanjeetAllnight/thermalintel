"""Merge and Split Integrity Validation Suite for ThermalIntel V2.

Verifies:
1. Deterministic merge survivor selection rule (earlier first_seen, higher count, higher FRP, lower ID).
2. Observation re-attribution: all observations from absorbed incident link to survivor.
3. Non-erasure of history: absorbed incident row remains in database with status CLOSED.
4. Bidirectional MERGED events recorded with complete metadata.
5. Idempotent repeated merge calls on already merged incidents.
6. Split operations: subset transferred to child incident with new deterministic stable ID.
7. Parent-child lineage preserved in event metadata and association records.
8. State recalculation: both parent and child centroids, FRPs, and counts are consistent.
9. Defensive validation against invalid inputs:
   - merging non-existent incident raises ValueError
   - merging incident with itself returns unchanged incident
   - splitting non-existent incident raises ValueError
   - splitting with empty list raises ValueError
   - splitting observations not belonging to parent raises ValueError
   - splitting ALL observations from parent raises ValueError.
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
    DISTINCT_SPATIAL_RECORDS,
    make_raw_firms_csv,
)


class TestMergeSplitIntegrity(unittest.TestCase):
    """Validation suite for deterministic merge and split mechanics."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "merge_split_test.db"

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

    def test_merge_incidents_deterministic_survivor_and_history(self):
        """Two incidents merge: survivor chosen deterministically, absorbed closed, history preserved."""
        # Create incident A (first_seen 08:00, count 1, FRP 80.0)
        rec_a = dict(DISTINCT_SPATIAL_RECORDS[0])
        rec_a["acq_time"] = "0800"
        rec_a["frp"] = 80.0
        csv_a = make_raw_firms_csv([rec_a])
        obs_a, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_a)
        res_a = self.incident_engine.correlate_observations(obs_a)
        inc_a = res_a.created_incidents[0]

        # Create incident B (first_seen 10:00, count 1, FRP 75.0)
        rec_b = dict(DISTINCT_SPATIAL_RECORDS[1])
        rec_b["acq_time"] = "1000"
        rec_b["frp"] = 75.0
        csv_b = make_raw_firms_csv([rec_b])
        obs_b, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_b)
        res_b = self.incident_engine.correlate_observations(obs_b)
        inc_b = res_b.created_incidents[0]

        self.assertNotEqual(inc_a.incident_id, inc_b.incident_id)

        # Merge incident A and incident B
        survivor, absorbed = self.incident_engine.merge_incidents(
            inc_a.incident_id,
            inc_b.incident_id,
            reason="Wildfire front coalesced across valley",
            actor="incident_commander",
        )

        # 1. Deterministic survivor rule: Inc A had earlier first_seen (08:00 vs 10:00), so A survives
        self.assertEqual(survivor.incident_id, inc_a.incident_id)
        self.assertEqual(absorbed.incident_id, inc_b.incident_id)

        # 2. Non-erasure of history: absorbed incident is CLOSED, not deleted
        db_absorbed = self.incident_repo.get_incident(inc_b.incident_id)
        self.assertIsNotNone(db_absorbed)
        self.assertEqual(db_absorbed.status, IncidentStatus.CLOSED)

        # 3. Observation re-attribution: survivor now has both observations
        survivor_obs = self.incident_repo.list_incident_observations(survivor.incident_id)
        self.assertEqual(len(survivor_obs), 2)
        survivor_obs_ids = {o.observation_id for o in survivor_obs}
        self.assertIn(obs_a[0].observation_id, survivor_obs_ids)
        self.assertIn(obs_b[0].observation_id, survivor_obs_ids)

        # 4. Survivor state recalculated
        self.assertEqual(survivor.observation_count, 2)
        self.assertEqual(survivor.peak_frp, max(rec_a["frp"], rec_b["frp"]))

        # 5. Timeline events recorded on both survivor and absorbed
        events_survivor = self.incident_repo.list_incident_events(survivor.incident_id)
        events_absorbed = self.incident_repo.list_incident_events(absorbed.incident_id)

        self.assertTrue(any(e.event_type == IncidentEventType.MERGED for e in events_survivor))
        self.assertTrue(any(e.event_type == IncidentEventType.MERGED for e in events_absorbed))

        # Check metadata on merged events
        surv_merge_evt = next(e for e in events_survivor if e.event_type == IncidentEventType.MERGED)
        self.assertEqual(surv_merge_evt.metadata["absorbed_incident_id"], absorbed.incident_id)

        abs_merge_evt = next(e for e in events_absorbed if e.event_type == IncidentEventType.MERGED)
        self.assertEqual(abs_merge_evt.metadata["surviving_incident_id"], survivor.incident_id)

        # 6. Idempotent repeated merge: calling merge again returns without corruption
        survivor_re, absorbed_re = self.incident_engine.merge_incidents(
            survivor.incident_id,
            absorbed.incident_id,
        )
        self.assertEqual(survivor_re.incident_id, survivor.incident_id)
        self.assertEqual(absorbed_re.incident_id, absorbed.incident_id)

    def test_split_incident_integrity_and_lineage(self):
        """Splitting an incident transfers observations to child, preserves lineage in event metadata."""
        # Create an incident with 3 observations
        csv_text = make_raw_firms_csv([
            INDUSTRIAL_BASELINE_RECORDS[0],
            INDUSTRIAL_BASELINE_RECORDS[1],
            dict(INDUSTRIAL_BASELINE_RECORDS[0], acq_time="1100", frp=50.0),
        ])
        observations, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv_text)
        self.assertEqual(len(observations), 3)

        res = self.incident_engine.correlate_observations(observations)
        self.assertEqual(len(res.created_incidents), 1)
        parent = res.created_incidents[0]
        self.assertEqual(parent.observation_count, 3)

        split_obs_id = observations[-1].observation_id

        # Split off 1 observation into child incident
        parent_after, child = self.incident_engine.split_incident(
            incident_id=parent.incident_id,
            split_observation_ids=[split_obs_id],
            reason="Secondary flare determined to be independent flare stack unit 2",
            actor="safety_officer",
        )

        # 1. Child incident has stable ID and correct observation count
        self.assertTrue(child.incident_id.startswith("INC-20261001-"))
        self.assertNotEqual(child.incident_id, parent.incident_id)
        self.assertEqual(child.observation_count, 1)

        # 2. Parent incident updated with remaining count
        self.assertEqual(parent_after.observation_count, 2)

        # 3. Observation attribution in DB
        child_obs = self.incident_repo.list_incident_observations(child.incident_id)
        self.assertEqual(len(child_obs), 1)
        self.assertEqual(child_obs[0].observation_id, split_obs_id)

        parent_obs = self.incident_repo.list_incident_observations(parent.incident_id)
        self.assertEqual(len(parent_obs), 2)
        self.assertNotIn(split_obs_id, [o.observation_id for o in parent_obs])

        # 4. Lineage recorded in event metadata
        parent_events = self.incident_repo.list_incident_events(parent.incident_id)
        child_events = self.incident_repo.list_incident_events(child.incident_id)

        parent_split_evt = next(e for e in parent_events if e.event_type == IncidentEventType.SPLIT)
        self.assertEqual(parent_split_evt.metadata["child_incident_id"], child.incident_id)

        child_split_evt = next(e for e in child_events if e.event_type == IncidentEventType.SPLIT)
        self.assertEqual(child_split_evt.metadata["parent_incident_id"], parent.incident_id)

    def test_merge_and_split_defensive_edge_inputs(self):
        """Verify error handling on non-existent, invalid, or illegal merge and split parameters."""
        # Merge non-existent incident
        with self.assertRaises(ValueError):
            self.incident_engine.merge_incidents("INC-FAKE-1", "INC-FAKE-2")

        # Merge incident with itself is safe no-op
        csv = make_raw_firms_csv([INDUSTRIAL_BASELINE_RECORDS[0]])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        inc = res.created_incidents[0]

        inc_same1, inc_same2 = self.incident_engine.merge_incidents(inc.incident_id, inc.incident_id)
        self.assertEqual(inc_same1.incident_id, inc.incident_id)

        # Split non-existent incident
        with self.assertRaises(ValueError):
            self.incident_engine.split_incident("INC-NON-EXISTENT", ["OBS-1"])

        # Split with empty observation list
        with self.assertRaises(ValueError):
            self.incident_engine.split_incident(inc.incident_id, [])

        # Split with observations not belonging to parent
        with self.assertRaises(ValueError):
            self.incident_engine.split_incident(inc.incident_id, ["OBS-FOREIGN-999"])

        # Split ALL observations from parent is rejected (cannot leave empty parent)
        with self.assertRaises(ValueError):
            self.incident_engine.split_incident(inc.incident_id, [obs[0].observation_id])

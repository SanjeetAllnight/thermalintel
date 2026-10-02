"""Property-based tests for canonical pipeline invariants.

Validates that fundamental architectural invariants hold under deterministic,
generative variations of inputs, orderings, and failure modes.

Invariants tested:
1. Deterministic Canonical Observation ID Generation.
2. Deterministic Normalization (idempotence and purity).
3. Idempotent Persistence (upserting N rows K times yields exactly N rows).
4. Entity Count Boundedness under duplicate-injected batches.
5. Ingestion Ordering Invariance in spatial clustering.
6. Quarantine Safety Invariant (invalid data never becomes valid persisted observations).
7. Referential Integrity of IncidentObservations (foreign key consistency).
8. Event Timeline Integrity (valid parent incident, monotonic non-decreasing timestamps).
9. Alert Deduplication Boundedness (repeated identical events yield <= 1 alert).
10. Replay Determinism Invariant (independent runs produce identical domain state).
"""

import os
import random
import tempfile
import sqlite3
import pytest
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from pathlib import Path

import services.api.database as db_mod
from services.api.migrations.runner import MigrationRunner
from services.api.schemas.common import RiskLevel, SourceType
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
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.ingestion.quarantine import QuarantineManager
from services.api.repositories.observation_repository import ObservationRepository
from services.api.incidents.repository import IncidentRepository
from services.api.alerts.repository import AlertV2Repository
from services.api.incidents.aggregator import IncidentAggregator
from services.replay.player import ReplayPlayer
from scenarios.loader import load_scenario_from_file

SCENARIOS_DIR = Path(__file__).resolve().parent.parent.parent / "scenarios" / "data"


class TestPipelineInvariants:
    """Rigorous property and invariant tests across the V2 canonical pipeline."""

    @pytest.fixture
    def rng(self):
        """Deterministic pseudorandom number generator with fixed seed."""
        return random.Random(42)

    @pytest.fixture
    def isolated_db(self):
        """Creates an isolated temporary database with all V2 migrations applied."""
        orig_db_path = db_mod.DB_PATH
        orig_env_db = os.environ.get("DATABASE_PATH")

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "property_test.db"
            os.environ["DATABASE_PATH"] = str(db_path)
            db_mod.DB_PATH = str(db_path)
            db_mod.invalidate_seed_cache()

            runner = MigrationRunner(db_path)
            runner.apply_migrations()

            def conn_factory():
                conn = sqlite3.connect(db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                return conn

            yield {
                "db_path": db_path,
                "conn_factory": conn_factory,
                "obs_repo": ObservationRepository(),
                "inc_repo": IncidentRepository(connection_factory=conn_factory),
                "alert_repo": AlertV2Repository(connection_factory=conn_factory),
            }

            if orig_env_db is not None:
                os.environ["DATABASE_PATH"] = orig_env_db
            else:
                os.environ.pop("DATABASE_PATH", None)
            db_mod.DB_PATH = orig_db_path
            db_mod.invalidate_seed_cache()

    def _generate_valid_raw_row(self, rng: random.Random, idx: int) -> Dict[str, Any]:
        """Generate a realistic raw FIRMS dictionary."""
        lat = round(rng.uniform(20.0, 35.0), 5)
        lon = round(rng.uniform(70.0, 85.0), 5)
        hour = rng.randint(0, 23)
        minute = rng.randint(0, 59)
        acq_time = f"{hour:02d}{minute:02d}"
        frp = round(rng.uniform(5.0, 350.0), 1)
        brightness = round(300.0 + (frp * 0.2) + rng.uniform(-5.0, 15.0), 1)
        bright_t31 = round(290.0 + rng.uniform(-10.0, 10.0), 1)
        conf = rng.choice(["nominal", "high", "low", "85", "95"])
        sat = rng.choice(["Suomi-NPP", "NOAA-20", "NOAA-21"])

        return {
            "latitude": lat,
            "longitude": lon,
            "brightness": brightness,
            "scan": 0.4,
            "track": 0.4,
            "acq_date": "2026-10-02",
            "acq_time": acq_time,
            "satellite": sat,
            "instrument": "VIIRS",
            "confidence": conf,
            "version": "2.0NRT",
            "bright_t31": bright_t31,
            "frp": frp,
            "daynight": "D" if 6 <= hour <= 18 else "N",
        }

    # -------------------------------------------------------------------------
    # Invariant 1: Deterministic Canonical Observation IDs
    # -------------------------------------------------------------------------
    def test_property_deterministic_canonical_observation_ids(self, rng):
        """Property: Observation ID generation is a pure mathematical function of canonical coordinates and sensor."""
        for _ in range(50):
            sat = rng.choice(["Suomi-NPP", "NOAA-20", "NOAA-21", "Terra", "Aqua"])
            instrument = rng.choice(["VIIRS", "MODIS"])
            lat = round(rng.uniform(-60.0, 60.0), 5)
            lon = round(rng.uniform(-150.0, 150.0), 5)
            acq_date = "2026-10-02"
            acq_time = f"{rng.randint(0, 23):02d}{rng.randint(0, 59):02d}"
            dn = rng.choice(["D", "N"])

            id1 = HotspotNormalizer.generate_observation_id(instrument, sat, acq_date, acq_time, lat, lon, dn)
            id2 = HotspotNormalizer.generate_observation_id(instrument, sat, acq_date, acq_time, lat, lon, dn)
            id3 = HotspotNormalizer.generate_observation_id(instrument, sat, acq_date, acq_time, lat, lon, dn)

            # Invariant: identical inputs always produce identical ID
            assert id1 == id2 == id3
            assert id1.startswith("OBS-")

            # Invariant: perturbation in coordinate changes the ID (collision resistance)
            perturbed_lat = round(lat + 0.001, 5)
            perturbed_id = HotspotNormalizer.generate_observation_id(instrument, sat, acq_date, acq_time, perturbed_lat, lon, dn)
            assert perturbed_id != id1

    # -------------------------------------------------------------------------
    # Invariant 2: Deterministic Normalization
    # -------------------------------------------------------------------------
    def test_property_deterministic_normalization(self, rng):
        """Property: Repeated normalization of the same raw record produces bit-for-bit identical Observations."""
        for i in range(25):
            row = self._generate_valid_raw_row(rng, i)
            _, obs1, err1 = HotspotNormalizer.normalize_row_with_diagnostics(row)
            _, obs2, err2 = HotspotNormalizer.normalize_row_with_diagnostics(row)

            assert err1 is None
            assert err2 is None
            assert obs1 is not None and obs2 is not None
            assert obs1.observation_id == obs2.observation_id
            assert obs1.latitude == obs2.latitude
            assert obs1.longitude == obs2.longitude
            assert obs1.frp == obs2.frp
            assert obs1.acquisition_time_utc == obs2.acquisition_time_utc

    # -------------------------------------------------------------------------
    # Invariant 3: Idempotent Persistence
    # -------------------------------------------------------------------------
    def test_property_idempotent_persistence(self, rng, isolated_db):
        """Property: Persisting N distinct observations K times results in exactly N stored rows."""
        repo = isolated_db["obs_repo"]
        db_path = isolated_db["db_path"]

        raw_rows = [self._generate_valid_raw_row(rng, i) for i in range(30)]
        observations = []
        for r in raw_rows:
            _, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(r)
            if obs:
                observations.append(obs)

        assert len(observations) == 30

        # Persist 4 times in a row (save_observations is idempotent via INSERT OR REPLACE)
        for iteration in range(4):
            repo.save_observations(observations)

        # Query all records
        stored_obs, total = repo.get_observations(limit=100)
        assert total == 30
        assert len(stored_obs) == 30

        # Primary key uniqueness in database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), COUNT(DISTINCT observation_id) FROM observations;")
        total_count, distinct_count = cursor.fetchone()
        conn.close()

        assert total_count == 30
        assert total_count == distinct_count

    # -------------------------------------------------------------------------
    # Invariant 4: Entity Count Boundedness Under Duplicate Ingestion
    # -------------------------------------------------------------------------
    def test_property_duplicate_ingestion_entity_count_bounded(self, rng, isolated_db):
        """Property: Ingesting U unique observations with D random duplicates never exceeds U total entities."""
        repo = isolated_db["obs_repo"]

        U = 20
        unique_obs: List[Observation] = []
        for i in range(U):
            _, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(self._generate_valid_raw_row(rng, i))
            unique_obs.append(obs)

        # Create mixed batch with 50 duplicates randomly chosen from the 20
        duplicates = [rng.choice(unique_obs) for _ in range(50)]
        mixed_batch = unique_obs + duplicates
        rng.shuffle(mixed_batch)

        assert len(mixed_batch) == 70

        repo.save_observations(mixed_batch)

        _, total = repo.get_observations(limit=200)
        assert total == U, f"Expected exactly {U} persisted entities, got {total}"

    # -------------------------------------------------------------------------
    # Invariant 5: Ingestion Ordering Invariance in Clustering
    # -------------------------------------------------------------------------
    def test_property_ordering_invariance_in_clustering(self, rng):
        """Property: The partitioning of observations into spatial clusters is invariant to presentation ordering."""
        # Generate 3 distinct spatial clusters separated by > 50km
        center_1 = (28.50, 77.20)
        center_2 = (29.50, 78.50)
        center_3 = (31.00, 76.00)

        centers = [center_1, center_2, center_3]
        all_obs: List[Observation] = []

        for c_idx, (c_lat, c_lon) in enumerate(centers):
            for i in range(5):
                lat = round(c_lat + rng.uniform(-0.005, 0.005), 5)
                lon = round(c_lon + rng.uniform(-0.005, 0.005), 5)
                row = {
                    "latitude": lat,
                    "longitude": lon,
                    "brightness": 320.0,
                    "scan": 0.4,
                    "track": 0.4,
                    "acq_date": "2026-10-02",
                    "acq_time": f"120{i}",
                    "satellite": "Suomi-NPP",
                    "instrument": "VIIRS",
                    "confidence": "high",
                    "version": "2.0NRT",
                    "bright_t31": 295.0,
                    "frp": 45.0,
                    "daynight": "D",
                }
                _, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(row)
                all_obs.append(obs)

        assert len(all_obs) == 15

        aggregator = IncidentAggregator(distance_threshold_km=3.0, time_window_hours=24.0)

        # Baseline clustering
        clusters_orig = aggregator.cluster_observations(all_obs)

        def build_cluster_partition(clusters):
            partition = {}
            for cl in clusters:
                member_ids = frozenset(o.observation_id for o in cl)
                for o in cl:
                    partition[o.observation_id] = member_ids
            return partition

        baseline_partition = build_cluster_partition(clusters_orig)

        # Test 5 different random permutations
        for perm_idx in range(5):
            shuffled_obs = list(all_obs)
            rng.shuffle(shuffled_obs)
            clusters_shuffled = aggregator.cluster_observations(shuffled_obs)
            shuffled_partition = build_cluster_partition(clusters_shuffled)

            # Invariant: every obs grouped with exactly the same peers regardless of input order
            for obs in all_obs:
                oid = obs.observation_id
                assert baseline_partition[oid] == shuffled_partition[oid], (
                    f"Ordering invariance broken in permutation {perm_idx} for observation {oid}"
                )

    # -------------------------------------------------------------------------
    # Invariant 6: Quarantine Safety Invariant
    # -------------------------------------------------------------------------
    def test_property_quarantine_safety_invariant(self, rng, isolated_db):
        """Property: Adversarially malformed rows are strictly quarantined and never persisted as valid Observations."""
        obs_repo = isolated_db["obs_repo"]

        # Rows with clearly invalid geospatial coordinates (will always trigger error)
        invalid_rows = [
            # Latitude out of bounds
            {"latitude": 91.5, "longitude": 77.0, "acq_date": "2026-10-02", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            {"latitude": -95.0, "longitude": 77.0, "acq_date": "2026-10-02", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            # Longitude out of bounds
            {"latitude": 28.0, "longitude": 185.0, "acq_date": "2026-10-02", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            {"latitude": 28.0, "longitude": -190.0, "acq_date": "2026-10-02", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            # Corrupted non-numeric values
            {"latitude": "BAD_LAT", "longitude": 77.0, "acq_date": "2026-10-02", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            # Invalid date format
            {"latitude": 28.0, "longitude": 77.0, "acq_date": "2026-99-99", "acq_time": "1200",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
            # Invalid time out of range
            {"latitude": 28.0, "longitude": 77.0, "acq_date": "2026-10-02", "acq_time": "2599",
             "frp": 10.0, "brightness": 320.0, "satellite": "Suomi-NPP", "instrument": "VIIRS",
             "version": "2.0NRT", "scan": 0.4, "track": 0.4, "bright_t31": 295.0, "daynight": "D"},
        ]

        valid_obs_list = []
        for r in invalid_rows:
            hotspot, obs, err = HotspotNormalizer.normalize_row_with_diagnostics(r)
            assert err is not None, f"Malformed row failed to trigger error: {r}"
            assert obs is None, f"Malformed row produced an Observation: {r}"
            if obs:
                valid_obs_list.append(obs)

        # Invariant: nothing was produced
        assert len(valid_obs_list) == 0

        # Invariant: no rows enter the database
        obs_repo.save_observations(valid_obs_list)
        _, total = obs_repo.get_observations()
        assert total == 0

    # -------------------------------------------------------------------------
    # Invariant 7: Referential Integrity of IncidentObservations
    # -------------------------------------------------------------------------
    def test_property_referential_integrity_invariants(self, rng, isolated_db):
        """Property: Every IncidentObservation maps to an existing Incident and an existing Observation."""
        obs_repo = isolated_db["obs_repo"]
        inc_repo = isolated_db["inc_repo"]
        db_path = isolated_db["db_path"]

        # Insert 10 observations
        observations = []
        for i in range(10):
            _, obs, _ = HotspotNormalizer.normalize_row_with_diagnostics(self._generate_valid_raw_row(rng, i))
            observations.append(obs)
        obs_repo.save_observations(observations)

        # Create 2 incidents
        for inc_idx in range(2):
            inc_id = f"INC-20261002-PROP{inc_idx}"
            now_iso = now_utc_iso()
            incident = Incident(
                incident_id=inc_id,
                status=IncidentStatus.ACTIVE,
                first_seen_utc=now_iso,
                last_seen_utc=now_iso,
                centroid_latitude=28.0 + inc_idx,
                centroid_longitude=77.0 + inc_idx,
                peak_frp=75.0,
                average_frp=50.0,
                observation_count=5,
                current_risk_score=75.0,
                current_severity=RiskLevel.HIGH,
                current_classification=SourceType.INDUSTRIAL,
                created_at_utc=now_iso,
                updated_at_utc=now_iso,
            )
            inc_repo.save_incident(incident)

            # Associate observations
            assigned_obs = observations[inc_idx * 5 : (inc_idx + 1) * 5]
            for o in assigned_obs:
                assoc = IncidentObservation(
                    incident_id=inc_id,
                    observation_id=o.observation_id,
                    associated_at_utc=now_iso,
                    association_type="PRIMARY",
                )
                inc_repo.add_incident_observation(assoc)

        # Invariant: SQL verification of foreign keys
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM incident_observations io
            LEFT JOIN incidents i ON io.incident_id = i.incident_id
            WHERE i.incident_id IS NULL;
        """)
        dangling_incidents = cursor.fetchone()[0]

        cursor.execute("""
            SELECT COUNT(*) FROM incident_observations io
            LEFT JOIN observations o ON io.observation_id = o.observation_id
            WHERE o.observation_id IS NULL;
        """)
        dangling_observations = cursor.fetchone()[0]
        conn.close()

        assert dangling_incidents == 0, "Dangling incident reference detected in incident_observations"
        assert dangling_observations == 0, "Dangling observation reference detected in incident_observations"

    # -------------------------------------------------------------------------
    # Invariant 8: Event Timeline Integrity
    # -------------------------------------------------------------------------
    def test_property_event_timeline_integrity_invariant(self, rng, isolated_db):
        """Property: Incident events reference valid incidents and have monotonically non-decreasing timestamps."""
        inc_repo = isolated_db["inc_repo"]

        inc_id = "INC-20261002-EVTLINE"
        now = datetime.now(timezone.utc)
        incident = Incident(
            incident_id=inc_id,
            status=IncidentStatus.ACTIVE,
            first_seen_utc=now.isoformat(),
            last_seen_utc=now.isoformat(),
            centroid_latitude=28.5,
            centroid_longitude=77.2,
            peak_frp=25.0,
            average_frp=25.0,
            observation_count=1,
            current_risk_score=35.0,
            current_severity=RiskLevel.MEDIUM,
            current_classification=SourceType.AGRICULTURAL,
            created_at_utc=now.isoformat(),
            updated_at_utc=now.isoformat(),
        )
        inc_repo.save_incident(incident)

        event_types_and_reasons = [
            (IncidentEventType.CREATED, "Initial detection"),
            (IncidentEventType.OBSERVATION_ADDED, "New hotspot correlated"),
            (IncidentEventType.ESCALATED, "FRP threshold exceeded"),
            (IncidentEventType.DEESCALATED, "FRP returned to normal"),
            (IncidentEventType.CLOSED, "No new detections for 96h"),
        ]
        base_time = now
        for i, (et, reason) in enumerate(event_types_and_reasons):
            ev_time = base_time + timedelta(minutes=10 * i)
            event = IncidentEvent(
                event_id=f"EVT-PROP-{inc_id}-{i}",
                incident_id=inc_id,
                event_type=et,
                timestamp_utc=ev_time.isoformat(),
                actor="property_test",
                reason=reason,
                metadata={"step": i},
            )
            inc_repo.save_incident_event(event)

        events = inc_repo.list_incident_events(inc_id)
        assert len(events) == len(event_types_and_reasons)

        # Invariant: Monotonic timestamps
        parsed_times = [datetime.fromisoformat(ev.timestamp_utc.replace("Z", "+00:00")) for ev in events]
        for idx in range(len(parsed_times) - 1):
            assert parsed_times[idx] <= parsed_times[idx + 1], (
                f"Event timeline broken between event {idx} and {idx + 1}"
            )

    # -------------------------------------------------------------------------
    # Invariant 9: Alert Deduplication Boundedness
    # -------------------------------------------------------------------------
    def test_property_alert_deduplication_boundedness(self, rng, isolated_db):
        """Property: Submitting K duplicate alert attempts for identical dedupe keys yields strictly <= 1 Alert."""
        alert_repo = isolated_db["alert_repo"]
        inc_repo = isolated_db["inc_repo"]

        inc_id = "INC-20261002-ALERTDEDUP"
        now_iso = now_utc_iso()
        inc_repo.save_incident(
            Incident(
                incident_id=inc_id,
                status=IncidentStatus.ACTIVE,
                first_seen_utc=now_iso,
                last_seen_utc=now_iso,
                centroid_latitude=28.0,
                centroid_longitude=77.0,
                peak_frp=500.0,
                average_frp=500.0,
                observation_count=5,
                current_risk_score=95.0,
                current_severity=RiskLevel.CRITICAL,
                current_classification=SourceType.INDUSTRIAL,
                created_at_utc=now_iso,
                updated_at_utc=now_iso,
            )
        )

        dedupe_key = f"ALERT:{inc_id}:SEVERITY_ESCALATION"

        # Attempt to insert identical alert 10 times (only the first should succeed)
        insert_results = []
        for attempt in range(10):
            alert = AlertV2(
                alert_id=f"ALT-PROP-{attempt}",
                incident_id=inc_id,
                rule_id="RULE_TEST_CRITICAL",
                dedupe_key=dedupe_key,
                priority=AlertSeverity.CRITICAL,
                state=AlertState.ACTIVE,
                title="Critical industrial flare",
                message=f"Attempt {attempt}",
                created_at_utc=now_iso,
            )
            res = alert_repo.insert(alert)
            insert_results.append(res)

        # Invariant: First insert returns True, subsequent return False (dedupe_key UNIQUE constraint)
        assert insert_results[0] is True
        assert all(r is False for r in insert_results[1:])

        # Invariant: Only 1 active alert exists for this dedupe_key
        alerts = alert_repo.list_alerts(incident_id=inc_id)
        matching = [a for a in alerts if a.dedupe_key == dedupe_key]
        assert len(matching) == 1, f"Alert deduplication bounded invariant violated: found {len(matching)} alerts"

    # -------------------------------------------------------------------------
    # Invariant 10: Replay Determinism Invariant
    # -------------------------------------------------------------------------
    def test_property_replay_determinism_invariant(self):
        """Property: Running the replay player twice with the same scenario yields identical state."""
        path = SCENARIOS_DIR / "scenario_1_industrial_spike.json"
        scenario = load_scenario_from_file(path)

        player1 = ReplayPlayer(scenario=scenario)
        player1.run_to_completion()
        pipe1 = player1.pipeline

        player2 = ReplayPlayer(scenario=scenario)
        player2.run_to_completion()
        pipe2 = player2.pipeline

        # Structural equivalence
        assert len(pipe1.incidents) == len(pipe2.incidents)
        assert len(pipe1.events) == len(pipe2.events)
        assert len(pipe1.alerts) == len(pipe2.alerts)

        # Semantic equivalence per incident
        for inc1, inc2 in zip(pipe1.incidents, pipe2.incidents):
            assert inc1.incident_id == inc2.incident_id
            assert inc1.peak_frp == inc2.peak_frp
            assert inc1.current_risk_score == inc2.current_risk_score
            assert inc1.current_severity == inc2.current_severity

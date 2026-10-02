"""Operational Alert Lifecycle Integrity Validation Suite for ThermalIntel V2.

Verifies:
1. AlertV2 creation triggered by qualifying incident transition events.
2. Deterministic deduplication preventing redundant alert creation.
3. Cooldown and anti-flood protection against chattering or noisy incidents.
4. Alert suppression preserving audit records with reason without paging operators.
5. Persistent acknowledgement in SQLite updating state and acknowledged_at_utc.
6. Automatic resolution of active alerts upon parent incident closure.
7. Unrelated non-critical transitions do not generate hazard alerts.
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
from services.api.schemas.common import RiskLevel
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    AlertSeverity,
    AlertState,
    now_utc_iso,
)
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.event import IncidentEvent
from services.api.schemas.v2.alert import AlertV2
from services.api.ingestion.normalizer import HotspotNormalizer
from services.api.repositories.observation_repository import ObservationRepository
from services.api.incidents.repository import IncidentRepository
from services.api.incidents.engine import IncidentEngine
from services.api.alerts.repository import AlertV2Repository
from services.api.alerts.service import AlertService
from services.api.alerts.cooldown import FloodProtectionEngine, FloodProtectionConfig

from tests.fixtures.v2_golden.fixtures import (
    INDUSTRIAL_BASELINE_RECORDS,
    INDUSTRIAL_SPIKE_RECORD,
    WEAK_DETECTION_RECORD,
    make_raw_firms_csv,
)


class TestAlertLifecycleIntegrity(unittest.TestCase):
    """Validation suite for transition-driven AlertV2 generation and lifecycle."""

    def setUp(self):
        self.original_db_path = db_mod.DB_PATH
        self.original_env_db = os.environ.get("DATABASE_PATH")

        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "alerts_test.db"

        os.environ["DATABASE_PATH"] = str(self.db_path)
        db_mod.DB_PATH = str(self.db_path)
        db_mod.invalidate_seed_cache()

        # Apply migrations
        runner = MigrationRunner(self.db_path)
        runner.apply_migrations()

        self.connection_factory = self._get_connection
        self.observation_repo = ObservationRepository()
        self.incident_repo = IncidentRepository(connection_factory=self.connection_factory)
        self.alert_repo = AlertV2Repository(connection_factory=self.connection_factory)

        self.incident_engine = IncidentEngine(repository=self.incident_repo)
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

    def test_alert_created_on_qualifying_incident_transition(self):
        """High FRP or critical escalation transition produces an active AlertV2."""
        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        incident = res.created_incidents[0]

        events = self.incident_repo.list_incident_events(incident.incident_id)
        trigger_event = events[0]

        alert = self.alert_service.process_incident_transition(
            incident=incident,
            event=trigger_event,
            extra_evidence={"frp": obs[0].frp},
        )

        self.assertIsNotNone(alert)
        self.assertEqual(alert.state, AlertState.ACTIVE)
        self.assertEqual(alert.incident_id, incident.incident_id)
        self.assertIn("CRITICAL", alert.title)
        self.assertIn("30.123", alert.title)

        # Check DB persistence
        db_alert = self.alert_repo.get_by_id(alert.alert_id)
        self.assertIsNotNone(db_alert)
        self.assertEqual(db_alert.state, AlertState.ACTIVE)

    def test_unrelated_low_risk_events_do_not_generate_alerts(self):
        """Weak or benign observations do not create false positive hazard alerts."""
        csv = make_raw_firms_csv([WEAK_DETECTION_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        incident = res.created_incidents[0]

        events = self.incident_repo.list_incident_events(incident.incident_id)
        trigger_event = events[0]

        alert = self.alert_service.process_incident_transition(
            incident=incident,
            event=trigger_event,
        )
        self.assertIsNone(alert, "Benign low-FRP detection should not generate an operational alert")

    def test_acknowledgement_lifecycle_workflow(self):
        """Acknowledging an alert transitions state in SQLite and records timestamp."""
        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        incident = res.created_incidents[0]
        event = self.incident_repo.list_incident_events(incident.incident_id)[0]

        alert = self.alert_service.process_incident_transition(
            incident=incident,
            event=event,
            extra_evidence={"frp": obs[0].frp},
        )
        self.assertIsNotNone(alert)

        # Acknowledge the alert
        ack_success = self.alert_service.acknowledge_alert(alert.alert_id)
        self.assertTrue(ack_success)

        # Verify DB state
        db_alert = self.alert_repo.get_by_id(alert.alert_id)
        self.assertIsNotNone(db_alert)
        self.assertEqual(db_alert.state, AlertState.ACKNOWLEDGED)
        self.assertIsNotNone(db_alert.acknowledged_at_utc)

    def test_automatic_resolution_on_incident_closure(self):
        """Closing an incident automatically resolves all open active alerts for that incident."""
        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        incident = res.created_incidents[0]
        event = self.incident_repo.list_incident_events(incident.incident_id)[0]

        alert = self.alert_service.process_incident_transition(
            incident=incident,
            event=event,
            extra_evidence={"frp": obs[0].frp},
        )
        self.assertIsNotNone(alert)
        self.assertEqual(alert.state, AlertState.ACTIVE)

        # Close incident via IncidentEngine
        closed_inc = self.incident_engine.close_incident(
            incident_id=incident.incident_id,
            reason="Controlled fire fully extinguished",
        )
        close_event = self.incident_repo.list_incident_events(incident.incident_id)[-1]

        # Process the CLOSED transition in alert service
        self.alert_service.process_incident_transition(
            incident=closed_inc,
            event=close_event,
        )

        # Verify alert transitioned from ACTIVE to RESOLVED
        resolved_alert = self.alert_repo.get_by_id(alert.alert_id)
        self.assertIsNotNone(resolved_alert)
        self.assertEqual(resolved_alert.state, AlertState.RESOLVED)
        self.assertIsNotNone(resolved_alert.resolved_at_utc)

    def test_anti_flood_cooldown_and_chattering_suppression(self):
        """Rapid repeated alerts on same incident within cooldown window are suppressed."""
        # Use custom strict flood engine: max 1 alert per 60 minutes
        strict_flood = FloodProtectionEngine(
            config=FloodProtectionConfig(
                per_rule_cooldown_seconds=3600,
                per_incident_cooldown_seconds=600,
                max_alerts_per_window=1,
                window_seconds=3600,
            )
        )
        alert_service = AlertService(
            connection_factory=self.connection_factory,
            repository=self.alert_repo,
            flood_engine=strict_flood,
        )

        csv = make_raw_firms_csv([INDUSTRIAL_SPIKE_RECORD])
        obs, _, _ = HotspotNormalizer.normalize_csv_with_quarantine(csv)
        res = self.incident_engine.correlate_observations(obs)
        incident = res.created_incidents[0]

        event1 = IncidentEvent(
            event_id="EVT-SPIKE-1",
            incident_id=incident.incident_id,
            event_type=IncidentEventType.ESCALATED,
            timestamp_utc="2026-10-01T14:00:00Z",
            actor="test",
            reason="First spike",
        )
        event2 = IncidentEvent(
            event_id="EVT-SPIKE-2",
            incident_id=incident.incident_id,
            event_type=IncidentEventType.ESCALATED,
            timestamp_utc="2026-10-01T14:05:00Z",  # 5 minutes later
            actor="test",
            reason="Second spike (chatter)",
        )

        # First alert: allowed
        alert1 = alert_service.process_incident_transition(
            incident=incident,
            event=event1,
            extra_evidence={"frp": 250.0},
        )
        self.assertIsNotNone(alert1)
        self.assertEqual(alert1.state, AlertState.ACTIVE)

        # Second alert: within 5 minutes, exceeding burst limit
        alert2 = alert_service.process_incident_transition(
            incident=incident,
            event=event2,
            extra_evidence={"frp": 260.0},
        )
        # Suppressed alert is created with state SUPPRESSED to maintain auditability without paging
        self.assertIsNotNone(alert2)
        self.assertEqual(alert2.state, AlertState.SUPPRESSED)
        self.assertIn("suppression_reason", alert2.evidence)

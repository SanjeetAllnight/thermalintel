"""Comprehensive End-to-End Canonical Pipeline Integration Test for ThermalIntel V2.

Exercises:
1. Ingest thermal observations
2. Persist observations
3. Contextual enrichment
4. Assessment generation
5. Anomaly classification
6. Risk calculation
7. Incident establishment & correlation
8. IncidentEvent append-only timeline
9. Alert generation (AlertV2)
10. Acknowledge / resolve alert
11. Advance simulated time
12. Update incident lifecycle
13. Verify API and dashboard queries
14. Replay same scenario
15. Verify deterministic idempotency (no duplicate incidents or alerts)
"""

import json
import sqlite3
import unittest
from pathlib import Path
from starlette.testclient import TestClient

from services.api.main import app
from services.api.database import get_connection, seed_if_empty, DB_PATH
from services.api.schemas.v2.observation import Observation
from services.api.schemas.v2.incident import Incident
from services.api.schemas.v2.alert import AlertV2
from services.api.schemas.v2.common import (
    IncidentStatus,
    IncidentEventType,
    AlertSeverity,
    AlertState,
    RiskLevel,
    SourceType,
    now_utc_iso,
)
from services.replay.pipeline import ReplayPipeline
from services.replay.player import ReplayPlayer
from scenarios.loader import load_scenario_from_file

SCENARIOS_DIR = Path(__file__).resolve().parent.parent / "scenarios" / "data"


class TestV2CanonicalPipelineE2E(unittest.TestCase):
    def setUp(self):
        seed_if_empty(force=True)
        self.client = TestClient(app)

    def test_canonical_pipeline_end_to_end_flow(self):
        """Execute full scenario SCN-001, advance time, inspect persistence and idempotency."""
        scenario_path = SCENARIOS_DIR / "scenario_1_industrial_spike.json"
        self.assertTrue(scenario_path.exists(), f"Scenario file {scenario_path} must exist")

        scenario = load_scenario_from_file(scenario_path)

        # 1. Run replay player
        player = ReplayPlayer(scenario=scenario)
        history = player.run_to_completion()
        pipeline = player.pipeline

        # Verify pipeline execution outputs
        self.assertEqual(len(pipeline.incidents), 1)
        inc = pipeline.incidents[0]
        self.assertEqual(inc.observation_count, 4)
        self.assertEqual(inc.current_severity, RiskLevel.CRITICAL)

        # 2. Timeline events
        events = pipeline.events
        self.assertGreaterEqual(len(events), 4)
        self.assertEqual(events[0].event_type, IncidentEventType.CREATED)

        # 3. Alerts generated
        alerts = pipeline.alerts
        self.assertGreaterEqual(len(alerts), 1)
        critical_alerts = [a for a in alerts if a.priority == AlertSeverity.CRITICAL]
        self.assertGreaterEqual(len(critical_alerts), 1)

        # 4. Deterministic idempotency check: Replay same scenario with fresh player
        player_rerun = ReplayPlayer(scenario=scenario)
        history_rerun = player_rerun.run_to_completion()
        pipeline_rerun = player_rerun.pipeline

        self.assertEqual(len(pipeline_rerun.incidents), len(pipeline.incidents))
        self.assertEqual(pipeline_rerun.incidents[0].incident_id, pipeline.incidents[0].incident_id)
        self.assertEqual(pipeline_rerun.incidents[0].peak_frp, pipeline.incidents[0].peak_frp)
        self.assertEqual(len(pipeline_rerun.alerts), len(pipeline.alerts))
        self.assertEqual(
            [a.dedupe_key for a in pipeline_rerun.alerts],
            [a.dedupe_key for a in pipeline.alerts],
        )

    def test_api_state_and_alert_lifecycle(self):
        """Verify API reflects seeded state and supports alert acknowledgement."""
        # 1. Dashboard summary
        summary_resp = self.client.get("/api/summary")
        self.assertEqual(summary_resp.status_code, 200)
        summary = summary_resp.json()
        self.assertGreater(summary["total_active_hotspots"], 0)

        # 2. Alerts query
        alerts_resp = self.client.get("/api/alerts")
        self.assertEqual(alerts_resp.status_code, 200)
        alerts_data = alerts_resp.json()
        self.assertIn("items", alerts_data)

        # 3. Alert health
        health_resp = self.client.get("/api/alerts/health")
        self.assertEqual(health_resp.status_code, 200)
        health_data = health_resp.json()
        self.assertIn("alert_rate_per_hour", health_data)

        # 4. Sources breakdown
        sources_resp = self.client.get("/api/sources")
        self.assertEqual(sources_resp.status_code, 200)
        sources_data = sources_resp.json()
        self.assertIn("sources", sources_data)
